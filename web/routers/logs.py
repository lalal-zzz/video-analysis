"""日志路由."""

from __future__ import annotations

from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime

from litestar import get, MediaType
from litestar.response import Template
from litestar import Response
import json


@get("/logs")
async def logs_page() -> Template:
    """日志查看页面."""
    return Template(
        template_name="logs.html",
        context={"title": "日志中心"},
    )


@get("/api/logs", media_type=MediaType.JSON)
async def get_logs(
    level: str | None = None,
    pipeline: str | None = None,
    module: str | None = None,
    limit: int = 100,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    """API: 获取结构化日志. since/until 为 ISO 格式时间戳."""
    from log import database
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None
    entries = database.query(
        level=level, pipeline=pipeline, module=module,
        limit=limit, offset=offset,
        since=since_dt, until=until_dt,
    )
    return {"total": len(entries), "entries": entries}


@get("/api/logs/stats", media_type=MediaType.JSON)
async def get_logs_stats() -> dict:
    """API: 获取日志统计."""
    from log import database
    return database.stats()


@get("/api/logs/pipelines", media_type=MediaType.JSON)
async def get_pipelines() -> dict:
    """API: 列出所有管道名称."""
    from log import database
    pipelines = database.list_pipelines()
    return {"pipelines": pipelines}
