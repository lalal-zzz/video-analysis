"""WebSocket 进度推送路由."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from litestar import WebSocket, get, post, websocket
from litestar.response import Template
from starlette.websockets import WebSocketDisconnect

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.utils.progress import progress_manager, TaskStatus

logger = logging.getLogger(__name__)

_ws_clients: set[WebSocket] = set()
_ws_lock = asyncio.Lock()


@get("/progress/docs")
async def ws_docs() -> dict:
    """WebSocket 使用说明."""
    return {
        "status": "websocket",
        "message": "WebSocket 端点运行于 /ws",
        "docs": "client.connect('ws://host/ws')",
        "endpoints": {
            "ws_connect": "/ws (WebSocket)",
            "list_tasks": "/ws/tasks (GET)",
            "task_detail": "/ws/tasks/{task_id} (GET)",
            "cancel_task": "/ws/cancel/{task_id} (POST)",
        },
        "client_protocol": [
            "ping → pong",
            "subscribe {task_id} → task_update",
            "cancel {task_id} → cancelled",
            "list → task_list",
        ],
    }


@post("/ws/cancel/{task_id:str}")
async def cancel_task(task_id: str) -> dict:
    """取消正在执行的任务."""
    success = progress_manager.cancel(task_id)
    return {"cancelled": success, "task_id": task_id}


@get("/ws/tasks")
async def list_tasks() -> dict:
    """列出所有任务."""
    return {"tasks": progress_manager.list_tasks()}


@get("/ws/tasks/{task_id:str}")
async def get_task(task_id: str) -> dict:
    """获取单个任务详情."""
    task = progress_manager.get(task_id)
    if not task:
        return {"error": "Task not found"}
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "domain": task.domain,
        "author": task.author,
        "status": task.status.value,
        "progress": task.progress,
        "current_step": task.current_step,
        "message": task.message,
        "error": task.error,
        "result": task.result,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


@websocket("/ws")
async def ws_progress(socket: WebSocket) -> None:
    """WebSocket 端点 — 接收连接，推送任务进度."""
    async with _ws_lock:
        _ws_clients.add(socket)

    try:
        await socket.accept()
        logger.info(f"[WS] Client connected. Total clients: {len(_ws_clients)}")

        # 发送当前所有活跃任务
        active_tasks = [
            {
                "task_id": t.task_id,
                "status": t.status.value,
                "progress": t.progress,
                "step": t.current_step,
                "message": t.message,
            }
            for t in progress_manager.tasks.values()
            if t.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]
        if active_tasks:
            await socket.send_json({"type": "active_tasks", "tasks": active_tasks})

        # 监听客户端消息
        while True:
            data = await socket.receive_text()

            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    await socket.send_json({"type": "pong"})

                elif msg_type == "subscribe":
                    task_id = msg.get("task_id", "")
                    if task_id:
                        task = progress_manager.get(task_id)
                        if task:
                            await socket.send_json({
                                "type": "task_update",
                                "task_id": task.task_id,
                                "status": task.status.value,
                                "progress": task.progress,
                                "step": task.current_step,
                                "message": task.message,
                            })

                elif msg_type == "cancel":
                    task_id = msg.get("task_id", "")
                    success = progress_manager.cancel(task_id)
                    await socket.send_json({
                        "type": "cancelled",
                        "task_id": task_id,
                        "success": success,
                    })

                elif msg_type == "list":
                    tasks = progress_manager.list_tasks()
                    await socket.send_json({"type": "task_list", "tasks": tasks})

            except json.JSONDecodeError:
                await socket.send_text(f"Unknown message: {data}")

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected (normal)")
    except Exception as e:
        logger.warning(f"[WS] Client disconnected: {e}")
    finally:
        async with _ws_lock:
            _ws_clients.discard(socket)
        logger.info(f"[WS] Client disconnected. Total clients: {len(_ws_clients)}")
