"""Litestar Web 应用入口."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from litestar import Litestar, get, MediaType
from litestar.static_files import StaticFilesConfig
from litestar.template.config import TemplateConfig
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.response import Template
from litestar import Response

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 初始化日志目录
from log import database
database.set_log_dir(str(PROJECT_ROOT / "data" / "logs"))

from data_manager import DataManager  # noqa: E402

# Import all route handlers
from web.routers.search import search_page, execute_search, analyze_videos, execute_author_search, api_subscribe, api_unsubscribe  # noqa: E402
from web.routers.domains import (domains_page, create_domain_page, create_domain,  # noqa: E402
                                  trigger_monitor, trigger_review, trigger_discover,
                                  trigger_monitor_htmx, trigger_review_htmx, trigger_discover_htmx,
                                  domain_detail_page, get_skill, update_skill, get_domain_data,
                                  list_skills, get_file_content, get_review_content)
from web.routers.results import results_page  # noqa: E402
from web.routers.transcripts import transcripts_page, transcript_detail  # noqa: E402
from web.routers.charts import get_author_trend, get_volume_trend  # noqa: E402
from web.routers.ws import ws_progress, ws_docs  # noqa: E402
from web.routers.task_runner import run_monitor, run_discover, run_review  # noqa: E402
from web.routers.ws import cancel_task, list_tasks, get_task  # noqa: E402
from web.routers.logs import logs_page, get_logs, get_logs_stats, get_pipelines  # noqa: E402
from web.routers.errors import page_not_found, server_error  # noqa: E402
from web.routers.login import (  # noqa: E402
    bilibili_login_page, bilibili_set_cookies, bilibili_login_status,
    generate_qrcode, poll_qrcode, confirm_bilibili_login,
    douyin_login_page, check_douyin_login, douyin_set_cookies,
)


@get("/")
async def index() -> Template:
    dm = DataManager()

    domains = [d.name for d in Path("data").iterdir() if d.is_dir() and (d / "subscriptions.json").exists()]
    subs_count = sum(len(dm.load_subscriptions(d)) for d in domains)
    today_count = sum(dm.count_analyses_recent(days=1, domain=d) for d in domains)
    transcripts_count = sum(dm.list_transcript_count(domain=d) for d in domains)

    return Template(
        template_name="dashboard.html",
        context={
            "title": "analyze-stock",
            "subs_count": subs_count,
            "domains_count": len(domains),
            "today_count": today_count,
            "transcripts_count": transcripts_count,
        },
    )


@get("/api/stats", media_type=MediaType.JSON)
async def api_stats() -> dict:
    dm = DataManager()
    domains = [d.name for d in Path("data").iterdir() if d.is_dir() and (d / "subscriptions.json").exists()]
    return {
        "subs_count": sum(len(dm.load_subscriptions(d)) for d in domains),
        "domains_count": len(domains),
        "today_count": sum(dm.count_analyses_recent(days=1, domain=d) for d in domains),
        "transcripts_count": sum(dm.list_transcript_count(domain=d) for d in domains),
    }


@get("/api/recent-activity", media_type=MediaType.JSON)
async def api_recent_activity(limit: int = 5) -> dict:
    dm = DataManager()
    domains = [d.name for d in Path("data").iterdir() if d.is_dir() and (d / "subscriptions.json").exists()]
    activities = []
    for domain in domains:
        reviews = dm.list_review_reports(domain, limit=1)
        for r in reviews:
            review_file = r.get("file", "")
            activities.append({
                "icon": "📊",
                "title": f"{domain} 领域复盘",
                "subtitle": "复盘完成" + (f" · {review_file}" if review_file else ""),
                "time": "今天",
                "click_action": f"location.href='/domains/{domain}'",
            })
        subs = dm.load_subscriptions(domain)
        if subs:
            latest = subs[-1] if isinstance(subs, list) else {}
            author = latest.get("author", {}) if isinstance(latest, dict) else {}
            if isinstance(author, dict):
                author_name = author.get("name", "未知作者")
            else:
                author_name = str(author)
            activities.append({
                "icon": "👤",
                "title": f"{domain}: {author_name}",
                "subtitle": "更新了视频" + (" | 评分 " + str(latest.get("score", ""))) if isinstance(latest, dict) and latest.get("score") else "更新了视频",
                "time": "最近",
                "click_action": f"location.href='/domains/{domain}'",
            })
    return {"activities": activities[:limit]}


@get("/health")
async def health() -> dict:
    return {"status": "ok"}


@get("/404")
async def page_not_found() -> Template:
    return Template(
        template_name="error.html",
        context={"title": "404 - 页面未找到", "code": 404, "message": "您所访问的页面不存在，请检查 URL 后重试"},
    )


@get("/error")
async def generic_error(msg: str = "服务器错误") -> Template:
    return Template(
        template_name="error.html",
        context={"title": "500 - 错误", "code": 500, "message": msg},
    )


template_config = TemplateConfig(
    directory=Path(PROJECT_ROOT) / "web" / "views",
    engine=JinjaTemplateEngine,
)

static_config = StaticFilesConfig(
    path="/static",
    directories=[str(Path(PROJECT_ROOT) / "web" / "static")],
)


from litestar.exceptions import NotFoundException


def app_error_handler(request: Any, exc: Exception) -> Template:
    """统一异常处理器 — 根据状态码渲染不同错误页面."""
    if isinstance(exc, NotFoundException):
        message = f"找不到路径: {request.url.path}"
        title = "404 - 页面未找到"
        code = 404
    else:
        message = str(exc) if str(exc) else "服务器内部错误，请稍后再试"
        title = f"500 - 服务器错误"
        code = 500
    return Template(
        template_name="error.html",
        context={"title": title, "code": code, "message": message},
        status_code=code,
    )


app = Litestar(
route_handlers=[
        index, health, api_stats, api_recent_activity,
        search_page, execute_search, analyze_videos, execute_author_search, api_subscribe, api_unsubscribe,
        domains_page, create_domain_page,
        create_domain, trigger_monitor, trigger_review, trigger_discover,
        trigger_monitor_htmx, trigger_review_htmx, trigger_discover_htmx,
        domain_detail_page, get_skill, update_skill, get_domain_data,
        list_skills, get_file_content, get_review_content,
        results_page, transcripts_page, transcript_detail,
        get_author_trend, get_volume_trend,
        ws_progress, ws_docs, cancel_task, list_tasks, get_task,
        logs_page, get_logs, get_logs_stats, get_pipelines,
        bilibili_login_page, bilibili_set_cookies, bilibili_login_status,
        generate_qrcode, poll_qrcode, confirm_bilibili_login,
        douyin_login_page, check_douyin_login, douyin_set_cookies,
        page_not_found, server_error,
    ],
    template_config=template_config,
    static_files_config=[static_config],
    exception_handlers={
        NotFoundException: app_error_handler,
        Exception: app_error_handler,
    },
    debug=True,
)
