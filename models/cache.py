from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CacheEntry(BaseModel):
    key: str
    value: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


class CacheStatus(BaseModel):
    video_hits: int = 0
    video_misses: int = 0
    query_hits: int = 0
    query_misses: int = 0
    total_entries: int = 0