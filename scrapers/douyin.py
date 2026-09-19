"""Douyin 爬虫 — 支持扫码登录与 Cookie 持久化。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from exceptions import ScraperError
from models.rules import SelectorConfig
from models.search import SearchQuery, SearchResult
from models.video import VideoMetadata, VideoStats
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)
COOKIE_FILE = Path("data") / "douyin_cookies.json"


class DouyinScraper(BaseScraper):
    platform = "douyin"

    def __init__(self, client: httpx.AsyncClient | None = None, *, load_cookies: bool = True) -> None:
        self._client = client or httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.douyin.com/",
            },
            timeout=30.0,
        )
        self._search_url = "https://www.douyin.com/aweme/v1/web/search/item/"
        self._detail_url = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
        self._post_url = "https://www.douyin.com/aweme/v1/web/aweme/post/"
        if load_cookies:
            self._load_cookies()

    # ── Cookie 管理 ────────────────────────────────────────

    def _load_cookies(self) -> None:
        if not COOKIE_FILE.exists():
            return
        try:
            data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
            for k, v in data.get("cookies", {}).items():
                self._client.cookies.set(k, v)
            logger.info(f"[Douyin] Cookie loaded from {COOKIE_FILE}")
        except Exception as e:
            logger.warning(f"[Douyin] Cookie load failed: {e}")

    def _save_cookies(self) -> None:
        try:
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            COOKIE_FILE.write_text(
                json.dumps({"cookies": dict(self._client.cookies)}, indent=2),
                encoding="utf-8",
            )
            logger.info(f"[Douyin] Cookie saved to {COOKIE_FILE}")
        except Exception as e:
            logger.warning(f"[Douyin] Cookie save failed: {e}")

    def set_cookies(self, cookies: dict[str, str]) -> None:
        for k, v in cookies.items():
            self._client.cookies.set(k, v)
        self._save_cookies()

    async def is_logged_in(self) -> bool:
        try:
            resp = await self._client.get("https://www.douyin.com/")
            cookies = dict(self._client.cookies)
            return bool(cookies.get("sessionid"))
        except Exception:
            return False

    # ── QR 码登录（扫码登录页） ─────────────────────────────

    @staticmethod
    async def get_login_url() -> str:
        return "https://www.douyin.com/login/"

    @staticmethod
    async def poll_login(client: httpx.AsyncClient, max_polls: int = 90, interval: float = 2.0) -> dict[str, Any]:
        for i in range(max_polls):
            try:
                resp = await client.get("https://www.douyin.com/")
                resp.raise_for_status()
                cookies = dict(client.cookies)
                if cookies.get("sessionid"):
                    return {"status": "confirmed", "cookies": cookies}
            except Exception:
                pass
            await asyncio.sleep(interval)
        return {"status": "timeout"}

    @staticmethod
    async def login_with_qrcode() -> dict[str, Any]:
        login_url = await DouyinScraper.get_login_url()
        print()
        print("=" * 60)
        print("  抖音扫码登录")
        print("=" * 60)
        print(f"  1. 浏览器打开: {login_url}")
        print("  2. 选择「扫码登录」（右上角）")
        print("  3. 打开手机抖音扫一扫")
        print()
        print("  等待扫码中...（最长 3 分钟）")
        print()

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            await client.get(login_url)
            await asyncio.sleep(1)
            result = await DouyinScraper.poll_login(client)

            if result.get("status") == "confirmed":
                cookies = result.get("cookies", {})
                required = {
                    "sessionid": cookies.get("sessionid", ""),
                    "sid_guard": cookies.get("sid_guard", ""),
                }
                s = DouyinScraper()
                s.set_cookies(required)
                return {"status": "success", "message": "登录成功！Cookie 已自动保存"}
            return {"status": "error", "message": "登录超时，请重新运行"}

    @classmethod
    async def cli_login(cls) -> bool:
        result = await cls.login_with_qrcode()
        if result["status"] == "success":
            print(f"\n✅ {result['message']}")
            return True
        print(f"\n❌ {result['message']}")
        return False

    # ── 搜索 ───────────────────────────────────────────────

    async def fetch_videos(self, query: SearchQuery) -> SearchResult:
        for attempt in range(3):
            params = {
                "keyword": query.keywords,
                "search_type": "video",
                "offset": 0,
                "count": min(query.max_results, 20),
                "publish_time": 0,
                "sort_type": self._sort_param(query.sort),
            }
            try:
                resp = await self._client.get(self._search_url, params=params)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status_code") == 0:
                    aweme_list = data.get("aweme_list") or data.get("data") or []
                    if isinstance(aweme_list, dict):
                        aweme_list = list(aweme_list.values())
                    if not isinstance(aweme_list, list):
                        aweme_list = []

                    videos = []
                    for item in aweme_list:
                        if not isinstance(item, dict):
                            continue
                        video = self._parse_aweme(item)
                        if video is not None:
                            videos.append(video)

                    extra = data.get("extra", {}) or {}
                    return SearchResult(
                        query=query,
                        videos=videos,
                        total_available=extra.get("total_count", len(videos)),
                    )
                elif data.get("status_code") == 2483:
                    raise ScraperError("Douyin login required")

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (412, 429) and attempt < 2:
                    await asyncio.sleep(2.0 * (2 ** attempt))
                    continue
                raise ScraperError(f"Douyin search failed: {e}") from e
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2.0 * (2 ** attempt))
                    continue
                raise ScraperError(f"Douyin search failed: {e}") from e

        raise ScraperError("Douyin search failed after 3 retries")

    # ── 作者视频 ───────────────────────────────────────────

    async def fetch_author_videos(self, author: str, max_results: int = 50) -> list[VideoMetadata]:
        sec_uid = await self._resolve_sec_uid(author)
        if sec_uid is None:
            raise ScraperError("Author not resolved; use the exact Douyin profile URL")

        _results: list[VideoMetadata] = []
        offset = 0
        page_size = min(20, max_results)

        while len(_results) < max_results:
            params = {
                "sec_user_id": sec_uid,
                "max_cursor": offset,
                "count": page_size,
                "source": 1,
            }
            try:
                resp = await self._client.get(self._post_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                raise ScraperError(f"Douyin author fetch failed: {e}") from e

            aweme_list = data.get("aweme_list", [])
            if data.get("status_code") != 0:
                raise ScraperError(f"Douyin API error {data.get('status_code')}")
            if not aweme_list:
                break

            for item in aweme_list:
                video = self._parse_aweme(item)
                if video is not None:
                    _results.append(video)
                    if len(_results) >= max_results:
                        break
            next_cursor = data.get("max_cursor")
            if not data.get("has_more") or next_cursor is None or next_cursor == offset:
                break
            offset = next_cursor

        return _results

    async def select(self, result: SearchResult, selector: SelectorConfig) -> list[VideoMetadata]:
        return selector.apply(result.videos)

    # ── 辅助方法 ───────────────────────────────────────────

    async def _resolve_sec_uid(self, author: str) -> str | None:
        from urllib.parse import urlparse
        parsed = urlparse(author)
        if parsed.hostname in {"www.douyin.com", "douyin.com"} and parsed.path.startswith("/user/"):
            return parsed.path.split("/user/", 1)[1].strip("/")
        if author.startswith("MS4w"):
            return author
        params = {
            "keyword": author,
            "search_type": "user",
            "offset": 0,
            "count": 10,
        }
        try:
            resp = await self._client.get(self._search_url, params=params)
            data = resp.json()
            user_list = data.get("user_list", [])
            for item in user_list:
                user_info = item.get("user_info", {})
                if user_info.get("nickname") == author:
                    return user_info.get("sec_uid")
        except Exception:
            pass
        return None

    def _parse_aweme(self, item: dict[str, Any]) -> VideoMetadata | None:
        aweme_id = item.get("aweme_id")
        if not aweme_id:
            return None

        video_info = item.get("video", {}) or {}
        author_info = item.get("author", {}) or {}
        stats = item.get("statistics", {}) or {}

        thumbnail_url = ""
        cover = video_info.get("cover", {}) or {}
        if cover:
            urls = cover.get("url_list", [])
            if urls:
                thumbnail_url = urls[0]

        publish_time = None
        create_time = item.get("create_time")
        if isinstance(create_time, (int, float)) and create_time > 0:
            publish_time = datetime.fromtimestamp(create_time)

        return VideoMetadata(
            platform="douyin",
            video_id=str(aweme_id),
            title=item.get("desc", ""),
            author=author_info.get("nickname", ""),
            author_url=f"https://www.douyin.com/user/{author_info.get('sec_uid', '')}",
            url=f"https://www.douyin.com/video/{aweme_id}",
            duration=video_info.get("duration", 0) / 1000,
            thumbnail_url=thumbnail_url,
            stats=VideoStats(
                views=int(stats.get("play_count", 0)),
                likes=int(stats.get("digg_count", 0)),
                comments=int(stats.get("comment_count", 0)),
                shares=int(stats.get("share_count", 0)),
            ),
            publish_time=publish_time,
        )

    @staticmethod
    def _sort_param(sort: str) -> int:
        mapping = {"relevance": 0, "publish_time": 1, "views": 2}
        return mapping.get(sort, 0)

    async def close(self) -> None:
        await self._client.aclose()
