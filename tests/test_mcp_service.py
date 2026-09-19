from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from mcp_server.auth import BrowserAuth, CookieStore
from mcp_server.jobs import Jobs
from mcp_server.media import MediaDownloader, validate_url
from mcp_server.service import VideoService
from mcp_server.storage import Paths, atomic_json, failure
from models import VideoMetadata, VideoTranscript


@pytest.fixture
def paths(tmp_path):
    return Paths(tmp_path / "data", tmp_path / "state")


@pytest.fixture
async def service(paths):
    svc = VideoService(paths)
    yield svc
    await svc.close()


def cookie(name="SESSDATA", value="secret", domain=".bilibili.com", expires=-1):
    return {"name": name, "value": value, "domain": domain, "path": "/", "expires": expires, "secure": True}


def video(platform="youtube", id="v1"):
    return VideoMetadata(platform=platform, video_id=id, title="sample", author="creator", url=f"https://www.youtube.com/watch?v={id}")


def test_cookie_scope_expiry_and_session_export(paths, tmp_path):
    store = CookieStore(paths)
    store.save("bilibili", [cookie(), cookie("expired", expires=time.time()-10), cookie("foreign", domain=".evil.com")])
    store.export("bilibili", tmp_path / "cookies.txt")
    jar = MozillaCookieJar(str(tmp_path / "cookies.txt"))
    jar.load(ignore_discard=True)
    assert [(c.name, c.expires) for c in jar] == [("SESSDATA", None)]


@pytest.mark.asyncio
async def test_logout_clears_every_managed_credential_and_prevents_reimport(service, paths, tmp_path):
    old = tmp_path / "old"
    atomic_json(old / "bilibili_cookies.json", {"cookies": {"SESSDATA": "legacy"}})
    assert service.cookies.migrate(old) == ["bilibili"]
    paths.profiles.joinpath("bilibili").mkdir(parents=True)
    paths.cookies.joinpath("bilibili.txt").write_text("legacy jar")
    await service.auth.logout("bilibili")
    assert service.cookies.read("bilibili") == []
    assert not (paths.cookies / "bilibili.txt").exists()
    assert not (paths.profiles / "bilibili").exists()
    assert service.cookies.migrate(old) == []
    assert (old / "bilibili_cookies.json").exists()


@pytest.mark.asyncio
async def test_new_scraper_uses_fresh_session_and_does_not_leak_cross_domain(service):
    service.cookies.save("bilibili", [cookie(value="first")])
    async with service.scraper("bilibili") as scraper:
        assert scraper._client.cookies.get("SESSDATA") == "first"
        assert "cookie" not in scraper._client.build_request("GET", "https://example.com").headers
    service.cookies.save("bilibili", [cookie(value="second")])
    async with service.scraper("bilibili") as scraper:
        assert scraper._client.cookies.get("SESSDATA") == "second"


@pytest.mark.asyncio
async def test_bilibili_login_requires_live_verification(service):
    request = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(json=AsyncMock(return_value={"data": {"isLogin": False}}))))
    service.auth.contexts["bilibili"] = SimpleNamespace(cookies=AsyncMock(return_value=[cookie()]), request=request, close=AsyncMock())
    result = await service.auth.wait("bilibili", 0)
    assert result["status"] == "auth_required"
    assert not service.cookies.read("bilibili")
    request.get.return_value.json.return_value = {"data": {"isLogin": True}}
    assert (await service.auth.wait("bilibili", 0))["verification"] == "verified"
    assert service.cookies.read("bilibili")


def test_id_cookie_does_not_count_as_authenticated():
    assert not BrowserAuth.has_session("bilibili", [cookie("DedeUserID")])
    assert not BrowserAuth.has_session("douyin", [cookie("sid_guard", domain=".douyin.com")])


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://youtube.com.evil.com/v", "http://youtube.com/v", "https://user:pass@youtube.com/v", "https://127.0.0.1/v"])
def test_download_url_validation(url):
    with pytest.raises(ValueError):
        validate_url("youtube", url)


def test_raw_errors_never_expose_cookie_or_signed_url():
    result = failure(RuntimeError("cookies SESSDATA=secret https://example.com?token=private"))
    assert result["status"] == "auth_required"
    assert "secret" not in str(result) and "private" not in str(result)
    assert failure(RuntimeError("HTTP 403"))["status"] == "error"


