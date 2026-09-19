"""爬虫包装 — 将现有 scrapers 注册为工具，供 LLM 按需调用."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

from tools.registry import ToolRegistry
from scrapers import BilibiliScraper, YouTubeScraper, DouyinScraper


def _run_async(coro):
    """从同步上下文安全运行协程，避免嵌套事件循环."""
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


class ScraperPool:
    """Scraper 实例池，避免重复创建."""

    _instances: dict[str, Any] = {}

    @classmethod
    def get(cls, platform: str):
        if platform not in cls._instances:
            if platform == "bilibili":
                cls._instances[platform] = BilibiliScraper()
            elif platform == "youtube":
                cls._instances[platform] = YouTubeScraper()
            elif platform == "douyin":
                cls._instances[platform] = DouyinScraper()
            else:
                raise ValueError(f"Unsupported platform: {platform}")
        return cls._instances[platform]


@ToolRegistry.register("search_videos")
def search_videos(platform: str, keywords: str, max_results: int = 20) -> list[dict]:
    """搜索视频。platform: 平台, keywords: 关键词（逗号分隔）, max_results: 最大结果数."""
    from models import SearchQuery, SearchResult

    kw_list = [k.strip() for k in keywords.split(",")]
    kw = kw_list[0] if kw_list else keywords

    def _run() -> list[dict]:
        scraper = ScraperPool.get(platform)
        query = SearchQuery(keywords=kw, platform=platform, max_results=max_results)
        result: SearchResult = _run_async(scraper.fetch_videos(query))
        return [
            {
                "video_id": v.video_id,
                "title": v.title,
                "author": v.author,
                "url": v.url,
                "publish_time": v.publish_time.isoformat() if v.publish_time else "",
                "views": v.stats.views,
            }
            for v in result.videos[:max_results]
        ]

    try:
        return _run()
    except Exception as e:
        return [{"error": str(e)}]


@ToolRegistry.register("search_authors")
def search_authors(platform: str, keywords: str, max_results: int = 20) -> list[dict]:
    """搜索作者。返回 unique authors from video results."""
    videos = search_videos(platform, keywords, max_results)
    seen = set()
    authors = []
    for v in videos:
        author = v.get("author", "")
        if author and author not in seen:
            seen.add(author)
            authors.append({"name": author, "platform": platform, "video_count": 1})
        elif author:
            for a in authors:
                if a["name"] == author:
                    a["video_count"] = a.get("video_count", 0) + 1
    return authors


@ToolRegistry.register("get_author_latest_videos")
def get_author_latest_videos(platform: str, author: str, since: str = "", max_n: int = 5) -> list[dict]:
    """获取作者最新视频."""
    from models import SearchQuery

    def _run() -> list[dict]:
        scraper = ScraperPool.get(platform)
        result = _run_async(scraper.fetch_author_videos(author))
        videos = result.videos[:max_n] if hasattr(result, "videos") else []
        return [
            {
                "video_id": v.video_id,
                "title": v.title,
                "url": v.url,
                "publish_time": v.publish_time.isoformat() if v.publish_time else "",
                "views": v.stats.views,
            }
            for v in videos
        ]

    try:
        return _run()
    except Exception as e:
        return [{"error": str(e)}]


@ToolRegistry.register("transcribe_video")
def transcribe_video(platform: str, video_url: str, video_title: str = "") -> dict:
    """转录视频。返回 full_text 和 metadata."""
    from transcribers import SubtitleParser, WhisperClient

    try:
        if platform == "youtube":
            from models.video import VideoMetadata
            vm = VideoMetadata(
                platform="youtube",
                video_id="dummy",
                title=video_title or "unknown",
                author="unknown",
                url=video_url,
            )
            tp = SubtitleParser()
            transcript = _run_async(tp.get_transcript(vm))
        else:
            vm = VideoMetadata(
                platform=platform,
                video_id="dummy",
                title=video_title or "unknown",
                author="unknown",
                url=video_url,
            )
            wc = WhisperClient()
            transcript = _run_async(wc.get_transcript(vm))

        return {
            "success": True,
            "full_text": transcript.full_text if transcript else "",
            "source": transcript.source if transcript else "unknown",
            "length": len(transcript.full_text) if transcript and transcript.full_text else 0,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}