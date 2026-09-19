"""进度管理器 — 跟踪后台任务的实时进度."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressTask:
    """单个后台任务的进度信息."""
    task_id: str
    task_type: str  # monitor, discover, review, search
    domain: str
    author: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0  # 0-100
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    message: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    cancelled: bool = False


class ProgressManager:
    """全局进度管理器 — 单例模式，WebSocket 推送用."""

    _instance: ProgressManager | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # type: ignore

    def __new__(cls) -> ProgressManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tasks: dict[str, ProgressTask] = {}
            cls._instance._subscribers: dict[str, set[Callable]] = defaultdict(set)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._tasks = {}  # type: ignore
            self._subscribers = defaultdict(set)  # type: ignore
            self._initialized = True

    @property
    def tasks(self) -> dict[str, ProgressTask]:
        return self._tasks

    def create_task(
        self,
        task_type: str,
        domain: str,
        author: str = "",
        total_steps: int = 0,
    ) -> str:
        """创建新任务，返回 task_id."""
        task_id = uuid.uuid4().hex[:12]
        task = ProgressTask(
            task_id=task_id,
            task_type=task_type,
            domain=domain,
            author=author,
            total_steps=total_steps,
            status=TaskStatus.PENDING,
            current_step=f"准备{task_type}任务...",
        )
        self._tasks[task_id] = task
        logger.info(f"[Progress] Created task: {task_id} ({task_type}/{domain}/{author})")
        return task_id

    def update(
        self,
        task_id: str,
        progress: int | None = None,
        step: str | None = None,
        message: str | None = None,
        status: TaskStatus | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> ProgressTask | None:
        """更新任务进度."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        if progress is not None:
            task.progress = max(0, min(100, progress))
        if step is not None:
            task.current_step = step
            task.completed_steps += 1
        if message is not None:
            task.message = message
        if status is not None:
            task.status = status
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error

        task.updated_at = datetime.now().isoformat()
        self._broadcast(task_id)
        return task

    def get(self, task_id: str) -> ProgressTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict]:
        """返回所有任务的摘要信息."""
        return [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "domain": t.domain,
                "author": t.author,
                "status": t.status.value,
                "progress": t.progress,
                "current_step": t.current_step,
                "message": t.message,
                "updated_at": t.updated_at,
            }
            for t in self._tasks.values()
        ]

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task:
            task.cancelled = True
            task.status = TaskStatus.CANCELLED
            task.current_step = "已取消"
            task.updated_at = datetime.now().isoformat()
            self._broadcast(task_id)
            return True
        return False

    def _broadcast(self, task_id: str) -> None:
        """通知所有监听该任务的客户端."""
        task = self._tasks.get(task_id)
        if not task:
            return

        payload = {
            "task_id": task.task_id,
            "status": task.status.value,
            "progress": task.progress,
            "step": task.current_step,
            "message": task.message,
            "error": task.error,
            "result": task.result,
        }

        for callback in self._subscribers.get(task_id, set()):
            try:
                asyncio.create_task(self._safe_callback(callback, payload))
            except Exception:
                pass

    async def _safe_callback(self, callback: Callable, payload: dict) -> None:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(payload)
            else:
                callback(payload)
        except Exception:
            pass

    def register_callback(self, task_id: str, callback: Callable) -> None:
        """注册回调（别名，与 subscribe 等价）."""
        self._subscribers[task_id].add(callback)

    def subscribe(self, task_id: str, callback: Callable) -> None:
        """订阅任务进度更新."""
        self._subscribers[task_id].add(callback)

    def unregister_callback(self, task_id: str, callback: Callable) -> None:
        self._subscribers[task_id].discard(callback)

    def cleanup(self, max_age_hours: int = 24) -> int:
        """清理过期任务，返回清理数量."""
        cutoff = datetime.now().timestamp() - max_age_hours * 3600
        to_remove = []
        for task_id, task in self._tasks.items():
            try:
                ts = datetime.fromisoformat(task.updated_at).timestamp()
                if ts < cutoff and task.status in (
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ):
                    to_remove.append(task_id)
            except (ValueError, TypeError):
                pass

        for tid in to_remove:
            del self._tasks[tid]
            self._subscribers.pop(tid, None)

        return len(to_remove)


# 全局单例
progress_manager = ProgressManager()
