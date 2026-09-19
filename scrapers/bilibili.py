"""Bilibili 爬虫 — 支持扫码登录与 Cookie 持久化。"""

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
COOKIE_FILE = Path("data") / "bilibili_cookies.json"


class BilibiliScraper(BaseScraper):
    platform = "bilibili"

    def __init__(self, client: httpx.AsyncClient | None = None, *, load_cookies: bool = True) -> None:
        self._client = client or httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
            },
            timeout=30.0,
        )
        self._search_url = "https://api.bilibili.com/x/web-interface/search/type"
        self._space_url = "https://api.bilibili.com/x/space/arc/search"
        self._nav_url = "https://api.bilibili.com/x/web-interface/nav"
        if load_cookies:
            self._load_cookies()

    def _load_cookies(self):
        if not COOKIE_FILE.exists():
            return
        try:
            data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
            for k, v in data.get("cookies", {}).items():
                self._client.cookies.set(k, v)
            logger.info(f"Bilibili Cookie loaded from {COOKIE_FILE}")
        except Exception as e:
            logger.warning(f"Cookie load failed: {e}")

    def _save_cookies(self):
        try:
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            cookies = dict(self._client.cookies)
            COOKIE_FILE.write_text(
                json.dumps({"cookies": cookies}, indent=2),
                encoding="utf-8",
            )
            logger.info(f"Bilibili Cookie saved to {COOKIE_FILE}")
        except Exception as e:
            logger.warning(f"Cookie save failed: {e}")

    def set_cookies(self, cookies: dict[str, str]):
        for k, v in cookies.items():
            self._client.cookies.set(k, v)
        self._save_cookies()

    async def is_logged_in(self) -> bool:
        try:
            resp = await self._client.get(self._nav_url)
            data = resp.json()
            return data.get("code") == 0 and data.get("data", {}).get("isLogin", False)
        except Exception:
            return False

    async def fetch_followed_authors(self, max_results: int = 200) -> list[dict[str, Any]]:
        """Return the logged-in user's Bilibili following list."""
        nav_resp = await self._client.get(self._nav_url)
        nav_data = nav_resp.json()
        account = nav_data.get("data", {})
        if nav_data.get("code") != 0 or not account.get("isLogin"):
            raise ScraperError("请先完成 Bilibili 登录")

        mid = account.get("mid")
        if not mid:
            raise ScraperError("登录信息中缺少用户 ID")

        authors: list[dict[str, Any]] = []
        page = 1
        limit = max(1, min(500, max_results))
        while len(authors) < limit:
            resp = await self._client.get(
                "https://api.bilibili.com/x/relation/followings",
                params={
                    "vmid": mid,
                    "pn": page,
                    "ps": 50,
                    "order": "desc",
                    "order_type": "attention",
                },
            )
            data = resp.json()
            if data.get("code") != 0:
                raise ScraperError(data.get("message") or "读取 Bilibili 关注列表失败")
            rows = data.get("data", {}).get("list", [])
            if not rows:
                break
            for row in rows:
                author_mid = str(row.get("mid", ""))
                name = str(row.get("uname", "")).strip()
                if author_mid and name:
                    authors.append({
                        "name": name,
                        "author_id": author_mid,
                        "url": f"https://space.bilibili.com/{author_mid}",
                    })
                    if len(authors) >= limit:
                        break
            page += 1
        return authors

    @staticmethod
    async def get_qrcode_info() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            )
            d = r.json()
            if d.get("code") != 0:
                return {"error": d.get("message", "QR code generation failed")}
            return {"qrcode_key": d["data"]["qrcode_key"], "url": d["data"]["url"]}

    @staticmethod
    async def poll_login(
        qrcode_key: str, max_polls: int = 60, interval: float = 2.0
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as c:
            for i in range(max_polls):
                r = await c.get(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                    params={"qrcode_key": qrcode_key},
                )
                d = r.json()
                code = d.get("code", -1)
                if code == 0:
                    return {
                        "status": "confirmed",
                        "cookies": dict(r.cookies),
                        "url": d.get("data", {}).get("url", ""),
                    }
                elif code == 86090:
                    return {"status": "scanned"}
                elif code == 86038:
                    return {"status": "expired"}
                await asyncio.sleep(interval)
            return {"status": "timeout"}

    @staticmethod
    async def login_with_qrcode() -> dict[str, Any]:
        qr = await BilibiliScraper.get_qrcode_info()
        if "error" in qr:
            return {"status": "error", "message": qr["error"]}

        url = qr["url"]
        key = qr["qrcode_key"]

        print()
        print("=" * 60)
        print("  BILIBILI 扫码登录")
        print("=" * 60)
        print()
        print("  1. 打开手机 Bilibili App")
        print("  2. 点击右上角 ··· → 扫一扫")
        print("  3. 扫描下方二维码")
        print()
        print(f"  二维码 URL: {url}")
        print(f"  二维码图片: https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={url}")
        print()
        print("  等待扫码中...（最长 2 分钟）")
        print()

        result = await BilibiliScraper.poll_login(key)

        if result.get("status") == "confirmed":
            cookies = result.get("cookies", {})
            required = {
                "SESSDATA": cookies.get("SESSDATA", ""),
                "bili_jct": cookies.get("bili_jct", ""),
                "buvid3": cookies.get("buvid3", ""),
            }
            s = BilibiliScraper()
            s.set_cookies(required)
            return {"status": "success", "message": "登录成功！Cookie 已自动保存"}
        elif result.get("status") == "scanned":
            print("已扫描，等待确认...")
            remaining = BilibiliScraper.poll_login(key, max_polls=30)
            if isinstance(remaining, dict) and remaining.get("status") == "confirmed":
                cookies_rem = remaining.get("cookies", {})
                s_rem = BilibiliScraper()
                s_rem.set_cookies({
                    "SESSDATA": cookies_rem.get("SESSDATA", ""),
                    "bili_jct": cookies_rem.get("bili_jct", ""),
                    "buvid3": cookies_rem.get("buvid3", ""),
                })
                return {"status": "success", "message": "登录成功！"}
            return {"status": "error", "message": "登录确认超时"}
        elif result.get("status") == "expired":
            return {"status": "error", "message": "二维码已过期，请重新运行"}
        else:
            return {"status": "error", "message": "登录超时，请重新运行"}

    async def fetch_videos(self, query: SearchQuery) -> SearchResult:
        for attempt in range(3):
            params = {"search_type": "video", "keyword": query.keywords, "page": 1}
            if query.sort == "publish_time":
                params["order"] = "pubdate"
            elif query.sort == "views":
                params["order"] = "click"
            try:
                resp = await self._client.get(self._search_url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 0:
                    result_data = data.get("data", {})
                    raw = result_data.get("result", [])
                    videos = []
                    for item in raw:
                        bvid = item.get("bvid") or item.get("aid")
                        if not bvid:
                            continue
                        title = (item.get("title", "") or "").replace("<em>", "").replace("</em>", "")
                        pubdate = item.get("pubdate")
                        pt = datetime.fromtimestamp(pubdate) if isinstance(pubdate, (int, float)) and pubdate > 0 else None
                        if query.date_from and pt and pt < query.date_from:
                            continue
                        if query.date_to and pt and pt > query.date_to:
                            continue
                        videos.append(VideoMetadata(
                            platform="bilibili",
                            video_id=str(bvid),
                            title=title,
                            author=item.get("author", ""),
                            author_url=f"https://space.bilibili.com/{item.get('mid', '')}",
                            url=f"https://www.bilibili.com/video/{bvid}",
                            duration=self._parse_duration(item.get("duration")),
                            thumbnail_url=item.get("pic", ""),
                            stats=VideoStats(
                                views=int(item.get("play", 0)),
                                likes=int(item.get("like", 0)),
                                comments=int(item.get("comment", 0)),
                            ),
                            publish_time=pt,
                        ))
                    if query.sort == "publish_time":
                        videos.sort(key=lambda v: v.publish_time or datetime.min, reverse=True)
                    elif query.sort == "views":
                        videos.sort(key=lambda v: v.stats.views or 0, reverse=True)
                    return SearchResult(
                        query=query, videos=videos,
                        total_available=result_data.get("numResults", len(videos)),
                    )
                elif data.get("code") == -412:
                    delay = 2.0 * (2 ** attempt)
                    logger.warning(f"412 rate limit, retrying in {delay}s ({attempt + 1}/3)")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise ScraperError(f"Bilibili API error: {data.get('message', 'unknown')}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (412, 429) and attempt < 2:
                    await asyncio.sleep(2.0 * (2 ** attempt))
                    continue
                raise ScraperError(f"Bilibili search failed: {e}") from e
        raise ScraperError("Bilibili search failed after 3 retries")

    async def fetch_author_videos(
        self, author: str, max_results: int = 50
    ) -> list[VideoMetadata]:
        mid = await self._resolve_mid(author)
        if mid is None:
            raise ScraperError("Author not resolved; use the exact Bilibili UID or profile URL")
        _r = []
        p = 1
        while len(_r) < max_results:
            params = {"mid": mid, "pn": p, "ps": min(30, max_results), "order": "pubdate"}
            try:
                resp = await self._client.get(self._space_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                raise ScraperError("Bilibili author request failed") from exc
            if data.get("code") != 0:
                raise ScraperError(f"Bilibili API error {data.get('code')}: {data.get('message', '')}")
            vl = data.get("data", {}).get("list", {}).get("vlist", [])
            if not vl:
                break
            for item in vl:
                bvid = item.get("bvid")
                if not bvid:
                    continue
                pubdate = item.get("created")
                pt = datetime.fromtimestamp(pubdate) if isinstance(pubdate, (int, float)) and pubdate > 0 else None
                _r.append(VideoMetadata(
                    platform="bilibili", video_id=str(bvid), title=item.get("title", ""),
                    author=item.get("author", ""),
                    author_url=f"https://space.bilibili.com/{item.get('mid', '')}",
                    url=f"https://www.bilibili.com/video/{bvid}",
                    duration=self._parse_duration(item.get("length")),
                    thumbnail_url=item.get("pic", ""),
                    stats=VideoStats(
                        views=int(item.get("play", 0)),
                        likes=int(item.get("video_review", 0)),
                        comments=int(item.get("comment", 0)),
                    ),
                    publish_time=pt,
                ))
                if len(_r) >= max_results:
                    break
            p += 1
        return _r

    async def select(self, result, selector):
        return selector.apply(result.videos)

    async def _resolve_mid(self, author: str) -> int | None:
        normalized = author.strip().rstrip("/")
        if normalized.isdigit():
            return int(normalized)
        if "space.bilibili.com/" in normalized:
            candidate = normalized.rsplit("/", 1)[-1].split("?", 1)[0]
            if candidate.isdigit():
                return int(candidate)
        params = {"search_type": "bili_user", "keyword": author, "page": 1}
        try:
            resp = await self._client.get(self._search_url, params=params)
            data = resp.json()
            if data.get("code") == 0:
                for u in data.get("data", {}).get("result", []):
                    if u.get("uname") == author:
                        return int(u["mid"])
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_duration(d):
        if d is None:
            return None
        if isinstance(d, (int, float)):
            return float(d)
        if isinstance(d, str):
            try:
                parts = [int(p) for p in d.split(":")]
                if len(parts) == 2:
                    return float(parts[0] * 60 + parts[1])
                if len(parts) == 3:
                    return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
            except (ValueError, TypeError):
                pass
        return None

    async def close(self):
        await self._client.aclose()

    @classmethod
    async def cli_login(cls):
        """CLI 扫码登录。生成二维码 → 等待扫码 → 自动保存 Cookie。"""
        result = await cls.login_with_qrcode()
        if result["status"] == "success":
            print(f"\n✅ {result['message']}")
        else:
            print(f"\n❌ {result['message']}")
        return result["status"] == "success"
