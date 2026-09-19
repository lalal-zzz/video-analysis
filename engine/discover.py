"""发现引擎 — 通过搜索发现候选作者."""

from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Callable

from tools import ToolRegistry
from data_manager import DataManager
import log

logger = logging.getLogger(__name__)


class DiscoverEngine:
    """通过搜索发现候选作者."""

    def __init__(self) -> None:
        self.dm = DataManager()

    def run(self, domain: str, progress_callback: Callable | None = None) -> list[dict]:
        """发现候选作者列表.

        progress_callback(percent: int, step: str, message: str)
        """
        log.log("INFO", "engine.discover", "discover_start",
                f"Discover candidates for domain '{domain}'", detail={"domain": domain})

        if progress_callback:
            progress_callback(0, "开始", f"正在分析领域 '{domain}'...")

        domain_dir = Path("config") / "domains" / domain
        if not domain_dir.exists():
            log.log("ERROR", "engine.discover", "domain_not_found",
                    f"Domain not found: {domain}", detail={"domain": domain})
            raise FileNotFoundError(f"Domain not found: {domain}")

        config_file = domain_dir / "config.yaml"
        if not config_file.exists():
            log.log("ERROR", "engine.discover", "config_not_found",
                    f"config.yaml not found for domain: {domain}", detail={"domain": domain})
            raise FileNotFoundError(f"config.yaml not found for domain: {domain}")

        import yaml
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        discovery = config.get("discovery", {})
        author_queries = discovery.get("author_search", [])
        video_queries = discovery.get("video_search", [])

        existing_subs = self.dm.load_subscriptions(domain)
        existing_authors = {s["author"]["name"].lower() for s in existing_subs}

        blacklist = self.dm.load_blacklist(domain)
        blacklisted = {b["author"]["name"].lower() for b in blacklist}

        candidates: list[dict] = []
        all_queries = author_queries + video_queries
        total_queries = len(all_queries)

        for idx, query in enumerate(all_queries):
            platform = query.get("platform", "")
            keywords = ", ".join(query.get("keywords", []))
            max_results = query.get("max_results", 20)

            if progress_callback:
                pct = int((idx / total_queries) * 80) if total_queries else 0
                progress_callback(pct, f"搜索: {keywords[:20]}",
                                  f"在 {platform} 搜索 '{keywords}'...")

            log.log("DEBUG", "engine.discover", "searching",
                    f"Searching platform={platform} keywords='{keywords}'", detail={"platform": platform, "keywords": keywords})
            try:
                authors = ToolRegistry.call("search_authors", platform=platform, keywords=keywords, max_results=max_results)
                for author in authors:
                    name = author.get("name", "").lower()
                    if name and name not in existing_authors and name not in blacklisted:
                        candidates.append({
                            "name": author.get("name", ""),
                            "platform": platform,
                            "video_count": author.get("video_count", 0),
                            "already_subscribed": name in existing_authors,
                            "already_blacklisted": name in blacklisted,
                        })
            except KeyError:
                logger.warning("Tool search_authors not registered, skipping")

        if progress_callback:
            progress_callback(90, "去重", "正在去重...")

        seen = set()
        unique: list[dict] = []
        for c in candidates:
            key = c["name"].lower()
            if key not in seen:
                seen.add(key)
                unique.append(c)

        if progress_callback:
            progress_callback(100, "完成", f"发现 {len(unique)} 位候选作者")

        log.log("INFO", "engine.discover", "discover_complete",
                f"Found {len(unique)} candidates for domain '{domain}'", detail={"domain": domain, "count": len(unique)})
        return unique