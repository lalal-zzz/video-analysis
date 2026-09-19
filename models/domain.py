"""领域配置、订阅、黑名单数据模型."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DiscoveryQuery(BaseModel):
    """一组搜索 query，用于发现新作者/视频."""

    platform: str
    keywords: list[str]
    sort: str = "views"
    max_results: int = 20
    date_range: tuple[str | None, str | None] = (None, None)


class MonitorConfig(BaseModel):
    """监控配置."""

    max_videos_per_author: int = 3
    transcription_method: str = "whisper"


class DiscoveryConfig(BaseModel):
    """发现配置."""

    author_search: list[DiscoveryQuery] = Field(default_factory=list)
    video_search: list[DiscoveryQuery] = Field(default_factory=list)


class ReviewConfig(BaseModel):
    """复盘配置."""

    interval_days: int = 7
    blacklist_threshold: float = -0.6


class DomainConfig(BaseModel):
    """一个领域的完整配置."""

    name: str
    description: str = ""
    enabled: bool = True
    skill: str = "video-analyst"
    review_skill: str = ""
    analysis_skill: str = "video-analyst"
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    review_prompt_template: str = ""
    blacklist_threshold: float = -0.6


class AuthorInfo(BaseModel):
    """被关注的作者."""

    name: str
    platform: str
    url: str
    author_id: str | None = None

    @property
    def slug(self) -> str:
        """安全文件名."""
        slug = self.name.replace(" ", "_")
        slug = "".join(c if c.isalnum() or c in "_-" else "_" for c in slug)
        return slug[:50]


class Subscription(BaseModel):
    """订阅记录."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    domain: str
    author: AuthorInfo
    subscribed_at: datetime = Field(default_factory=datetime.now)
    score: float = 0.0
    next_review_at: datetime | None = None
    review_interval_days: int = 7
    total_analyses: int = 0
    last_monitored_at: datetime | None = None
    is_blacklisted: bool = False
    blacklist_reason: str | None = None
    tags: list[str] = []
    notes: str = ""


class BlacklistEntry(BaseModel):
    """黑名单记录."""

    author: AuthorInfo
    domain: str
    reason: str = ""
    blacklisted_at: datetime = Field(default_factory=datetime.now)


class ToolCallRecord(BaseModel):
    """工具调用记录."""

    tool_name: str
    kwargs: dict[str, Any]
    result: Any
    executed_at: datetime = Field(default_factory=datetime.now)
