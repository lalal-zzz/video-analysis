"""Offline regression tests for the service's signed author-query boundary."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
import pytest
from yt_dlp.extractor.bilibili import BilibiliSpaceVideoIE

from mcp_server.bilibili import BilibiliServiceScraper
from mcp_server.service import VideoService
from mcp_server.storage import Paths


NAV = {"code": 0, "data": {"isLogin": False, "wbi_img": {
    "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
    "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
}}}


@pytest.mark.asyncio
async def test_signed_author_pages_preserve_metadata_without_requiring_login(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1702204169)
    oracle = BilibiliSpaceVideoIE()
    oracle._wbi_key_cache = {}
    monkeypatch.setattr(oracle, "_download_json", lambda *args, **kwargs: NAV)
    nav_calls = []
    pages = []

    def handle(request):
        if request.url.path.endswith("/nav"):
            nav_calls.append(request)
            return httpx.Response(200, json=NAV)
        assert request.url.path == "/x/space/wbi/arc/search"
        params = dict(request.url.params)
        expected = oracle._sign_wbi({k: v for k, v in params.items() if k not in {"wts", "w_rid"}}, "123")
        assert params == expected
        assert request.headers["Referer"] == "https://space.bilibili.com/123"
        assert request.headers["Origin"] == "https://space.bilibili.com"
        pn, ps = int(params["pn"]), int(params["ps"])
        pages.append((pn, ps, params["w_rid"]))
        return httpx.Response(200, json={"code": 0, "data": {"list": {"vlist": [
            {"bvid": f"BV{i}", "title": f"video{i}", "author": "creator", "mid": 123,
             "created": 1700000000 + i, "length": "02:15", "play": 42}
            for i in range((pn - 1) * ps, pn * ps)
        ]}}})

    scraper = BilibiliServiceScraper(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        videos = await scraper.fetch_author_videos("https://space.bilibili.com/123", 31)
        assert len(videos) == 31 and len({v.video_id for v in videos}) == 31
        assert [(pn, ps) for pn, ps, _ in pages] == [(1, 30), (2, 30)]
        assert pages[0][2] != pages[1][2] and len(nav_calls) == 1
        assert videos[-1].url == "https://www.bilibili.com/video/BV30"
        assert videos[0].duration == 135 and videos[0].stats.views == 42
        assert videos[0].publish_time is not None
    finally:
        await scraper.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("body, expected", [
    ({"code": -799, "message": "请求过于频繁，请稍后再试"}, "platform_restricted"),
    ({"code": 0, "data": {"list": {"vlist": []}}}, "ok"),
])
async def test_service_latest_keeps_signed_endpoint_failures_and_empty_results(tmp_path, monkeypatch, body, expected):
    service = VideoService(Paths(tmp_path / "data", tmp_path / "state"))

    def handle(request):
        return httpx.Response(200, json=NAV if request.url.path.endswith("/nav") else body)

    @asynccontextmanager
    async def scraper(platform):
        instance = BilibiliServiceScraper(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        try:
            yield instance
        finally:
            await instance.close()

    monkeypatch.setattr(service, "scraper", scraper)
    try:
        result = await service.latest("bilibili", ["123"], 2, refresh=True)
        assert result["videos"] == []
        item = result["results"][0]
        assert item.get("code", item["status"]) == expected
        assert "w_rid" not in json.dumps(result)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_missing_wbi_key_never_sends_unsigned_author_request():
    seen = []

    def handle(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"code": 0, "data": {"isLogin": False}})

    scraper = BilibiliServiceScraper(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    try:
        with pytest.raises(Exception, match="Bilibili author request failed"):
            await scraper.fetch_author_videos("123", 2)
        assert seen == ["/x/web-interface/nav"]
    finally:
        await scraper.close()
