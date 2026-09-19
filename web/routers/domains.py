"""领域管理路由."""

from __future__ import annotations

from pathlib import Path
from litestar import get, post, MediaType, Request
from litestar.response import Template
from data_manager import DataManager

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import DomainManager
from web.routers.task_runner import run_monitor, run_discover, run_review
from web.utils.progress import progress_manager, TaskStatus
import log
from data_manager import DataManager


dm = DomainManager()
data_mgr = DataManager()
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "domains"
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config" / "skills"


@get("/domains")
async def domains_page() -> Template:
    """领域管理页面."""
    domains = dm.list_domains()
    # 丰富领域数据：订阅作者数 + 已配置技能名
    from data_manager import DataManager
    dm_data = DataManager()
    for d in domains:
        name = d["name"]
        # 订阅作者数
        subs = dm_data.load_subscriptions(name)
        d["sub_count"] = len(subs)
        # 已配置技能名（从 SKILL.md 首行读取）
        skill_path = CONFIG_DIR / name / "SKILL.md"
        if skill_path.exists():
            skill_first_line = skill_path.read_text(encoding="utf-8").strip().split("\n")[0]
            # 去掉 markdown 标题标记
            d["skill_name"] = skill_first_line.lstrip("#").strip() if skill_first_line else name
        else:
            d["skill_name"] = ""
    return Template(
        template_name="domains.html",
        context={"title": "领域管理", "domains": domains},
    )


@get("/domains/create")
async def create_domain_page() -> Template:
    """创建领域页面."""
    return Template(
        template_name="domains.html",
        context={"title": "创建领域", "domain_name": "", "intent": ""},
    )


@post("/domains/create", media_type=MediaType.TEXT)
async def create_domain(request: Request) -> str:
    """创建领域."""
    data = await request.form()
    name = data.get("name", "")
    intent = data.get("intent", "")
    template = data.get("template", "stock")

    if not name or not intent:
        return '<div class="text-red-500">请填写领域名称和描述</div>'

    try:
        with log.pipeline_context(f"domain_create_{name}"):
            result = dm.create(name, intent, template_name=template)
        return f'''
        <div class="p-4 bg-green-50 border border-green-200 rounded">
            <h3 class="font-bold text-green-800">创建成功</h3>
            <p class="text-sm text-green-700 mt-1">领域 "{name}" 已创建</p>
            <div class="mt-2 text-sm text-green-600">
                文件: {", ".join(result["files"][:3])}
            </div>
        </div>
        '''
    except Exception as e:
        log.log("ERROR", "web.domains", "domain_create_error",
                f"Failed to create domain '{name}': {e}", error=str(e))
        return f'<div class="text-red-500">错误: {e}</div>'


@post("/domains/{domain_name:str}/monitor", media_type=MediaType.JSON)
async def trigger_monitor(domain_name: str) -> dict:
    """触发监控（异步，返回 task_id）."""
    import asyncio

    log.log("INFO", "web.domains", "monitor_trigger",
            f"Monitor triggered for domain '{domain_name}'")

    task_id = progress_manager.create_task("monitor", domain_name)
    progress_manager.update(task_id, status=TaskStatus.RUNNING, step="开始", message=f"监控 {domain_name}...")

    async def _run():
        result = await run_monitor(domain_name)
        return result

    asyncio.create_task(_run())

    return {
        "status": "started",
        "task_id": task_id,
        "message": f"监控任务已启动 (task: {task_id})",
        "domain": domain_name,
    }


@post("/domains/{domain_name:str}/discover", media_type=MediaType.JSON)
async def trigger_discover(domain_name: str) -> dict:
    """触发发现（异步，返回 task_id）."""
    import asyncio

    log.log("INFO", "web.domains", "discover_trigger",
            f"Discover triggered for domain '{domain_name}'")

    task_id = progress_manager.create_task("discover", domain_name)
    progress_manager.update(task_id, status=TaskStatus.RUNNING, step="开始", message=f"发现 {domain_name}...")

    async def _run():
        result = await run_discover(domain_name)
        return result

    asyncio.create_task(_run())

    return {
        "status": "started",
        "task_id": task_id,
        "message": f"发现任务已启动 (task: {task_id})",
        "domain": domain_name,
    }


