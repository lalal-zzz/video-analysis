"""扫码登录路由 — Bilibili / 抖音 扫码登录 + Cookie 管理。"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from litestar import get, post
from litestar.response import Template, Redirect
from litestar.datastructures import State

from scrapers.bilibili import BilibiliScraper
from scrapers.douyin import DouyinScraper


# ── Bilibili 扫码登录 ─────────────────────────────────────

@get("/bilibili-login")
async def bilibili_login_page() -> Template:
    """Bilibili 扫码登录页面。"""
    return Template("login_bilibili.html")


@get("/api/bilibili/qrcode/generate")
async def generate_qrcode() -> dict[str, Any]:
    """生成 B站二维码，返回 qrcode_key 和 URL。"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            )
            d = r.json()
            if d.get("code") != 0:
                return {"status": "error", "message": d.get("message", "生成失败")}
            return {
                "status": "ok",
                "qrcode_key": d["data"]["qrcode_key"],
                "url": d["data"]["url"],
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@get("/api/bilibili/qrcode/poll")
async def poll_qrcode(qrcode_key: str) -> dict[str, Any]:
    """轮询 B站二维码扫码状态。"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": qrcode_key},
            )
            d = r.json()
            code = d.get("code", -1)
            if code == 0:
                return {"status": "confirmed", "cookies": dict(r.cookies)}
            elif code == 86090:
                return {"status": "scanned"}
            elif code == 86038:
                return {"status": "expired"}
            return {"status": "waiting"}
    except Exception:
        return {"status": "error"}


@post("/api/bilibili/confirm")
async def confirm_bilibili_login() -> dict[str, Any]:
    """二维码确认登录后，保存 Cookie 到 BilibiliScraper。"""
    try:
        scraper = BilibiliScraper()
        # 重新请求以获取最新的 cookies
        resp = await scraper._client.get(scraper._nav_url)
        data = resp.json()
        
        if data.get("code") == 0 and data.get("data", {}).get("isLogin", False):
            # 保存关键 cookie
            cookies = dict(scraper._client.cookies)
            required = {
                "SESSDATA": cookies.get("SESSDATA", ""),
                "bili_jct": cookies.get("bili_jct", ""),
                "buvid3": cookies.get("buvid3", ""),
            }
            scraper.set_cookies(required)
            return {"status": "success", "message": "Cookie 已保存"}
        return {"status": "error", "message": "登录信息不完整"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@post("/api/bilibili/cookies")
async def bilibili_set_cookies(data: dict[str, str]) -> dict[str, str]:
    """手动设置 Cookie。在浏览器登录后从控制台粘贴 document.cookie。"""
    cookie_str = data.get("cookies", "")
    if not cookie_str:
        return {"status": "error", "message": "请提供 Cookie 字符串"}

    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookies[name.strip()] = value.strip()

    BilibiliScraper().set_cookies(cookies)

    return {
        "status": "success",
        "message": f"已设置 {len(cookies)} 个 Cookie 字段",
    }


@get("/api/bilibili/status")
async def bilibili_login_status() -> dict[str, Any]:
    """检查 B站登录状态。"""
    try:
        bs = BilibiliScraper()
        resp = await bs._client.get(bs._nav_url)
        data = resp.json()
        is_login = data.get("code") == 0 and data.get("data", {}).get("isLogin", False)
        return {
            "logged_in": is_login,
            "username": data.get("data", {}).get("uname", "") if is_login else "",
            "message": "已登录" if is_login else "未登录",
        }
    except Exception:
        return {"logged_in": False, "message": "检查失败"}


# ── 抖音扫码登录 ──────────────────────────────────────────

@get("/douyin-login")
async def douyin_login_page() -> Template:
    """抖音扫码登录页面。"""
    return Template("login_douyin.html")


@get("/api/douyin/check-login")
async def check_douyin_login() -> dict[str, Any]:
    """检查抖音登录状态。"""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
            resp = await c.get("https://www.douyin.com/")
            cookies = dict(c.cookies)
            logged_in = bool(cookies.get("sessionid"))
            return {
                "logged_in": logged_in,
                "message": "已登录" if logged_in else "未登录",
            }
    except Exception as e:
        return {"logged_in": False, "message": str(e)}


@post("/api/douyin/cookies")
async def douyin_set_cookies(data: dict[str, str]) -> dict[str, str]:
    """手动设置抖音 Cookie。"""
    cookie_str = data.get("cookies", "")
    if not cookie_str:
        return {"status": "error", "message": "请提供 Cookie 字符串"}

    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookies[name.strip()] = value.strip()

    DouyinScraper().set_cookies(cookies)

    return {
        "status": "success",
        "message": f"已设置 {len(cookies)} 个 Cookie 字段",
    }
