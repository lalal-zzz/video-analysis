"""Bilibili WBI author-query adapter for the supported service surface."""
from __future__ import annotations

import asyncio
import hashlib
import time
from urllib.parse import urlencode, urlparse

import httpx

from scrapers.bilibili import BilibiliScraper


MIXIN_ORDER = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)


class BilibiliServiceScraper(BilibiliScraper):
    """Reuse core parsing/pagination while signing requests at the HTTP boundary.

    The key is scoped to this scraper's managed session and reused for its pages.
    Public nav WBI keys are usable even when isLogin is false.
    """

    def __init__(self, client: httpx.AsyncClient | None = None, *, load_cookies: bool = False) -> None:
        super().__init__(client, load_cookies=load_cookies)
        self._space_url = "https://api.bilibili.com/x/space/wbi/arc/search"
        self._wbi_key = ""
        self._wbi_expires = 0.0
        self._wbi_lock = asyncio.Lock()
        self._client.event_hooks.setdefault("request", []).append(self._sign_author_request)

    async def _get_wbi_key(self) -> str:
        async with self._wbi_lock:
            if self._wbi_key and time.monotonic() < self._wbi_expires:
                return self._wbi_key
            response = await self._client.get(self._nav_url)
            response.raise_for_status()
            data = response.json().get("data") or {}
            images = data.get("wbi_img") or {}
            parts = [urlparse(str(images.get(name, ""))).path.rsplit("/", 1)[-1].split(".", 1)[0]
                     for name in ("img_url", "sub_url")]
            if any(len(part) != 32 or any(c not in "0123456789abcdefABCDEF" for c in part) for part in parts):
                raise RuntimeError("Bilibili WBI key unavailable")
            lookup = "".join(parts)
            self._wbi_key = "".join(lookup[i] for i in MIXIN_ORDER)[:32]
            self._wbi_expires = time.monotonic() + 300
            return self._wbi_key

    async def _sign_author_request(self, request: httpx.Request) -> None:
        if request.url.host != "api.bilibili.com" or request.url.path != "/x/space/wbi/arc/search":
            return
        key = await self._get_wbi_key()
        params = dict(request.url.params)
        params.pop("w_rid", None)
        params["wts"] = str(round(time.time()))
        params = {k: "".join(c for c in v if c not in "!'()*") for k, v in sorted(params.items())}
        params["w_rid"] = hashlib.md5((urlencode(params) + key).encode()).hexdigest()
        request.url = request.url.copy_with(params=params)
        request.headers["Referer"] = f"https://space.bilibili.com/{params['mid']}"
        request.headers["Origin"] = "https://space.bilibili.com"