@pytest.mark.asyncio
async def test_sixty_downloads_are_bounded_isolated_and_persisted(service, monkeypatch):
    active = maximum = 0
    async def worker(item):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(.001)
        active -= 1
        if item["id"] % 10 == 0:
            raise RuntimeError("failure")
        return {"status": "ok", "id": item["id"]}
    submitted = service.jobs.submit("download", [{"id": i} for i in range(60)], worker, 3)
    result = await service.jobs.wait(submitted["job_id"], 10)
    assert result["status"] == "partial"
    assert result["succeeded"] == 54 and result["failed"] == 6
    assert maximum == 3
    reloaded = Jobs(service.jobs.root).get(submitted["job_id"])
    assert reloaded == result


def test_crashed_job_is_not_success(paths):
    jobs = Jobs(paths.root / "jobs")
    atomic_json(jobs.root / "a.json", {"status": "running", "results": [], "job_id": "a"})
    assert jobs.get("a")["status"] == "interrupted"


@pytest.mark.asyncio
async def test_media_requires_real_file_and_reuses_cache(service, monkeypatch):
    import yt_dlp
    calls = []
    class FakeYDL:
        def __init__(self, options): self.options = options
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def prepare_filename(self, info): return self.options["outtmpl"].replace("%(id)s", "v1").replace("%(ext)s", "mp4")
        def extract_info(self, url, download):
            calls.append(url)
            info = {"id": "v1", "title": "sample"}
            Path(self.prepare_filename(info)).write_bytes(b"test media")
            return info
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    url = "https://www.youtube.com/watch?v=v1"
    one = await service.media.download("youtube", url, service.paths.root / "videos")
    two = await service.media.download("youtube", url, service.paths.root / "videos")
    assert one["status"] == "ok" and Path(one["files"][0]).is_file()
    assert two["cached"] and len(calls) == 1
    monkeypatch.setattr(FakeYDL, "extract_info", lambda *args, **kwargs: None)
    failed = await service.media.download("youtube", url + "2", service.paths.root / "videos")
    assert failed["status"] == "error"


@pytest.mark.asyncio
async def test_empty_subtitle_falls_back_and_artifact_analysis_roundtrip(service, monkeypatch):
    from transcribers import SubtitleParser, WhisperClient
    metadata = video()
    monkeypatch.setattr(SubtitleParser, "get_transcript", AsyncMock(return_value=VideoTranscript(video=metadata, source="subtitle")))
    service.media.download = AsyncMock(return_value={"status": "ok", "files": ["sample.mp4"]})
    fallback = AsyncMock(return_value=VideoTranscript(video=metadata, full_text="actual words", source="whisper"))
    monkeypatch.setattr(WhisperClient, "transcribe_file", fallback)
    result = await service.transcribe(metadata.model_dump(mode="json"))
    assert result["status"] == "ok"
    assert "actual words" in service.read(result["artifact"])["content"]
    assert (await service.transcribe(metadata.model_dump(mode="json")))["cached"]
    assert fallback.await_count == 1
    prepared = await service.analyze([result["artifact"]], "Summarize")
    assert prepared["mode"] == "host"
    saved = service.save_analysis("Summary", [result["artifact"]], "Summarize")
    assert "Summary" in service.read(saved["artifact"])["content"]


@pytest.mark.asyncio
async def test_latest_multiple_authors_fail_independently_and_deduplicate(service, monkeypatch):
    @asynccontextmanager
    async def scraper(platform):
        async def fetch(author, limit):
            if author == "bad": raise RuntimeError("login required")
            return [video(id="same")]
        yield SimpleNamespace(fetch_author_videos=fetch)
    monkeypatch.setattr(service, "scraper", scraper)
    result = await service.latest("youtube", ["a", "b", "bad"], 5)
    assert result["status"] == "partial"
    assert len(result["videos"]) == 1
    assert result["results"][-1]["status"] == "auth_required"


@pytest.mark.asyncio
async def test_domain_and_subscriptions_do_not_overwrite_implicitly(service):
    await service.domain("create", "test", {"description": "demo"})
    items = [{"author": {"name": "creator", "platform": "youtube", "url": "https://www.youtube.com/@creator"}}]
    await service.subscriptions("replace", "test", items)
    with pytest.raises(ValueError):
        await service.domain("create", "test", {})
    with pytest.raises(ValueError):
        await service.subscriptions("replace", "test", None)
    assert len((await service.subscriptions("list", "test", None))["items"]) == 1
    with pytest.raises(ValueError):
        await service.subscriptions("list", "../escape", None)
    with pytest.raises(ValueError):
        service.read("../../state/cookies/youtube.json")


