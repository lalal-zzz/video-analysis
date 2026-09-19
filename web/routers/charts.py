"""图表数据 API — 从 DataManager 读取真实数据."""

from __future__ import annotations

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from litestar import get, MediaType
from data.manager import DataManager


@get("/charts/author-trend/{domain:str}", media_type=MediaType.JSON)
async def get_author_trend(domain: str) -> dict:
    """获取作者评分趋势数据 — 从订阅的 score_history 提取."""
    dm = DataManager()
    subs = dm.load_subscriptions(domain)

    if not subs:
        return {"xAxis": [], "series": {}}

    # Collect all score history points
    all_dates: set[str] = set()
    series: dict[str, list[float]] = {}

    for sub in subs:
        author = sub.get("author", {})
        if isinstance(author, dict):
            name = author.get("name", "未知")
        else:
            name = str(author)
        history = sub.get("score_history", [])
        if not history:
            continue
        scores: list[tuple[str, float]] = []
        for h in history:
            d = (h.get("changed_at", "") or "")[:10]
            v = h.get("value", 0)
            if d:
                all_dates.add(d)
                scores.append((d, v))
        if scores:
            scores.sort(key=lambda x: x[0])
            series[name] = [s[1] for s in scores]

    xAxis = sorted(all_dates)
    return {"xAxis": xAxis, "series": series}


@get("/charts/volume-trend/{domain:str}", media_type=MediaType.JSON)
async def get_volume_trend(domain: str) -> dict:
    """获取领域分析趋势 — 按日期统计分析数量."""
    dm = DataManager()
    analyses = dm.list_analyses(domain)

    from collections import Counter
    date_counts: Counter = Counter()

    for a in analyses:
        ts = (a.get("timestamp") or a.get("analyzed_at") or "")[:10]
        if ts:
            date_counts[ts] += 1

    sorted_dates = sorted(date_counts.keys())
    return {
        "dates": sorted_dates,
        "counts": [date_counts[d] for d in sorted_dates],
        "total": sum(date_counts.values()),
    }