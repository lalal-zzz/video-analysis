"""后台任务运行器 — 委托真正的引擎，推送实时进度."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import MonitorEngine, DiscoverEngine, ReviewEngine
from web.utils.progress import progress_manager, TaskStatus
import log

logger = logging.getLogger(__name__)

_monitor_engine = MonitorEngine()
_discover_engine = DiscoverEngine()
_review_engine = ReviewEngine()


def _make_progress_callback(task_id: str):
    """创建一个 progress_callback 闭包，更新 progress_manager."""
    def cb(percent: int, step: str, message: str, *_args: Any, **_kwargs: Any) -> None:
        progress_manager.update(
            task_id,
            progress=percent,
            step=step,
            message=message,
        )
    return cb


async def run_monitor(domain: str) -> dict:
    """异步执行监控任务 — 委托 MonitorEngine + 进度推送."""
    task_id = progress_manager.create_task("monitor", domain)
    progress_manager.update(task_id, status=TaskStatus.RUNNING, step="开始", message="正在启动监控...")
    log.log("INFO", "web.task_runner", "monitor_start",
            f"Monitor task started for domain '{domain}'", detail={"domain": domain, "task_id": task_id})

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _monitor_engine.run(domain, progress_callback=_make_progress_callback(task_id)),
        )

        progress_manager.update(
            task_id,
            progress=100,
            status=TaskStatus.COMPLETED,
            step="完成",
            message=f"监控完成: {result.get('monitored', 0)} 视频, {result.get('errors', 0)} 错误",
            result=result,
        )
        log.log("INFO", "web.task_runner", "monitor_complete",
                f"Monitor completed: {result.get('monitored')} videos, {result.get('errors')} errors",
                detail={"domain": domain, "task_id": task_id, "result": result})
        return {"task_id": task_id, **result}

    except Exception as e:
        logger.error(f"Monitor failed for '{domain}': {e}")
        log.log("ERROR", "web.task_runner", "monitor_error",
                f"Monitor failed for '{domain}': {e}", detail={"domain": domain}, error=str(e))
        progress_manager.update(
            task_id,
            status=TaskStatus.FAILED,
            step="失败",
            error=str(e),
            message=f"监控失败: {e}",
        )
        return {"task_id": task_id, "status": "error", "error": str(e)}


async def run_discover(domain: str) -> dict:
    """异步执行发现任务 — 委托 DiscoverEngine + 进度推送."""
    task_id = progress_manager.create_task("discover", domain)
    progress_manager.update(task_id, status=TaskStatus.RUNNING, step="开始", message="正在启动发现...")
    log.log("INFO", "web.task_runner", "discover_start",
            f"Discover task started for domain '{domain}'", detail={"domain": domain, "task_id": task_id})

    try:
        loop = asyncio.get_running_loop()
        candidates = await loop.run_in_executor(
            None,
            lambda: _discover_engine.run(domain, progress_callback=_make_progress_callback(task_id)),
        )

        result = {
            "task_id": task_id,
            "status": "ok",
            "candidates": candidates[:50],
            "total_found": len(candidates),
        }

        progress_manager.update(
            task_id,
            progress=100,
            status=TaskStatus.COMPLETED,
            step="完成",
            message=f"发现 {len(candidates)} 位候选作者",
            result=result,
        )
        log.log("INFO", "web.task_runner", "discover_complete",
                f"Discover completed: {len(candidates)} candidates",
                detail={"domain": domain, "task_id": task_id, "candidates": len(candidates)})
        return result

    except Exception as e:
        logger.error(f"Discover failed for '{domain}': {e}")
        log.log("ERROR", "web.task_runner", "discover_error",
                f"Discover failed for '{domain}': {e}", detail={"domain": domain}, error=str(e))
        progress_manager.update(
            task_id,
            status=TaskStatus.FAILED,
            step="失败",
            error=str(e),
            message=f"发现失败: {e}",
        )
        return {"task_id": task_id, "status": "error", "error": str(e)}


async def run_review(domain: str) -> dict:
    """异步执行复盘任务 — 委托 ReviewEngine + 进度推送."""
    task_id = progress_manager.create_task("review", domain)
    progress_manager.update(task_id, status=TaskStatus.RUNNING, step="开始", message="正在启动复盘...")
    log.log("INFO", "web.task_runner", "review_start",
            f"Review task started for domain '{domain}'", detail={"domain": domain, "task_id": task_id})

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _review_engine.run(domain),
        )

        progress_manager.update(
            task_id,
            progress=100,
            status=TaskStatus.COMPLETED,
            step="完成",
            message=f"复盘完成. 评分调整: {result.get('score_changes', 0)}, 新拉黑: {result.get('new_blacklists', 0)}",
            result=result,
        )
        log.log("INFO", "web.task_runner", "review_complete",
                f"Review completed for '{domain}'",
                detail={"domain": domain, "task_id": task_id, "result": result})
        return {"task_id": task_id, **result}

    except Exception as e:
        logger.error(f"Review failed for '{domain}': {e}")
        log.log("ERROR", "web.task_runner", "review_error",
                f"Review failed for '{domain}': {e}", detail={"domain": domain}, error=str(e))
        progress_manager.update(
            task_id,
            status=TaskStatus.FAILED,
            step="失败",
            error=str(e),
            message=f"复盘失败: {e}",
        )
        return {"task_id": task_id, "status": "error", "error": str(e)}