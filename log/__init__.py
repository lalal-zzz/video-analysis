from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Iterator

from log import database

_pipeline: ContextVar[str | None] = ContextVar("_pipeline", default=None)
_pipeline_id: ContextVar[str | None] = ContextVar("_pipeline_id", default=None)


def new_pipeline_id() -> str:
    pid = str(uuid.uuid4())[:8]
    _pipeline_id.set(pid)
    return pid


def get_pipeline_id() -> str | None:
    return _pipeline_id.get()


def current_pipeline() -> str:
    return _pipeline.get() or "system"


@contextmanager
def pipeline_context(name: str) -> Iterator[str]:
    pid = new_pipeline_id()
    prev_pipeline = _pipeline.get()
    prev_pid = _pipeline_id.get()
    _pipeline.set(name)
    _pipeline_id.set(pid)
    try:
        database.append_event(
            level="INFO", module="pipeline", event=f"{name}_start",
            message=f"Pipeline {name} started", pipeline=name, pipeline_id=pid,
        )
        yield pid
    except BaseException as exc:
        database.append_event(
            level="ERROR", module="pipeline", event=f"{name}_error",
            message=f"Pipeline {name} failed: {exc}", pipeline=name,
            pipeline_id=pid, error=str(exc),
        )
        raise
    finally:
        if prev_pid:
            _pipeline.set(prev_pipeline)
            _pipeline_id.set(prev_pid)
        else:
            _pipeline.set(None)
            _pipeline_id.set(None)


@contextmanager
def timed_operation(level: str, module: str, event: str, message: str = "",
                    detail: dict[str, Any] | None = None) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    except BaseException as exc:
        dt = (time.perf_counter() - t0) * 1000
        database.append_event(
            level="ERROR", module=module, event=f"{event}_error",
            message=str(exc), pipeline=current_pipeline(),
            pipeline_id=get_pipeline_id(), error=str(exc), duration_ms=round(dt, 1),
        )
        raise
    else:
        dt = (time.perf_counter() - t0) * 1000
        database.append_event(
            level=level, module=module, event=event, message=message,
            pipeline=current_pipeline(), pipeline_id=get_pipeline_id(),
            detail=detail, duration_ms=round(dt, 1),
        )


def log(level: str, module: str, event: str, message: str = "",
        detail: dict[str, Any] | None = None, error: str | None = None) -> None:
    database.append_event(
        level=level, module=module, event=event, message=message,
        pipeline=current_pipeline(), pipeline_id=get_pipeline_id(),
        detail=detail, error=error,
    )