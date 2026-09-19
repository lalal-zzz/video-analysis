"""Verified yt-dlp downloads with isolated cookie jars and bounded retries."""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp_server.auth import CookieStore
from mcp_server.storage import atomic_json, failure, platform_name

HOSTS = {"bilibili": ("bilibili.com", "b23.tv"), "youtube": ("youtube.com", "youtu.be"), "douyin": ("douyin.com", "iesdouyin.com")}


def validate_url(platform: str, url: str) -> str:
    platform_name(platform)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or not any(host == h or host.endswith("." + h) for h in HOSTS[platform]):
        raise ValueError("A supported platform HTTPS video URL is required")
    return url


class QuietLogger:
    # yt-dlp messages can contain signed URLs, credentials and terminal output.
    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class MediaDownloader:
    def __init__(self, store: CookieStore) -> None:
        self.store = store
        self.limits = {p: asyncio.Semaphore(3) for p in HOSTS}
        self.locks: dict[str, asyncio.Lock] = {}

    def _download(self, platform: str, url: str, directory: Path, audio: bool) -> dict[str, Any]:
        import yt_dlp

        directory.mkdir(parents=True, exist_ok=True)
        index = directory / "download.json"
        if index.exists():
            try:
                cached = json.loads(index.read_text(encoding="utf-8"))
                files = [Path(p).resolve() for p in cached.get("files", [])]
            except (ValueError, TypeError, AttributeError):
                cached, files = {}, []
            if files and all(p.is_relative_to(directory) and p.is_file() and p.stat().st_size > 0 for p in files):
                return {**cached, "cached": True}
        with tempfile.TemporaryDirectory(prefix="video-analysis-cookies-") as temporary:
            cookie = Path(temporary) / "cookies.txt"
            self.store.export(platform, cookie)
            options: dict[str, Any] = {
                "format": "bestaudio/best" if audio else "bestvideo*+bestaudio/best" if shutil.which("ffmpeg") else "best[ext=mp4]/best",
                "outtmpl": str(directory / "%(id)s.%(ext)s"), "noplaylist": True,
                "quiet": True, "no_warnings": True, "noprogress": True,
                "logger": QuietLogger(), "cookiefile": str(cookie), "socket_timeout": 30,
                "retries": 2, "fragment_retries": 2, "extractor_retries": 1,
                "continuedl": True, "overwrites": False, "ignoreerrors": False,
                "windowsfilenames": True,
            }
            files: list[Path] = []
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info or info.get("_type") in {"playlist", "multi_video"}:
                    raise RuntimeError("No single video downloaded")
                candidates = [info.get("filepath"), ydl.prepare_filename(info)]
                candidates.extend(item.get("filepath") for item in info.get("requested_downloads", []))
                for candidate in candidates:
                    if not candidate:
                        continue
                    path = Path(candidate).resolve()
                    if path.is_relative_to(directory) and path.is_file() and path.stat().st_size and path.suffix.lower() in {".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".ogg", ".opus", ".flv", ".ts", ".aac", ".wav", ".mov"}:
                        if path not in files:
                            files.append(path)
                if not files:
                    raise RuntimeError("Downloader did not produce a non-empty media file")
                result = {"status": "ok", "platform": platform, "url": url, "video_id": str(info.get("id", "")),
                          "title": info.get("title") or "", "files": [str(p) for p in files], "cached": False}
            atomic_json(index, result)
            return result

    def _bilibili_direct(self, url: str, directory: Path) -> dict[str, Any]:
        """Public low-resolution MP4 fallback when the extractor cannot resolve media."""
        import httpx

        match = re.search(r"/video/(BV[0-9A-Za-z]+)", url)
        if not match:
            raise ValueError("Bilibili fallback requires a BV video URL")
        bvid = match.group(1)
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
        with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
            for cookie in self.store.read("bilibili"):
                client.cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path", "/"))
            response = client.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid})
            response.raise_for_status()
            info = response.json()
            if info.get("code") != 0:
                raise RuntimeError(f"Bilibili API {info.get('code')}")
            page = info["data"]
            response = client.get("https://api.bilibili.com/x/player/playurl", params={"bvid": bvid, "cid": page["cid"], "qn": 16, "fnval": 0, "platform": "html5"})
            response.raise_for_status()
            play = response.json()
            streams = play.get("data", {}).get("durl", [])
            if play.get("code") != 0 or len(streams) != 1:
                raise RuntimeError("No complete MP4 stream available")
            directory.mkdir(parents=True, exist_ok=True)
            partial = directory / f"{bvid}.mp4.part"
            target = directory / f"{bvid}.mp4"
            media_url = streams[0]["url"]
            if not media_url.startswith(("https://", "http://")):
                raise ValueError("Invalid media URL")
            with client.stream("GET", media_url) as response:
                response.raise_for_status()
                if "text/" in response.headers.get("content-type", ""):
                    raise RuntimeError("Media response is not video")
                with partial.open("wb") as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
            if not partial.stat().st_size:
                raise RuntimeError("Empty download")
            partial.replace(target)
            result = {"status": "ok", "platform": "bilibili", "url": url, "video_id": bvid,
                      "title": page.get("title", ""), "files": [str(target)], "cached": False,
                      "fallback": "bilibili_direct", "quality": "platform_default_low_resolution"}
            atomic_json(directory / "download.json", result)
            return result

    async def download(self, platform: str, url: str, output: Path, audio: bool = False) -> dict[str, Any]:
        try:
            validate_url(platform, url)
            key = hashlib.sha256((platform + url + str(audio)).encode()).hexdigest()[:24]
            directory = (output / platform / key).resolve()
            lock = self.locks.setdefault(str(directory), asyncio.Lock())
            async with lock, self.limits[platform]:
                for attempt in range(2):
                    try:
                        # Shield the worker: do not release locks or close cookie state while it still runs.
                        task = asyncio.create_task(asyncio.to_thread(self._download, platform, url, directory, audio))
                        try:
                            return await asyncio.shield(task)
                        except asyncio.CancelledError:
                            await task
                            raise
                    except Exception as exc:
                        error = failure(exc, platform)
                        if attempt == 0 and error["code"] == "timeout":
                            await asyncio.sleep(1)
                            continue
                        if platform == "bilibili":
                            try:
                                fallback = asyncio.create_task(asyncio.to_thread(self._bilibili_direct, url, directory))
                                try:
                                    return await asyncio.shield(fallback)
                                except asyncio.CancelledError:
                                    await fallback
                                    raise
                            except Exception as fallback_exc:
                                fallback_error = failure(fallback_exc, platform)
                                if fallback_error["code"] in {"platform_restricted", "network_error", "timeout", "authentication_required"}:
                                    return fallback_error
                        return error
        except Exception as exc:
            return failure(exc, platform)
        return {"status": "error", "code": "operation_failed"}
