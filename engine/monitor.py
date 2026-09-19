"""监控引擎 — 拉取已订阅作者的最新视频并分析."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Callable

from tools import ToolRegistry
from data_manager import DataManager
import log

logger = logging.getLogger(__name__)


class MonitorEngine:
    """监控引擎 — 遍历订阅，拉取新视频，转录并分析."""

    def __init__(self, skill: str = "video-analyst") -> None:
        self.dm = DataManager()
        self.skill = skill

    def run(self, domain: str, progress_callback: Callable | None = None) -> dict:
        """执行监控，返回统计信息。

        progress_callback(percent: int, step: str, message: str, author: str)
        """
        log.log("INFO", "engine.monitor", "monitor_start",
                f"Monitor start for domain '{domain}'", detail={"domain": domain})
        subs = self.dm.load_subscriptions(domain)
        if not subs:
            log.log("INFO", "engine.monitor", "no_subs",
                    f"No subscriptions for domain '{domain}'", detail={"domain": domain})
            if progress_callback:
                progress_callback(100, "完成", "没有订阅作者", "")
            return {"status": "ok", "monitored": 0, "skipped": 0, "errors": 0}

        active = [s for s in subs if not s.get("is_blacklisted", False)]
        if not active:
            log.log("INFO", "engine.monitor", "all_blacklisted",
                    f"All {len(subs)} subs blacklisted for '{domain}'", detail={"domain": domain, "total": len(subs)})
            if progress_callback:
                progress_callback(100, "完成", f"所有 {len(subs)} 个订阅均已拉黑", "")
            return {"status": "ok", "monitored": 0, "skipped": len(subs), "errors": 0}

        max_per_author = 3
        monitored = 0
        errors = 0
        now = datetime.now().isoformat()
        total_active = len(active)

        if progress_callback:
            progress_callback(0, "开始", f"有 {total_active} 位活跃作者", "")

        for i, sub in enumerate(active):
            author = sub["author"]
            platform = author.get("platform", "")
            author_name = author.get("name", "")

            if progress_callback:
                pct = int((i / total_active) * 100)
                progress_callback(pct, f"{author_name} ({i + 1}/{total_active})",
                                  f"正在拉取 {author_name} 的视频...", author_name)

            try:
                videos = ToolRegistry.call(
                    "get_author_latest_videos",
                    platform=platform,
                    author=author_name,
                    max_n=max_per_author,
                )

                if not videos or "error" in str(videos):
                    log.log("WARNING", "engine.monitor", "fetch_videos_failed",
                            f"Failed to fetch videos for {author_name}", detail={"author": author_name, "platform": platform})
                    continue

                video_count = 0
                for video in videos:
                    if "error" in video:
                        errors += 1
                        continue

                    video_count += 1
                    video_id = video.get("video_id", "")
                    title = video.get("title", "")
                    url = video.get("url", "")

                    if progress_callback:
                        progress_callback(pct, f"转录: {title[:30]}", f"正在转录 {title[:40]}...", author_name)

                    result = ToolRegistry.call(
                        "transcribe_video",
                        platform=platform,
                        video_url=url,
                        video_title=title,
                    )

                    if result.get("success"):
                        full_text = result.get("full_text", "")
                        self.dm.save_transcript_text(domain, author_name, video_id, full_text)

                        self.dm.save_analysis_summary(domain, author_name, {
                            "video_id": video_id,
                            "title": title,
                            "full_text_length": len(full_text),
                            "timestamp": now,
                        })

                        monitored += 1
                        log.log("INFO", "engine.monitor", "video_monitored",
                                f"Monitored: {author_name} - {title}", detail={"author": author_name, "video_id": video_id, "title": title})

                sub["last_monitored_at"] = now
                sub["total_analyses"] = sub.get("total_analyses", 0) + video_count

            except Exception as e:
                logger.error(f"Monitor error for {author_name}: {e}")
                log.log("ERROR", "engine.monitor", "author_error",
                        f"Monitor error for {author_name}: {e}", detail={"author": author_name}, error=str(e))
                errors += 1

        self.dm.save_subscriptions(domain, subs)

        if progress_callback:
            progress_callback(100, "完成", f"监控完成: {monitored} 视频, {errors} 错误", "")

        log.log("INFO", "engine.monitor", "monitor_complete",
                f"Monitor complete for '{domain}': {monitored} monitored, {errors} errors",
                detail={"domain": domain, "monitored": monitored, "errors": errors})

        return {
            "status": "ok",
            "monitored": monitored,
            "skipped": len(subs) - len(active),
            "errors": errors,
            "total_active": total_active,
            "timestamp": now,
        }