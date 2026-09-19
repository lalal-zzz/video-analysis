from datetime import datetime
from pydantic import BaseModel, HttpUrl


class VideoStats(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    favorites: int = 0
    shares: int = 0


class VideoMetadata(BaseModel):
    platform: str
    video_id: str
    title: str
    author: str
    author_url: str | None = None
    publish_time: datetime | None = None
    duration: float | None = None
    url: str
    thumbnail_url: str | None = None
    stats: VideoStats = VideoStats()
    tags: list[str] = []
    description: str = ""