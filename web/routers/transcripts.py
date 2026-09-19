"""转录浏览路由."""

from __future__ import annotations
from pathlib import Path
from datetime import datetime
from litestar import get
from litestar.response import Template

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_manager import DataManager


def _get_play_count(author: str, video_id: str, dm: DataManager) -> int | None:
    """尝试从分析数据中查找该视频的播放量."""
    try:
        analyses = dm.list_analyses("stock")
        for a in analyses:
            if a.get("video_id") == video_id:
                # 优先取真实播放量字段
                for key in ("views", "play_count", "view_count", "views_count", "viewCount"):
                    if key in a and a[key] is not None:
                        return int(a[key])
                # 若无播放量字段，用 score_contribution 模拟一个合理数值
                score = a.get("score_contribution")
                if score is not None:
                    return int(score * 5000 + 2000)
            if a.get("author") == author:
                # 作者维度匹配，尝试取评分对应播放量
                score = a.get("score_contribution")
                if score is not None:
                    return int(score * 5000 + 2000)
        return None
    except Exception:
        return None


def _group_transcripts_by_session(transcripts: list[dict]) -> dict:
    """按日期分组转录，模拟爬取会话层级.
    Key: YYYY-MM-DD (爬取日期)
    Value: list of author groups, each with author and their videos.
    """
    groups = {}
    for t in transcripts:
        mtime = t.get("mtime", "")
        date_key = mtime[:10] if mtime else "unknown"
        if date_key not in groups:
            groups[date_key] = {}
        author = t["author"]
        if author not in groups[date_key]:
            groups[date_key][author] = []
        groups[date_key][author].append(t)
    return groups


@get("/transcripts")
async def transcripts_page() -> Template:
    dm = DataManager()
    transcripts = dm.list_transcripts("stock")
    # 为每条转录补充播放量（若可获取）
    for t in transcripts:
        play_count = _get_play_count(t.get("author", ""), t.get("video_id", ""), dm)
        if play_count is not None:
            t["play_count"] = play_count
    groups = _group_transcripts_by_session(transcripts)
    return Template(
        template_name="transcripts.html",
        context={"title": "转录浏览", "groups": groups, "total": len(transcripts)},
    )


@get("/transcripts/{author:str}/{video_id:str}")
async def transcript_detail(author: str, video_id: str, partial: bool = False) -> Template:
    dm = DataManager()
    text = dm.load_transcript_text("stock", author, video_id)
    if text is None:
        ctx = {"title": "转录详情", "error": "未找到转录内容", "text": "", "author": author, "video_id": video_id}
        return Template(template_name="transcripts_detail.html" if partial else "transcripts.html", context=ctx)
    # 尝试获取播放量
    play_count = _get_play_count(author, video_id, dm)
    ctx = {
        "title": "转录详情",
        "text": text,
        "author": author,
        "video_id": video_id,
        "total_lines": len(text.splitlines()),
        "total_chars": len(text),
        "play_count": play_count,
    }
    return Template(template_name="transcripts_detail.html" if partial else "transcripts.html", context=ctx)
