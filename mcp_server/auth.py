"""Managed Chromium login and domain-scoped cookie storage."""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp_server.storage import Paths, atomic_json, atomic_text, platform_name, within

DOMAINS = {"bilibili": ("bilibili.com",), "youtube": ("youtube.com", "google.com"), "douyin": ("douyin.com",)}
LANDING = {"bilibili": "https://www.bilibili.com/", "youtube": "https://www.youtube.com/", "douyin": "https://www.douyin.com/"}
# Bilibili's passport host can redirect to passport.bilibili.cn, which is
# intermittently unreachable from some networks. Start on the stable main
# site instead; the user can click its login button and complete QR login.
# Start on each platform's own site. YouTube can redirect to Google after the
# user clicks its sign-in button; opening accounts.google.com directly is
# confusing and may trigger a different Google account flow.
LOGIN = dict(LANDING)


def allowed_cookie(platform: str, cookie: dict[str, Any]) -> bool:
    domain = str(cookie.get("domain", "")).lstrip(".").lower()
    expiry = cookie.get("expires", -1)
    return bool(cookie.get("value")) and any(domain == d or domain.endswith("." + d) for d in DOMAINS[platform]) and (expiry in (None, -1, 0) or float(expiry) > time.time())


class CookieStore:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def read(self, platform: str) -> list[dict[str, Any]]:
        platform_name(platform)
        file = self.paths.cookies / f"{platform}.json"
        if not file.exists():
            return []
        try:
            rows = json.loads(file.read_text(encoding="utf-8"))["cookies"]
            return [c for c in rows if allowed_cookie(platform, c)]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    def save(self, platform: str, cookies: list[dict[str, Any]]) -> None:
        platform_name(platform)
        atomic_json(self.paths.cookies / f"{platform}.json", {"cookies": [c for c in cookies if allowed_cookie(platform, c)]})

    def export(self, platform: str, target: Path) -> None:
        """Each downloader gets its own jar; yt-dlp may rewrite it on close."""
        jar = MozillaCookieJar(str(target))
        for c in self.read(platform):
            expiry = c.get("expires", -1)
            jar.set_cookie(Cookie(0, c["name"], c["value"], None, False, c["domain"], True,
                                  c["domain"].startswith("."), c.get("path", "/"), True,
                                  bool(c.get("secure")), int(expiry) if expiry and expiry > 0 else None,
                                  not expiry or expiry <= 0, None, None, {}, False))
        jar.save(ignore_discard=True, ignore_expires=False)

    def migrate(self, legacy: Path) -> list[str]:
        migrated = []
        for platform in DOMAINS:
            if (self.paths.cookies / f"{platform}.json").exists() or (self.paths.cookies / f"{platform}.logged-out").exists():
                continue
            rows = []
            file = legacy / f"{platform}_cookies.json"
            if file.exists():
                try:
                    old = json.loads(file.read_text(encoding="utf-8")).get("cookies", {})
                    rows = old if isinstance(old, list) else [{"name": k, "value": v, "domain": "." + DOMAINS[platform][0], "path": "/", "expires": -1} for k, v in old.items()]
                except (ValueError, OSError, TypeError):
                    pass
            shared = legacy / "ytdlp_cookies.txt"
            if shared.exists():
                try:
                    jar = MozillaCookieJar(str(shared))
                    jar.load(ignore_discard=True)
                    rows.extend({"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "secure": c.secure, "expires": c.expires or -1} for c in jar)
                except (ValueError, OSError):
                    pass
            if any(allowed_cookie(platform, c) for c in rows):
                self.save(platform, rows)
                migrated.append(platform)
        return migrated

    def clear(self, platform: str) -> None:
        platform_name(platform)
        for suffix in (".json", ".txt"):
            (self.paths.cookies / f"{platform}{suffix}").unlink(missing_ok=True)
        # Prevent old files being silently re-imported after an explicit logout.
        atomic_text(self.paths.cookies / f"{platform}.logged-out", "logged out\n")

    def summary(self, platform: str) -> dict[str, Any]:
        platform_name(platform)
        rows = self.read(platform)
        names = {str(row.get("name", "")) for row in rows}
        required = {"bilibili": {"SESSDATA"}, "youtube": {"SID", "SAPISID", "LOGIN_INFO"}, "douyin": {"sessionid", "sessionid_ss"}}[platform]
        return {"platform": platform, "cookie_file": bool(rows), "cookie_count": len(rows),
                "required_cookie_present": bool(names & required),
                "expired_or_invalid_removed": False}


class BrowserAuth:
    def __init__(self, paths: Paths, store: CookieStore) -> None:
        self.paths, self.store = paths, store
        self.contexts: dict[str, Any] = {}
        self.pages: dict[str, Any] = {}
        self.locks = {p: asyncio.Lock() for p in DOMAINS}
        self.playwright: Any = None
        self.start_lock = asyncio.Lock()

    async def context(self, platform: str, headless: bool = False) -> Any:
        platform_name(platform)
        if platform in self.contexts:
            return self.contexts[platform]
        async with self.start_lock:
            if self.playwright is None:
                from playwright.async_api import async_playwright
                self.playwright = await async_playwright().start()
        options = {
            "headless": headless,
            "viewport": {"width": 1280, "height": 900},
            "accept_downloads": False,
            # The managed profile has no access to the user's Windows Hello /
            # personal-browser passkeys. Prevent Google from auto-selecting
            # that unavailable credential and keep password/QR alternatives.
            "args": ["--disable-features=WebAuthentication,WebAuthenticationConditionalUI"],
        }
        try:
            context = await self.playwright.chromium.launch_persistent_context(str(self.paths.profiles / platform), **options)
        except Exception as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            # Use an installed browser binary with OUR profile, never the user's usual profile.
            context = None
            # Prefer the installed Edge channel when available. This still
            # uses our isolated profile directory, never the user's personal
            # Edge profile or its existing cookies.
            for channel in ("msedge", "chrome"):
                try:
                    context = await self.playwright.chromium.launch_persistent_context(str(self.paths.profiles / platform), channel=channel, **options)
                    break
                except Exception:
                    continue
            if context is None:
                raise exc
        self.contexts[platform] = context
        context.on("close", lambda *_: self._forget(platform, context))
        return context

    def _forget(self, platform: str, context: Any) -> None:
        if self.contexts.get(platform) is context:
            self.contexts.pop(platform, None)
            self.pages.pop(platform, None)

    async def start(self, platform: str) -> dict[str, Any]:
        platform_name(platform)
        async with self.locks[platform]:
            try:
                context = await self.context(platform)
            except Exception as exc:
                if "Executable doesn't exist" in str(exc):
                    return {"status": "error", "code": "browser_missing", "message": "请使用服务的 Python 执行 python -m playwright install chromium"}
                raise
            page = self.pages.get(platform)
            if page is None or page.is_closed():
                # A persistent context already owns an initial page. Reuse it
                # instead of opening a second tab and leaving about:blank
                # visible beside the login page.
                open_pages = [candidate for candidate in context.pages if not candidate.is_closed()]
                page = open_pages[0] if open_pages else await context.new_page()
                self.pages[platform] = page
                await page.goto(LOGIN[platform], wait_until="domcontentloaded", timeout=45000)
            await page.bring_to_front()
            return {"status": "auth_required", "platform": platform, "message": "请在打开的浏览器完成登录，再调用 wait_for_platform_login。"}

    @staticmethod
    def has_session(platform: str, cookies: list[dict[str, Any]]) -> bool:
        names = {c["name"] for c in cookies if allowed_cookie(platform, c)}
        required = {"bilibili": {"SESSDATA"}, "youtube": {"SID", "SAPISID", "__Secure-3PAPISID", "LOGIN_INFO"}, "douyin": {"sessionid", "sessionid_ss"}}
        return bool(names & required[platform])

    async def wait(self, platform: str, timeout_seconds: int = 30) -> dict[str, Any]:
        platform_name(platform)
        deadline = time.monotonic() + max(0, min(timeout_seconds, 45))
        async with self.locks[platform]:
            while True:
                context = self.contexts.get(platform)
                if context is None:
                    return {"status": "auth_required", "message": "登录窗口已关闭或服务已重启，请调用 start_platform_login。"}
                cookies = await context.cookies()
                if self.has_session(platform, cookies):
                    verified = False
                    if platform == "bilibili":
                        response = await context.request.get("https://api.bilibili.com/x/web-interface/nav", timeout=15000)
                        data = await response.json()
                        verified = bool(data.get("data", {}).get("isLogin"))
                    elif platform == "youtube":
                        page = self.pages[platform]
                        if urlparse(page.url).hostname not in {"www.youtube.com", "youtube.com"}:
                            await page.goto(LANDING[platform], wait_until="domcontentloaded")
                        verified = await page.locator("button#avatar-btn").count() > 0
                    else:
                        # Cookie presence is only experimental evidence on Douyin.
                        verified = False
                    if verified or platform == "douyin":
                        self.store.save(platform, cookies)
                        return {"status": "ok", "platform": platform, "verification": "verified" if verified else "session_detected", "best_effort": platform == "douyin"}
                if time.monotonic() >= deadline:
                    return {"status": "auth_required", "pending": True, "message": "尚未确认登录；完成后再次调用 wait_for_platform_login。"}
                await asyncio.sleep(1)

    async def logout(self, platform: str) -> dict[str, Any]:
        platform_name(platform)
        async with self.locks[platform]:
            context = self.contexts.pop(platform, None)
            self.pages.pop(platform, None)
            if context:
                await context.close()
            target = within(self.paths.profiles, platform)
            if target.exists():
                shutil.rmtree(target)
            self.store.clear(platform)
        return {"status": "ok", "platform": platform}

    async def following(self, platform: str, limit: int) -> dict[str, Any]:
        """DOM fallback deliberately reports incomplete coverage; no guessed authors."""
        if not self.has_session(platform, self.store.read(platform)):
            return {"status": "auth_required", "platform": platform, "authors": []}
        async with self.locks[platform]:
            context = await self.context(platform)
            await context.add_cookies(self.store.read(platform))
            page = await context.new_page()
            found: dict[str, dict[str, str]] = {}
            try:
                await page.goto("https://www.youtube.com/feed/channels" if platform == "youtube" else "https://www.douyin.com/follow", wait_until="domcontentloaded", timeout=45000)
                selector = 'ytd-channel-renderer a#main-link' if platform == "youtube" else 'a[href*="/user/"]'
                for _ in range(12):
                    rows = await page.locator(selector).evaluate_all("els => els.map(e => ({url:e.href,name:(e.innerText || e.getAttribute('title') || '').trim()}))")
                    for row in rows:
                        if row["name"] and row["url"].startswith(LANDING[platform]):
                            found[row["url"]] = {"name": row["name"], "url": row["url"], "platform": platform}
                    if len(found) >= limit:
                        break
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(750)
            finally:
                await page.close()
            # Douyin's follow feed contains authors visible in that feed, not all followings.
            return {"status": "partial", "best_effort": True, "complete": False,
                    "source": "subscription_page" if platform == "youtube" else "following_feed",
                    "authors": list(found.values())[:limit],
                    "message": "仅返回页面实际可见作者，不能保证覆盖全部关注；页面结构变化时可能为空。"}

    async def validate(self, platform: str) -> dict[str, Any]:
        platform_name(platform)
        summary = self.store.summary(platform)
        if not summary["cookie_file"] or not summary["required_cookie_present"]:
            return {"status": "auth_required", "verification": "local_cookie_missing", **summary,
                    "message": "没有可验证的完整 Cookie 会话，请调用 start_platform_login。"}
        cookies = self.store.read(platform)
        jar = {c["name"]: c["value"] for c in cookies}
        try:
            import httpx
            headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
            if platform == "bilibili":
                async with httpx.AsyncClient(headers=headers, cookies=jar, timeout=15, follow_redirects=True) as client:
                    response = await client.get("https://api.bilibili.com/x/web-interface/nav")
                    data = response.json()
                    valid = response.is_success and data.get("code") == 0 and bool(data.get("data", {}).get("isLogin"))
            elif platform == "youtube":
                async with httpx.AsyncClient(headers=headers, cookies=jar, timeout=15, follow_redirects=True) as client:
                    response = await client.get("https://www.youtube.com/feed/channels")
                    text = response.text
                    valid = response.is_success and "Sign in" not in text and "accounts.google.com" not in str(response.url)
            else:
                async with httpx.AsyncClient(headers=headers, cookies=jar, timeout=15, follow_redirects=True) as client:
                    response = await client.get("https://www.douyin.com/")
                    valid = response.is_success and bool(jar.get("sessionid") or jar.get("sessionid_ss"))
            return {"status": "ok" if valid else "auth_required", "verification": "remote_endpoint" if valid else "remote_rejected", **summary,
                    "message": "Cookie 已通过平台接口验证。" if valid else "Cookie 文件存在，但平台接口拒绝或无法确认会话；请重新登录。"}
        except Exception:
            return {"status": "error", "code": "validation_network_error", "verification": "network_error", **summary,
                    "message": "Cookie 本地格式有效，但平台验证请求失败；稍后重试。"}

    async def close(self) -> None:
        for context in list(self.contexts.values()):
            await context.close()
        self.contexts.clear()
        self.pages.clear()
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