@post("/domains/{domain_name:str}/review", media_type=MediaType.JSON)
async def trigger_review(domain_name: str) -> dict:
    """触发复盘（异步，返回 task_id）."""
    import asyncio

    log.log("INFO", "web.domains", "review_trigger",
            f"Review triggered for domain '{domain_name}'")

    task_id = progress_manager.create_task("review", domain_name)
    progress_manager.update(task_id, status=TaskStatus.RUNNING, step="开始", message=f"复盘 {domain_name}...")

    async def _run():
        result = await run_review(domain_name)
        return result

    asyncio.create_task(_run())

    return {
        "status": "started",
        "task_id": task_id,
        "message": f"复盘任务已启动 (task: {task_id})",
        "domain": domain_name,
    }


@post("/domains/{domain_name:str}/monitor-htmx", media_type=MediaType.TEXT)
async def trigger_monitor_htmx(domain_name: str) -> str:
    """触发监控 (HTMX 版，同步)."""
    try:
        result = dm.run(domain_name, "monitor")
        log.log("INFO", "web.domains", "monitor_htmx",
                f"Monitor HTMX for '{domain_name}': {result.get('monitored', 0)} monitored, {result.get('errors', 0)} errors")
        if result.get("status") == "ok":
            return f'''
            <div class="p-3 bg-blue-50 rounded text-sm">
                监控完成: {result.get("monitored", 0)} 视频, {result.get("errors", 0)} 错误
            </div>
            '''
        return f'<div class="text-red-500">错误: {result.get("message")}</div>'
    except Exception as e:
        log.log("ERROR", "web.domains", "monitor_htmx_error",
                f"HTMX monitor error for '{domain_name}': {e}", error=str(e))
        return f'<div class="text-red-500">错误: {e}</div>'


@post("/domains/{domain_name:str}/review-htmx", media_type=MediaType.TEXT)
async def trigger_review_htmx(domain_name: str) -> str:
    """触发复盘 (HTMX 版，同步)."""
    try:
        result = dm.run(domain_name, "review")
        log.log("INFO", "web.domains", "review_htmx",
                f"Review HTMX for '{domain_name}'")
        if result.get("status") == "ok":
            return f'''
            <div class="p-3 bg-purple-50 rounded">
                <h4 class="font-bold text-purple-800">复盘完成</h4>
                <p class="text-sm text-purple-600 mt-1">
                    评分调整: {result.get("score_changes", 0)} | 新拉黑: {result.get("new_blacklists", 0)}
                </p>
            </div>
            '''
        return f'<div class="text-red-500">错误: {result.get("message")}</div>'
    except Exception as e:
        log.log("ERROR", "web.domains", "review_htmx_error",
                f"HTMX review error for '{domain_name}': {e}", error=str(e))
        return f'<div class="text-red-500">错误: {e}</div>'


@post("/domains/{domain_name:str}/discover-htmx", media_type=MediaType.TEXT)
async def trigger_discover_htmx(domain_name: str) -> str:
    """触发发现 (HTMX 版，同步)."""
    try:
        result = dm.run(domain_name, "discover")
        log.log("INFO", "web.domains", "discover_htmx",
                f"Discover HTMX for '{domain_name}'")
        if result.get("status") == "ok":
            return f'''
            <div class="p-3 bg-yellow-50 border border-yellow-200 rounded text-sm">
                发现完成: {result.get("new_authors", 0)} 位新作者
            </div>
            '''
        return f'<div class="text-red-500">错误: {result.get("message")}</div>'
    except Exception as e:
        log.log("ERROR", "web.domains", "discover_htmx_error",
                f"HTMX discover error for '{domain_name}': {e}", error=str(e))
        return f'<div class="text-red-500">错误: {e}</div>'


# ── 领域详情 ─────────────────────────────────────────────