@pytest.mark.asyncio
async def test_bilibili_following_pagination_keeps_page_size_fixed():
    from scrapers.bilibili import BilibiliScraper
    pages = []
    def handle(request):
        if request.url.path.endswith("nav"):
            return httpx.Response(200, json={"code": 0, "data": {"isLogin": True, "mid": 1}})
        page, size = int(request.url.params["pn"]), int(request.url.params["ps"])
        pages.append((page, size))
        start = (page-1)*size
        return httpx.Response(200, json={"code": 0, "data": {"list": [{"mid": i, "uname": f"author{i}"} for i in range(start+1, start+size+1)]}})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    scraper = BilibiliScraper(client, load_cookies=False)
    try:
        authors = await scraper.fetch_followed_authors(61)
        assert len({a["author_id"] for a in authors}) == 61
        assert pages == [(1, 50), (2, 50)]
    finally:
        await scraper.close()


@pytest.mark.asyncio
async def test_query_cache_changes_after_login(service, monkeypatch):
    from models import SearchResult
    fetch = AsyncMock(side_effect=lambda q: SearchResult(query=q, videos=[video()]))
    @asynccontextmanager
    async def scraper(platform):
        yield SimpleNamespace(fetch_videos=fetch)
    monkeypatch.setattr(service, "scraper", scraper)
    await service.search("youtube", "sample", 5)
    assert (await service.search("youtube", "sample", 5))["cached"]
    service.cookies.save("youtube", [cookie("SID", domain=".youtube.com")])
    assert not (await service.search("youtube", "sample", 5))["cached"]
    assert fetch.await_count == 2
    await service.search("youtube", "sample", 5, refresh=True)
    assert fetch.await_count == 3


@pytest.mark.asyncio
async def test_legacy_artifacts_import_without_overwriting(service, tmp_path):
    old = tmp_path / "legacy"
    (old / "transcripts").mkdir(parents=True)
    source = old / "transcripts" / "v.md"
    source.write_text("legacy words", encoding="utf-8")
    assert service.migrate(old)["copied_artifacts"] == 1
    assert service.migrate(old)["copied_artifacts"] == 0
    artifact = service.artifacts("transcripts", 10)["artifacts"][0]["id"]
    assert (await service.analyze([artifact], "summarize"))["mode"] == "host"
    assert source.read_text(encoding="utf-8") == "legacy words"


@pytest.mark.asyncio
async def test_youtube_creator_fetch_targets_channel_uploads(monkeypatch):
    import yt_dlp
    from scrapers.youtube import YouTubeScraper
    calls = []
    class YDL:
        def __init__(self, opts): assert opts["playlistend"] == 4
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            calls.append(url)
            return {"entries": [{"id": "v1", "view_count": None, "like_count": None, "comment_count": None}]}
    monkeypatch.setattr(yt_dlp, "YoutubeDL", YDL)
    videos = await YouTubeScraper().fetch_author_videos("https://www.youtube.com/@creator/videos?view=0", 4)
    assert calls == ["https://www.youtube.com/@creator/videos"]
    assert len(videos) == 1


@pytest.mark.asyncio
async def test_missing_browser_falls_back_to_isolated_chrome(service, monkeypatch):
    context = SimpleNamespace(on=lambda *args: None, close=AsyncMock())
    launch = AsyncMock(side_effect=[RuntimeError("Executable doesn't exist"), context])
    service.auth.playwright = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch), stop=AsyncMock())
    assert await service.auth.context("youtube", headless=True) is context
    assert launch.await_args_list[1].kwargs["channel"] == "msedge"
    assert launch.await_args_list[1].args[0] == str(service.paths.profiles / "youtube")


@pytest.mark.asyncio
async def test_analyzer_passes_large_prompt_over_stdin(monkeypatch):
    from analyzers.codex_client import CodexAnalyzer
    process = SimpleNamespace(communicate=AsyncMock(return_value=(b"analysis", b"")), returncode=0)
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    text = "long prompt" * 10000
    assert await CodexAnalyzer()._run_codex(text) == "analysis"
    assert spawn.call_args.args == ("codex", "exec", "--skip-git-repo-check", "-")
    process.communicate.assert_awaited_once_with(text.encode())


@pytest.mark.asyncio
async def test_bilibili_direct_rate_limit_is_not_reported_as_login(service, monkeypatch):
    def extractor(*args): raise RuntimeError("Video unavailable")
    def direct(*args): raise RuntimeError("HTTP 412")
    monkeypatch.setattr(service.media, "_download", extractor)
    monkeypatch.setattr(service.media, "_bilibili_direct", direct)
    result = await service.media.download("bilibili", "https://www.bilibili.com/video/BVtest", service.paths.root / "videos")
    assert result["code"] == "platform_restricted"
    assert result["status"] == "error"
