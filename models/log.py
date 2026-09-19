from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    level: str = "INFO"
    module: str = ""
    pipeline: str | None = None
    pipeline_id: str | None = None
    event: str = ""
    message: str = ""
    detail: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None