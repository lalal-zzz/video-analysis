"""YouTube 爬虫 — 使用 yt_dlp 替代 YouTube Data API v3.

无需 API key，通过 yt_dlp 的网页爬取能力进行搜索。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from exceptions import ScraperError
from models.rules import SelectorConfig
from models.search import SearchQuery, SearchResult
from models.video import VideoMetadata, VideoStats
from scrapers.base import BaseScraper


class YouTubeScraper(BaseScraper):
    platform = "youtube"

    def __init__(self) -> None:
        self._ydl_opts: dict[str, Any] = {
            "quiet": True,
            "extract_flat": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "skip_download": True,
        }

    async def fetch_videos(self, query: SearchQuery) -> SearchResult:
        max_results = min(query.max_results, 50)
        search_terms = query.keywords

        # 如果指定了作者，使用 from: 语法缩小搜索范围
        if query.author:
            search_terms = f"from:{query.author} {search_terms}"

        def _search() -> list[dict[str, Any]]:
            import yt_dlp

            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                try:
                    result = ydl.extract_info(
                        f"ytsearch{max_results}:{search_terms}",
                        download=False,
                    )
                except Exception as e:
                    raise ScraperError(f"YouTube search failed: {e}") from e
                return result.get("entries", []) if result else []

        loop = asyncio.get_event_loop()
        try:
            entries = await loop.run_in_executor(None, _search)
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"YouTube search error: {e}") from e

        videos = []
        for entry in entries:
            if not entry or not entry.get("id"):
                continue

            video = self._entry_to_metadata(entry)

            # 日期过滤（yt_dlp 搜索不支持原生日期过滤，在 Python 层做）
            if query.date_from and video.publish_time and video.publish_time < query.date_from:
                continue
            if query.date_to and video.publish_time and video.publish_time > query.date_to:
                continue

            videos.append(video)

        # 排序（yt_dlp 默认按相关性排序，但我们可以覆盖）
        if query.sort == "publish_time":
            videos.sort(key=lambda v: v.publish_time or datetime.min, reverse=True)
        elif query.sort == "views":
            videos.sort(key=lambda v: v.stats.views or 0, reverse=True)
        # relevance 是 yt_dlp 默认排序，不需要额外处理

        return SearchResult(
            query=query,
            videos=videos,
            total_available=len(videos),
        )

    async def fetch_author_videos(
        self, author: str, max_results: int = 50
    ) -> list[VideoMetadata]:
        def _search_author() -> list[dict[str, Any]]:
            import yt_dlp

            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                try:
                    # 先尝试通过 from: 语法搜索该频道的视频
                    result = ydl.extract_info(
                        f"ytsearch{max_results}:from:{author}",
                        download=False,
                    )
                except Exception:
                    return []
                return result.get("entries", []) if result else []

        loop = asyncio.get_event_loop()
        try:
            entries = await loop.run_in_executor(None, _search_author)
        except Exception as e:
            raise ScraperError(f"YouTube author fetch failed: {e}") from e

        videos = []
        for entry in entries:
            if not entry or not entry.get("id"):
                continue
            videos.append(self._entry_to_metadata(entry))

        return videos[:max_results]

    async def select(
        self, result: SearchResult, selector: SelectorConfig
    ) -> list[VideoMetadata]:
        return selector.apply(result.videos)

    @staticmethod
    def _entry_to_metadata(entry: dict[str, Any]) -> VideoMetadata:
        """将 yt_dlp 搜索结果条目转换为 VideoMetadata。"""
        upload_date_str = entry.get("upload_date", "")
        publish_time = None
        if upload_date_str and len(upload_date_str) == 8:
            try:
                publish_time = datetime.strptime(upload_date_str, "%Y%m%d")
            except ValueError:
                pass

        return VideoMetadata(
            platform="youtube",
            video_id=entry.get("id", ""),
            title=entry.get("title", ""),
            author=entry.get("channel", "") or entry.get("uploader", ""),
            author_url=entry.get("channel_url", "")
            or f"https://www.youtube.com/channel/{entry.get('channel_id', '')}",
            url=entry.get("webpage_url", "")
            or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
            publish_time=publish_time,
            duration=entry.get("duration"),
            thumbnail_url=entry.get("thumbnail", ""),
            description=entry.get("description", ""),
            tags=entry.get("tags", []),
            stats=VideoStats(
                views=entry.get("view_count", 0),
                likes=entry.get("like_count", 0),
                comments=entry.get("comment_count", 0),
            ),
        )

    async def close(self) -> None:
        # yt_dlp 不需要特殊的关闭操作
        pass