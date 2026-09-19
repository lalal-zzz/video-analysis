"""Application workflows shared by the MCP tools."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from cache.manager import DiskCache
from config.settings import CacheConfig, Settings
from data.manager import DataManager
from models import SearchQuery, VideoMetadata, VideoTranscript
from models.domain import DomainConfig, Subscription
from mcp_server.auth import BrowserAuth, CookieStore
from mcp_server.jobs import Jobs
from mcp_server.media import MediaDownloader, QuietLogger, validate_url
from mcp_server.storage import Paths, atomic_json, atomic_text, batch_result, failure, identifier, platform_name, within


class VideoService:
    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or Paths()
        self.cookies = CookieStore(self.paths)
        self.auth = BrowserAuth(self.paths, self.cookies)
        self.media = MediaDownloader(self.cookies)
        self.data = DataManager(self.paths.root)
        self.cache = DiskCache(Settings(cache=CacheConfig(storage_dir=str(self.paths.root / "cache"), query_ttl_hours=1)))
        self.jobs = Jobs(self.paths.root / "jobs")
        self.limits = {p: asyncio.Semaphore(3) for p in ("bilibili", "youtube", "douyin")}
        self.transcribe_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self.whisper: Any = None

    def event(self, operation: str, status: str) -> None:
        record = {"time": datetime.now(timezone.utc).isoformat(), "operation": operation, "status": status}
        atomic_json(self.paths.root / "events" / f"{uuid.uuid4().hex}.json", record)

    async def close(self) -> None:
        await self.jobs.close()
        await self.auth.close()
        if self.whisper:
            await self.whisper.close()

    def status(self) -> dict[str, Any]:
        return {"status": "ok", "platforms": {p: {"session_saved": self.auth.has_session(p, self.cookies.read(p)), "following": "api" if p == "bilibili" else "best_effort"} for p in self.limits},
                "ffmpeg": bool(shutil.which("ffmpeg")), "whisper": importlib.util.find_spec("whisper") is not None,
                "codex": bool(shutil.which("codex")), "claude": bool(shutil.which("claude")),
                "data_dir": str(self.paths.root), "active_jobs": len(self.jobs.tasks)}

    @asynccontextmanager
    async def scraper(self, platform: str) -> AsyncIterator[Any]:
        from scrapers import BilibiliScraper, DouyinScraper, YouTubeScraper
        platform_name(platform)
        with tempfile.TemporaryDirectory(prefix="video-analysis-query-") as temporary:
            if platform == "youtube":
                scraper = YouTubeScraper()
                jar = Path(temporary) / "cookies.txt"
                self.cookies.export(platform, jar)
                scraper._ydl_opts.update(cookiefile=str(jar), logger=QuietLogger(), socket_timeout=20, retries=1)
            else:
                scraper = {"bilibili": BilibiliScraper, "douyin": DouyinScraper}[platform](load_cookies=False)
                for cookie in self.cookies.read(platform):
                    scraper._client.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path", "/"))
            try:
                yield scraper
            finally:
                await scraper.close()

    def query_cache(self, platform: str) -> DiskCache:
        auth_key = hashlib.sha256(json.dumps(self.cookies.read(platform), sort_keys=True).encode()).hexdigest()[:16]
        return DiskCache(Settings(cache=CacheConfig(storage_dir=str(self.paths.root / "cache" / auth_key), query_ttl_hours=1)))

    async def search(self, platform: str, keywords: str, limit: int, refresh: bool = False) -> dict[str, Any]:
        platform_name(platform)
        if not keywords.strip() or not 1 <= limit <= 50:
            raise ValueError("keywords required; limit 1-50")
        query = SearchQuery(platform=platform, keywords=keywords, max_results=limit)
        # Login changes invalidate query cache, including cached anonymous failures.
        query_cache = self.query_cache(platform)
        cached = await query_cache.get_query(query)
        if cached is not None and not refresh:
            return {"status": "ok", "videos": [v.model_dump(mode="json") for v in cached.videos], "cached": True}
        async with self.limits[platform], self.scraper(platform) as scraper:
            result = await scraper.fetch_videos(query)
        if result.videos:
            await query_cache.set_query(result)
        return {"status": "ok", "videos": [v.model_dump(mode="json") for v in result.videos], "cached": False}

    async def latest(self, platform: str, authors: list[str], limit: int, refresh: bool = False) -> dict[str, Any]:
        platform_name(platform)
        if not 1 <= len(authors) <= 100 or not 1 <= limit <= 50:
            raise ValueError("1-100 authors and 1-50 videos per author are supported")

        async def one(author: str) -> dict[str, Any]:
            try:
                query = SearchQuery(platform=platform, author=author, keywords="creator_latest", max_results=limit, sort="publish_time")
                query_cache = self.query_cache(platform)
                cached = await query_cache.get_query(query)
                if cached is not None and not refresh:
                    return {"status": "ok", "author": author, "cached": True, "videos": [v.model_dump(mode="json") for v in cached.videos]}
                async with self.limits[platform], self.scraper(platform) as scraper:
                    values = await scraper.fetch_author_videos(author, limit)
                values.sort(key=lambda v: v.publish_time.timestamp() if v.publish_time else 0, reverse=True)
                if values:
                    from models import SearchResult
                    await query_cache.set_query(SearchResult(query=query, videos=values[:limit]))
                return {"status": "ok", "author": author, "videos": [v.model_dump(mode="json") for v in values[:limit]]}
            except Exception as exc:
                return {"author": author, **failure(exc, platform)}
        results = await asyncio.gather(*(one(author) for author in dict.fromkeys(authors)))
        seen: set[str] = set()
        videos = []
        for result in results:
            for video in result.get("videos", []):
                if video["video_id"] not in seen:
                    videos.append(video)
                    seen.add(video["video_id"])
        return {**batch_result(results), "videos": videos}

    async def followed(self, platform: str, limit: int) -> dict[str, Any]:
        platform_name(platform)
        if not 1 <= limit <= 500:
            raise ValueError("limit must be 1-500")
        if platform != "bilibili":
            return await self.auth.following(platform, limit)
        async with self.scraper(platform) as scraper:
            rows = await scraper.fetch_followed_authors(limit)
        return {"status": "ok", "authors": [{"platform": platform, **row} for row in rows], "limit_reached": len(rows) == limit}

    async def transcribe(self, raw: dict[str, Any]) -> dict[str, Any]:
        from transcribers import SubtitleParser, WhisperClient
        try:
            video = VideoMetadata.model_validate(raw)
            validate_url(video.platform, video.url)
            identifier(video.video_id)
            # Deduplicate transcription and serialize access to the single Whisper model.
            async with self.transcribe_lock:
                transcript = await self.cache.get_video(video.platform, video.video_id)
                cached = transcript is not None
                if transcript is None:
                    transcript = None
                    if video.platform == "youtube":
                        client = httpx.AsyncClient(timeout=30, follow_redirects=True)
                        for cookie in self.cookies.read(video.platform):
                            client.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path", "/"))
                        parser = SubtitleParser(client)
                        try:
                            transcript = await parser.get_transcript(video)
                        except Exception:
                            transcript = None
                        finally:
                            await parser.close()
                    if transcript is None or not transcript.full_text.strip():
                        if self.whisper is None:
                            self.whisper = WhisperClient(model_name="base", language=None, download_dir=str(self.paths.root / "audio"), load_cookies=False)
                        downloaded = await self.media.download(video.platform, video.url, self.paths.root / "audio", audio=True)
                        if downloaded["status"] != "ok":
                            return downloaded
                        transcript = await self.whisper.transcribe_file(video, Path(downloaded["files"][0]))
                    if not transcript.full_text.strip():
                        raise RuntimeError("Transcription returned no text")
                    await self.cache.set_video(transcript)
                key = f"{video.platform}-{video.video_id}"
                file = self.paths.artifacts / "transcripts" / f"{key}.json"
                atomic_json(file, transcript.model_dump(mode="json"))
                return {"status": "ok", "artifact": str(file.relative_to(self.paths.artifacts)), "video_id": video.video_id,
                        "source": transcript.source, "length": len(transcript.full_text), "cached": cached}
        except Exception as exc:
            return failure(exc, raw.get("platform", ""))

    def artifacts(self, kind: str, limit: int) -> dict[str, Any]:
        if kind not in {"transcripts", "results", "reviews"} or not 1 <= limit <= 500:
            raise ValueError("Invalid artifact kind/limit")
        files = sorted((self.paths.artifacts / kind).glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return {"status": "ok", "artifacts": [{"id": str(p.relative_to(self.paths.artifacts)), "size": p.stat().st_size} for p in files[:limit] if p.is_file()]}

    def read(self, artifact: str, offset: int = 0, limit: int = 20000) -> dict[str, Any]:
        path = within(self.paths.artifacts, artifact)
        if path.suffix not in {".md", ".txt", ".json"} or offset < 0 or not 1 <= limit <= 100000:
            raise ValueError("Invalid artifact request")
        text = path.read_text(encoding="utf-8")
        return {"status": "ok", "artifact": artifact, "content": text[offset:offset + limit], "next_offset": offset + limit if offset + limit < len(text) else None}

    async def analyze(self, artifacts: list[str], query: str, model: str = "host") -> dict[str, Any]:
        from models.analysis import AnalysisRequest
        if not artifacts or len(artifacts) > 100 or not query.strip():
            raise ValueError("1-100 transcript artifacts and a query are required")
        transcripts = []
        for artifact in artifacts:
            path = within(self.paths.artifacts / "transcripts", str(Path(artifact).relative_to("transcripts")))
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                transcripts.append(VideoTranscript.model_validate_json(text))
            elif path.suffix in {".md", ".txt"}:
                transcripts.append(VideoTranscript(video=VideoMetadata(platform="legacy", video_id=path.stem, title=path.stem, author="legacy", url=""), full_text=text, source="legacy"))
            else:
                raise ValueError("Unsupported transcript artifact")
        if model == "host":
            return {"status": "ok", "mode": "host", "query": query, "artifacts": artifacts,
                    "message": "由当前助手调用 read_artifact 阅读这些转录、完成分析，再调用 save_analysis 保存；本工具未生成分析结论。"}
        if model not in {"claude", "codex"}:
            raise ValueError("model must be host, claude or codex")
        from analyzers.claude_client import ClaudeAnalyzer
        from analyzers.codex_client import CodexAnalyzer
        analyzer = ClaudeAnalyzer() if model == "claude" else CodexAnalyzer()
        result = await analyzer.analyze(AnalysisRequest(transcripts=transcripts, user_query=query, model_type=model))
        return self.save_analysis(result.summary, artifacts, query)

    def save_analysis(self, content: str, artifacts: list[str], query: str) -> dict[str, Any]:
        if not content.strip():
            raise ValueError("Analysis content is empty")
        for artifact in artifacts:
            if not within(self.paths.artifacts, artifact).is_file():
                raise FileNotFoundError("Source artifact missing")
        file = self.paths.artifacts / "results" / f"{uuid.uuid4().hex}.md"
        atomic_text(file, f"# Analysis\n\nQuestion: {query}\n\nSources: {', '.join(artifacts)}\n\n{content}\n")
        return {"status": "ok", "artifact": str(file.relative_to(self.paths.artifacts))}

    async def subscriptions(self, action: str, domain: str, items: list[dict[str, Any]] | None) -> dict[str, Any]:
        identifier(domain)
        async with self.write_lock:
            if action == "replace":
                if items is None:
                    raise ValueError("replace requires explicit items (use [] to clear)")
                parsed = [Subscription.model_validate({**item, "domain": domain}) for item in items]
                atomic_json(self.paths.root / domain / "subscriptions.json", [item.model_dump(mode="json") for item in parsed])
            elif action != "list":
                raise ValueError("action must be list or replace")
            return {"status": "ok", "items": self.data.load_subscriptions(domain)}

    def migrate(self, directory: Path) -> dict[str, Any]:
        migrated_platforms = self.cookies.migrate(directory)
        count = 0
        for kind in ("transcripts", "results"):
            source = directory / kind
            for file in source.rglob("*") if source.exists() else []:
                if not file.is_file() or file.suffix not in {".md", ".txt"} or file.is_symlink():
                    continue
                key = hashlib.sha256(str(file.relative_to(directory)).encode()).hexdigest()[:20]
                target = self.paths.artifacts / kind / f"legacy-{key}{file.suffix}"
                if not target.exists():
                    atomic_text(target, file.read_text(encoding="utf-8"))
                    count += 1
        return {"status": "ok", "migrated_platforms": migrated_platforms, "copied_artifacts": count, "originals_preserved": True}

    async def domain(self, action: str, name: str, config: dict[str, Any] | None) -> dict[str, Any]:
        if action == "list":
            return {"status": "ok", "domains": [p.stem for p in self.paths.domains.glob("*.json")]}
        identifier(name)
        file = self.paths.domains / f"{name}.json"
        if action in {"create", "update"}:
            async with self.write_lock:
                if action == "create" and file.exists():
                    raise ValueError("Domain already exists")
                if action == "update" and not file.exists():
                    raise FileNotFoundError("Unknown domain")
                if config is None:
                    raise ValueError("config is required")
                model = DomainConfig.model_validate({**config, "name": name})
                atomic_json(file, model.model_dump(mode="json"))
                return {"status": "ok", "config": model.model_dump(mode="json")}
        cfg = DomainConfig.model_validate_json(file.read_text(encoding="utf-8"))
        if action == "read":
            return {"status": "ok", "config": cfg.model_dump(mode="json")}
        if action == "discover":
            results = []
            for query in cfg.discovery.video_search + cfg.discovery.author_search:
                results.append(await self.search(query.platform, " ".join(query.keywords), min(query.max_results, 50)))
            return batch_result(results)
        if action == "monitor":
            groups: dict[str, list[str]] = {}
            for item in self.data.load_subscriptions(name):
                subscription = Subscription.model_validate(item)
                if not subscription.is_blacklisted:
                    author = subscription.author
                    groups.setdefault(author.platform, []).append(author.url or author.author_id or author.name)
            results = [await self.latest(p, authors, cfg.monitor.max_videos_per_author) for p, authors in groups.items()]
            return {**batch_result(results), "videos": [v for result in results for v in result.get("videos", [])], "message": "已获取订阅作者更新；按需调用 batch_transcribe 和 analyze_videos。"}
        if action == "review":
            return {"status": "ok", "mode": "host", "subscriptions": self.data.load_subscriptions(name),
                    "artifacts": self.artifacts("results", 100)["artifacts"], "prompt": cfg.review_prompt_template or "依据已保存分析复盘作者观点与证据，注明缺失数据。"}
        raise ValueError("Unknown domain action")
