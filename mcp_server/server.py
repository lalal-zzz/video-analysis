"""STDIO entrypoint. All diagnostic logging goes to stderr."""
from __future__ import annotations

import functools
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP

from mcp_server.service import VideoService
from mcp_server.storage import failure, identifier, platform_name

service: VideoService | None = None


def current() -> VideoService:
    global service
    if service is None:
        service = VideoService()
    return service


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    try:
        yield
    finally:
        if service:
            await service.close()


mcp = FastMCP("video-analysis", lifespan=lifespan)


def tool(function: Any) -> Any:
    @functools.wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = await function(*args, **kwargs)
        except Exception as exc:
            result = failure(exc)
        if service:
            service.event(function.__name__, result.get("status", "unknown"))
        return result
    mcp.tool()(wrapped)
    return wrapped


@tool
async def get_system_status() -> dict[str, Any]:
    """Check dependencies and saved sessions. Saved sessions may have expired remotely."""
    return current().status()


@tool
async def start_platform_login(platform: str) -> dict[str, Any]:
    """Open managed Chromium for user QR/password login; public downloads need not log in."""
    return await current().auth.start(platform)


@tool
async def wait_for_platform_login(platform: str, timeout_seconds: int = 30) -> dict[str, Any]:
    """Check login for at most 45 seconds; repeat while the user is logging in."""
    return await current().auth.wait(platform, timeout_seconds)


@tool
async def wait_platform_login(platform: str, timeout_seconds: int = 30) -> dict[str, Any]:
    """Compatibility alias for wait_for_platform_login."""
    return await current().auth.wait(platform, timeout_seconds)


@tool
async def validate_platform_cookies(platform: str) -> dict[str, Any]:
    """Validate managed cookies locally and with the platform endpoint without returning cookie values."""
    return await current().auth.validate(platform)


@tool
async def logout_platform(platform: str) -> dict[str, Any]:
    """Remove the managed profile and all managed cookies; active batches must finish first."""
    if current().jobs.tasks:
        return {"status": "error", "code": "jobs_active", "message": "请等待批量任务完成后退出登录。"}
    return await current().auth.logout(platform)


@tool
async def migrate_legacy_data(directory: str) -> dict[str, Any]:
    """Copy legacy cookies and transcripts/results into managed storage; originals are preserved."""
    path = Path(directory).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("Existing legacy data directory required")
    return current().migrate(path)


@tool
async def search_videos(platform: str, keywords: str, max_results: int = 20, refresh: bool = False) -> dict[str, Any]:
    """Search 1-50 videos using the current saved session, without forcing login."""
    return await current().search(platform, keywords, max_results, refresh)


@tool
async def get_latest_videos(platform: str, authors: list[str], max_per_author: int = 5, refresh: bool = False) -> dict[str, Any]:
    """Fetch up to 50 recent videos each for up to 100 creators. More than 3 creators returns a job ID; poll get_job. Prefer profile URLs/IDs."""
    platform_name(platform)
    if not 1 <= len(authors) <= 100 or not 1 <= max_per_author <= 50:
        raise ValueError("Invalid author count or video limit")
    if len(authors) > 3:
        async def worker(item: dict[str, Any]) -> dict[str, Any]:
            return await current().latest(platform, [item["author"]], max_per_author, refresh)
        return current().jobs.submit("latest", [{"author": a} for a in dict.fromkeys(authors)], worker, 3)
    return await current().latest(platform, authors, max_per_author, refresh)


@tool
async def list_followed_authors(platform: str, limit: int = 200) -> dict[str, Any]:
    """Bilibili following API; YouTube subscriptions and Douyin follow-feed authors are experimental partial results."""
    return await current().followed(platform, limit)


@tool
async def batch_download(videos: list[dict[str, Any]], output_dir: str = "", max_concurrency: int = 3) -> dict[str, Any]:
    """Start a durable background download of 1-500 items (platform, url). Poll get_job; only verified nonempty media files succeed."""
    target = Path(output_dir).expanduser().resolve() if output_dir else current().paths.root / "videos"

    async def worker(item: dict[str, Any]) -> dict[str, Any]:
        return await current().media.download(item.get("platform", ""), item.get("url", ""), target)
    return current().jobs.submit("download", videos, worker, max_concurrency)


@tool
async def batch_transcribe(videos: list[dict[str, Any]], session: str = "") -> dict[str, Any]:
    """Start subtitle-first transcription with Whisper fallback. Poll get_job for reusable transcript artifact IDs."""
    if session:
        identifier(session)
    return current().jobs.submit("transcribe", videos, current().transcribe, 2)


@tool
async def get_job(job_id: str, wait_seconds: int = 0) -> dict[str, Any]:
    """Read persistent batch progress and per-item results; optionally wait up to 30 seconds. Interrupted jobs must be resubmitted; completed files are reused."""
    return await current().jobs.wait(job_id, wait_seconds)


@tool
async def analyze_videos(artifacts: list[str], user_query: str, model: str = "host") -> dict[str, Any]:
    """Prepare host analysis from transcript artifacts, or explicitly invoke an installed claude/codex analyzer."""
    return await current().analyze(artifacts, user_query, model)


@tool
async def save_analysis(content: str, artifacts: list[str], user_query: str = "") -> dict[str, Any]:
    """Save an analysis written by the current assistant with its source artifact IDs."""
    return current().save_analysis(content, artifacts, user_query)


@tool
async def manage_subscriptions(action: str, domain: str = "default", items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """List/replace local subscriptions; each item contains author={name,platform,url}. Replace requires explicit items; [] clears."""
    return await current().subscriptions(action, domain, items)


@tool
async def manage_domain(action: str, name: str = "default", config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Domain list/create/read/update/discover/monitor/review. Config uses DomainConfig, discovery.video_search and monitor.max_videos_per_author."""
    return await current().domain(action, name, config)


@tool
async def list_artifacts(kind: str = "transcripts", limit: int = 100) -> dict[str, Any]:
    """List transcript/result/review artifact IDs for read_artifact and analyze_videos."""
    return current().artifacts(kind, limit)


@tool
async def read_artifact(artifact: str, offset: int = 0, limit: int = 20000) -> dict[str, Any]:
    """Read a text artifact page. Continue at next_offset until null; cannot read cookies or arbitrary files."""
    return current().read(artifact, offset, limit)


@tool
async def get_overview() -> dict[str, Any]:
    """Counts of artifacts, saved domains, and active batch jobs."""
    paths = current().paths
    return {"status": "ok", "artifacts": {kind: len(list((paths.artifacts / kind).glob("*"))) for kind in ("transcripts", "results", "reviews")},
            "domains": len(list(paths.domains.glob("*.json"))), "active_jobs": len(current().jobs.tasks)}


@tool
async def query_logs(limit: int = 50) -> dict[str, Any]:
    """Read sanitized operation/status events, with no raw errors or session secrets."""
    files = sorted((current().paths.root / "events").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"status": "ok", "events": [json.loads(p.read_text(encoding="utf-8")) for p in files[:max(1, min(limit, 500))]]}


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
