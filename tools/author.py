"""获取视频对应博主信息 — 根据视频 ID/URL 返回博主详细资料。"""

from __future__ import annotations

import logging
from typing import Any

from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@ToolRegistry.register("get_video_author")
def get_video_author(platform: str, video_id: str) -> dict[str, Any]:
    """根据视频 ID 获取博主信息。

    Args:
        platform: 平台名称 ("youtube" | "bilibili" | "douyin")
        video_id: 视频 ID

    Returns:
        dict with keys: author, author_id, author_url, avatar, subscribers,
                        video_title, video_url, platform, description, views, likes
    """
    try:
        if platform == "youtube":
            return _get_youtube_author(video_id)
        elif platform == "bilibili":
            return _get_bilibili_author(video_id)
        elif platform == "douyin":
            return _get_douyin_author(video_id)
        else:
            return {"error": f"Unsupported platform: {platform}"}
    except Exception as e:
        logger.error(f"get_video_author failed: {e}")
        return {"error": str(e)}


def _get_youtube_author(video_id: str) -> dict[str, Any]:
    """使用 yt_dlp 获取作者信息（同步方式，无需事件循环）。"""
    import yt_dlp
    with yt_dlp.YoutubeDL({
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,  # 获取完整信息
    }) as ydl:
        try:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
        except Exception as e:
            return {"error": f"YouTube author fetch failed: {e}"}

    return {
        "author": info.get("channel", info.get("uploader", "")),
        "author_id": info.get("channel_id", ""),
        "author_url": info.get("channel_url", ""),
        "avatar": info.get("channel_thumbnail", ""),
        "subscribers": info.get("channel_follower_count", 0),
        "video_title": info.get("title", ""),
        "video_url": info.get("webpage_url", f"https://www.youtube.com/watch?v={video_id}"),
        "platform": "youtube",
        "description": info.get("description", ""),
        "views": info.get("view_count", 0),
        "likes": info.get("like_count", 0),
    }


def _get_bilibili_author(video_id: str) -> dict[str, Any]:
    """从 Bilibili 视频获取作者信息。"""
    import httpx
    try:
        with httpx.Client(headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }, timeout=30.0) as client:
            resp = client.get(
                f"https://api.bilibili.com/x/web-interface/view?bvid={video_id}"
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            return {"error": f"Bilibili API error: {data.get('message', 'unknown')}"}

        video_data = data["data"]
        owner = video_data.get("owner", {})
        stat = video_data.get("stat", {})

        return {
            "author": owner.get("name", ""),
            "author_id": str(owner.get("mid", "")),
            "author_url": f"https://space.bilibili.com/{owner.get('mid', '')}",
            "avatar": owner.get("face", ""),
            "subscribers": stat.get("follower", 0),
            "video_title": video_data.get("title", ""),
            "video_url": f"https://www.bilibili.com/video/{video_id}",
            "platform": "bilibili",
            "description": video_data.get("desc", ""),
            "views": stat.get("view", 0),
            "likes": stat.get("like", 0),
        }
    except Exception as e:
        return {"error": f"Bilibili author fetch failed: {e}"}


def _get_douyin_author(video_id: str) -> dict[str, Any]:
    """从抖音视频获取作者信息。"""
    import httpx
    try:
        with httpx.Client(headers={
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; SM-S9080) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/112.0.0.0 Mobile Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        }, timeout=30.0) as client:
            resp = client.get(
                "https://www.douyin.com/aweme/v1/web/aweme/detail/",
                params={"aweme_id": video_id},
            )
            resp.raise_for_status()
            data = resp.json()

        aweme_detail = data.get("aweme_detail", {})
        if not aweme_detail:
            return {"error": "Video not found"}

        author_info = aweme_detail.get("author", {}) or {}
        stat = aweme_detail.get("statistics", {}) or {}

        return {
            "author": author_info.get("nickname", ""),
            "author_id": str(author_info.get("uid", "")),
            "author_url": f"https://www.douyin.com/user/{author_info.get('sec_uid', '')}",
            "avatar": (author_info.get("avatar_larger", {}) or {}).get("url_list", [""])[0] if author_info.get("avatar_larger") else "",
            "subscribers": author_info.get("follower_count", 0),
            "video_title": aweme_detail.get("desc", ""),
            "video_url": f"https://www.douyin.com/video/{video_id}",
            "platform": "douyin",
            "views": stat.get("play_count", 0),
            "likes": stat.get("digg_count", 0),
        }
    except Exception as e:
        return {"error": f"Douyin author fetch failed: {e}"}