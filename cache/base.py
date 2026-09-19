from abc import ABC, abstractmethod

from models.search import SearchQuery, SearchResult
from models.transcript import VideoTranscript


class BaseCache(ABC):
    @abstractmethod
    async def get_video(self, platform: str, video_id: str) -> VideoTranscript | None:
        ...

    @abstractmethod
    async def set_video(self, transcript: VideoTranscript) -> None:
        ...

    @abstractmethod
    async def get_query(self, query: SearchQuery) -> SearchResult | None:
        ...

    @abstractmethod
    async def set_query(self, result: SearchResult) -> None:
        ...