@get("/domains/{domain_name:str}")
async def domain_detail_page(domain_name: str) -> Template:
    """领域详情页：SKILL.md + 配置 + 订阅 + 复盘."""
    skill_path = CONFIG_DIR / domain_name / "SKILL.md"
    config_path = CONFIG_DIR / domain_name / "config.yaml"

    skill_content = ""
    config_content = ""
    if skill_path.exists():
        skill_content = skill_path.read_text(encoding="utf-8")
    if config_path.exists():
        config_content = config_path.read_text(encoding="utf-8")

    subscriptions = data_mgr.load_subscriptions(domain_name)
    blacklist = data_mgr.load_blacklist(domain_name)
    reviews = data_mgr.list_review_reports(domain_name)
    domains_list = dm.list_domains()
    domain_info = next((d for d in domains_list if d["name"] == domain_name), {})

    return Template(
        template_name="domain_detail.html",
        context={
            "title": f"领域: {domain_name}",
            "domain": domain_info,
            "domain_name": domain_name,
            "skill_content": skill_content,
            "config_content": config_content,
            "subscriptions": subscriptions,
            "blacklist": blacklist,
            "reviews": reviews,
        },
    )


@get("/api/domains/{domain_name:str}/skill")
async def get_skill(domain_name: str) -> dict:
    """获取 SKILL.md 内容."""
    skill_path = CONFIG_DIR / domain_name / "SKILL.md"
    if not skill_path.exists():
        return {"status": "error", "message": "SKILL.md not found"}
    return {"status": "ok", "content": skill_path.read_text(encoding="utf-8")}


@post("/api/domains/{domain_name:str}/skill", media_type=MediaType.JSON)
async def update_skill(domain_name: str, data: dict) -> dict:
    """更新 SKILL.md 内容."""
    skill_path = CONFIG_DIR / domain_name / "SKILL.md"
    content = data.get("content", "")
    if not content:
        return {"status": "error", "message": "内容不能为空"}
    skill_path.write_text(content, encoding="utf-8")
    return {"status": "ok", "message": "SKILL.md 已保存"}


@get("/api/domains/{domain_name:str}/data")
async def get_domain_data(domain_name: str) -> dict:
    """获取领域数据（订阅、黑名单、复盘）. """
    return {
        "subscriptions": data_mgr.load_subscriptions(domain_name),
        "blacklist": data_mgr.load_blacklist(domain_name),
        "reviews": data_mgr.list_review_reports(domain_name),
    }


@get("/api/domains/{domain_name:str}/review/{filename:str}")
async def get_review_content(domain_name: str, filename: str) -> dict:
    """获取复盘报告全文."""
    review_path = data_mgr._root / domain_name / "review" / filename
    if not review_path.exists():
        return {"status": "error", "message": "Report not found"}
    return {"status": "ok", "content": review_path.read_text(encoding="utf-8")}


@get("/api/domains/{domain_name:str}/skills")
async def list_skills(domain_name: str) -> dict:
    """获取该领域关联的所有 skills."""
    skills = []
    # 1. 领域自己的文件
    domain_path = CONFIG_DIR / domain_name
    if domain_path.exists():
        for f in sorted(domain_path.iterdir()):
            if f.is_file():
                skills.append({
                    "name": f.name,
                    "path": str(f),
                    "type": "domain",
                })
    # 2. 项目级 skills（可被任何领域引用）
    if SKILLS_DIR.exists():
        for f in sorted(SKILLS_DIR.iterdir()):
            if f.is_dir():
                skill_md = f / "SKILL.md"
                skill_info = {"name": f.name, "path": str(f), "type": "project"}
                if skill_md.exists():
                    skill_info["content"] = skill_md.read_text(encoding="utf-8")
                skills.append(skill_info)
    return {"skills": skills}


@get("/api/files/{filepath:path}")
async def get_file_content(filepath: str) -> dict:
    """读取任意文件内容."""
    project_root = Path(__file__).resolve().parent.parent.parent
    # Support both absolute paths and relative paths
    path = Path(filepath)
    if not path.is_absolute():
        path = project_root / filepath
    if not path.exists() or not path.is_file():
        return {"status": "error", "message": f"File not found: {path}"}
    try:
        return {"status": "ok", "content": path.read_text(encoding="utf-8")}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── 订阅管理 ─────────────────────────────────────────────

import json
from datetime import datetime


@get("/api/domains/{domain_name:str}/subscriptions")
async def get_subscriptions_api(domain_name: str) -> dict:
    """获取订阅作者列表 (JSON API)."""
    subs = data_mgr.load_subscriptions(domain_name)
    return {"subscriptions": subs}


