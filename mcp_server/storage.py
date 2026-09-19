"""Runtime paths, validated identifiers and atomic persistence."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

PLATFORMS = ("bilibili", "youtube", "douyin")


def platform_name(value: str) -> str:
    if value not in PLATFORMS:
        raise ValueError("platform must be bilibili, youtube or douyin")
    return value


def identifier(value: str) -> str:
    if not re.fullmatch(r"[\w-]{1,80}", value) or value in {".", ".."}:
        raise ValueError("identifier must contain 1-80 letters, digits, underscores or hyphens")
    return value


def within(root: Path, name: str) -> Path:
    root = root.resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("path must remain inside the requested data directory")
    return path


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".write-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str))


class Paths:
    def __init__(self, root: Path | None = None, state: Path | None = None) -> None:
        self.state = (state or Path(os.getenv("VIDEO_ANALYSIS_STATE_DIR") or user_data_dir("video-analysis", appauthor=False))).resolve()
        self.root = (root or Path(os.getenv("VIDEO_ANALYSIS_DATA_DIR") or self.state / "data")).resolve()
        self.cookies = self.state / "cookies"
        self.profiles = self.state / "browser-profiles"
        self.artifacts = self.root / "artifacts"
        self.domains = self.root / "domains"


def failure(exc: Exception, platform: str = "") -> dict[str, Any]:
    """Expose categories, never raw downloader exceptions (which can contain tokens)."""
    message = str(exc).lower()
    if any(x in message for x in ("unavailable", "not available", "removed", "deleted", "不存在")):
        status, code, text = "error", "video_unavailable", "该视频不存在、已下架或在当前地区不可用；请使用可播放的链接。"
    elif any(x in message for x in ("login", "log in", "sign in", "cookies", "登录", "401")):
        status, code, text = "auth_required", "authentication_required", "需要登录或刷新会话；调用 start_platform_login，完成后重试。"
    elif any(x in message for x in ("429", "412", "403", "captcha", "rate limit", "风控")):
        status, code, text = "error", "platform_restricted", "平台限流或验证拦截；请稍后重试。登录不保证能解除限制。"
    elif isinstance(exc, (ValueError, TypeError)):
        status, code, text = "error", "invalid_input", "参数无效；检查平台、链接、标识符或工具参数。"
    elif isinstance(exc, (ImportError, FileNotFoundError)):
        status, code, text = "error", "dependency_missing", "缺少依赖或文件；检查 get_system_status 与安装说明。"
    elif any(x in message for x in ("requested format", "no video formats", "ffmpeg", "javascript", "js runtime")):
        status, code, text = "error", "media_dependency_or_format", "没有可下载的媒体格式；检查 ffmpeg、yt-dlp 及 JavaScript 运行时。"
    elif any(x in message for x in ("connection", "certificate", "resolve", "network", "urlopen")):
        status, code, text = "error", "network_error", "无法连接平台；检查网络、代理和证书配置。"
    elif isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        status, code, text = "error", "timeout", "操作超时，可重试失败的条目。"
    else:
        status, code, text = "error", "operation_failed", "操作未完成；请检查网络、平台可用性与依赖。"
    return {"status": status, "code": code, "message": text, **({"platform": platform} if platform else {})}


def batch_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    succeeded = sum(r.get("status") == "ok" for r in results)
    status = "ok" if succeeded == len(results) else "partial" if succeeded else "auth_required" if results and all(r.get("status") == "auth_required" for r in results) else "error"
    return {"status": status, "results": results, "succeeded": succeeded, "failed": len(results) - succeeded}
