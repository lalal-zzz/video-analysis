"""Models for fixed-creator monitoring and research workflows."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FixedCreator(BaseModel):
    """A creator tracked by a research watchlist."""

    name: str
    platform: str
    url: str
    author_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class CreatorWatchlist(BaseModel):
    """A stable set of creators used for repeated research runs."""

    name: str
    description: str = ""
    enabled: bool = True
    creators: list[FixedCreator] = Field(default_factory=list)
    analysis_skill: str = "creator-research"
    max_videos_per_creator: int = 5
    updated_at: datetime = Field(default_factory=datetime.now)