@post("/api/domains/{domain_name:str}/subscribe", media_type=MediaType.JSON)
async def subscribe_author(domain_name: str, data: dict) -> dict:
    """订阅一个作者."""
    author_name = data.get("name", "").strip()
    platform = data.get("platform", "").strip()
    author_url = data.get("url", "").strip()
    author_id = data.get("author_id", "").strip()

    if not author_name or not platform:
        return {"status": "error", "message": "作者名和平台不能为空"}

    # 检查是否已订阅
    existing = data_mgr.load_subscriptions(domain_name)
    for sub in existing:
        sa = sub.get("author", {})
        if sa.get("name") == author_name and sa.get("platform") == platform:
            if sub.get("is_blacklisted"):
                # 如果之前在黑名单但已取消，移除黑名单
                data_mgr.unblacklist_author(domain_name, author_name)
            return {"status": "existed", "message": "已订阅该作者"}

    new_sub = {
        "id": f"sub_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "author": {
            "name": author_name,
            "platform": platform,
            "url": author_url,
            "author_id": author_id or None,
        },
        "subscribed_at": datetime.now().isoformat(),
        "score": 0.5,
        "score_history": [],
        "total_analyses": 0,
        "last_monitored_at": None,
        "is_blacklisted": False,
        "tags": [],
        "notes": "",
    }
    existing.append(new_sub)
    data_mgr.save_subscriptions(domain_name, existing)
    log.log("INFO", "web.domains", "author_subscribed",
            f"Author '{author_name}' ({platform}) subscribed to domain '{domain_name}'")
    return {"status": "ok", "message": f"已关注 {author_name}"}


@post("/api/domains/{domain_name:str}/unsubscribe", media_type=MediaType.JSON)
async def unsubscribe_author(domain_name: str, data: dict) -> dict:
    """取消关注一个作者."""
    author_name = data.get("name", "").strip()
    platform = data.get("platform", "").strip()

    if not author_name or not platform:
        return {"status": "error", "message": "作者名和平台不能为空"}

    existing = data_mgr.load_subscriptions(domain_name)
    updated = False
    new_list = []
    for sub in existing:
        sa = sub.get("author", {})
        if sa.get("name") == author_name and sa.get("platform") == platform:
            updated = True
        else:
            new_list.append(sub)

    if updated:
        data_mgr.save_subscriptions(domain_name, new_list)
        data_mgr.unblacklist_author(domain_name, author_name)
        log.log("INFO", "web.domains", "author_unsubscribed",
                f"Author '{author_name}' ({platform}) unsubscribed from domain '{domain_name}'")
        return {"status": "ok", "message": f"已取消关注 {author_name}"}
    else:
        return {"status": "error", "message": "未找到该作者"}


@post("/api/domains/{domain_name:str}/toggle_blacklist", media_type=MediaType.JSON)
async def toggle_blacklist(domain_name: str, data: dict) -> dict:
    """切换作者黑名单状态."""
    author_name = data.get("name", "").strip()
    platform = data.get("platform", "").strip()
    action = data.get("action", "")  # "blacklist" or "unblacklist"

    if not author_name:
        return {"status": "error", "message": "作者名不能为空"}

    existing = data_mgr.load_subscriptions(domain_name)
    updated = False
    new_list = []

    for sub in existing:
        sa = sub.get("author", {})
        if sa.get("name") == author_name and sa.get("platform") == platform:
            if action == "blacklist":
                sub["is_blacklisted"] = True
                sub["blacklist_reason"] = data.get("reason", "手动拉黑")
                sub["blacklisted_at"] = datetime.now().isoformat()
                log.log("WARNING", "web.domains", "author_blacklisted",
                        f"Author '{author_name}' blacklisted in domain '{domain_name}'")
            else:
                sub["is_blacklisted"] = False
                sub.pop("blacklist_reason", None)
                sub.pop("blacklisted_at", None)
                log.log("INFO", "web.domains", "author_unblacklisted",
                        f"Author '{author_name}' removed from blacklist in domain '{domain_name}'")
            updated = True
            break

    if updated:
        data_mgr.save_subscriptions(domain_name, existing)
        return {"status": "ok", "message": "已更新"}
    else:
        return {"status": "error", "message": "未找到该作者"}