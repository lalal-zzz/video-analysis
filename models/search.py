from datetime import datetime

from pydantic import BaseModel, Field

from .video import VideoMetadata


class SearchQuery(BaseModel):
    keywords: str = ""
    platform: str = ""  # "bilibili" | "youtube" | "douyin" | ""
    sort: str = "relevance"  # "relevance" | "publish_time" | "views"
    max_results: int = 20
    author: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    def cache_key(self) -> str:
        parts = [
            self.platform,
            self.keywords,
            self.sort,
            str(self.max_results),
            self.author or "",
            str(self.date_from),
            str(self.date_to),
        ]
        return "|".join(parts)


class SearchResult(BaseModel):
    query: SearchQuery
    videos: list[VideoMetadata] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.now)
    total_available: int = 0