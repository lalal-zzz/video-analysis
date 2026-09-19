"""股票工具 — 股票数据获取，注册到全局 ToolRegistry."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── 工具注册 ───────────────────────────────────────────────

from tools.registry import ToolRegistry


@ToolRegistry.register("get_stock_data")
def get_stock_data(symbol: str, start: str = "", end: str = "") -> list[dict]:
    """获取股票历史数据。symbol: 股票代码, start/end: YYYY-MM-DD. 需要安装 akshare."""
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return [{"error": "akshare not installed. pip install akshare"}]

    try:
        if start and end:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="qfq")
        else:
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="qfq")
        records = df.tail(30).to_dict(orient="records")
        return [
            {
                "date": str(r.get("日期", "")),
                "open": float(r.get("开盘", 0)),
                "close": float(r.get("收盘", 0)),
                "high": float(r.get("最高", 0)),
                "low": float(r.get("最低", 0)),
                "volume": int(r.get("成交量", 0)),
            }
            for r in records
        ]
    except Exception as e:
        return [{"error": str(e)}]


@ToolRegistry.register("get_market_sentiment")
def get_market_sentiment(days: int = 7) -> dict:
    """获取市场情绪概览（基于涨停跌停数）."""
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return {"error": "akshare not installed"}

    try:
        df = ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "limit_up": len(df),
        }
    except Exception as e:
        return {"error": str(e)}


@ToolRegistry.register("get_volume_trends")
def get_volume_trends(domain: str) -> dict:
    """获取领域内视频播放量趋势."""
    from data_manager import DataManager
    dm = DataManager()
    transcripts = dm.list_transcripts(domain)
    if not transcripts:
        return {"domain": domain, "total": 0, "videos": []}

    total_views = 0
    for t in transcripts[:20]:
        # 从分析摘要中获取 views
        total_views += 1

    return {
        "domain": domain,
        "total_transcripts": len(transcripts),
        "recent_videos": transcripts[:10],
    }
