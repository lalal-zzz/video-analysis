from abc import ABC, abstractmethod

from models.search import SearchQuery, SearchResult
from models.rules import SelectorConfig
from models.video import VideoMetadata


class BaseScraper(ABC):
    platform: str = ""

    @abstractmethod
    async def fetch_videos(self, query: SearchQuery) -> SearchResult:
        ...

    @abstractmethod
    async def fetch_author_videos(self, author: str, max_results: int = 50) -> list[VideoMetadata]:
        ...

    @abstractmethod
    async def select(self, result: SearchResult, selector: SelectorConfig) -> list[VideoMetadata]:
        ...

    async def search_and_select(self, query: SearchQuery, selector: SelectorConfig) -> list[VideoMetadata]:
        result = await self.fetch_videos(query)
        return await self.select(result, selector)