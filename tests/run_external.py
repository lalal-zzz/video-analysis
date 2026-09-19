#!/usr/bin/env python3
"""Unified external integration test — no Docker required.

Usage:
    python tests/run_external.py                  # Full test (data + tools + web)
    python tests/run_external.py --no-web         # Skip web route tests
    python tests/run_external.py --fresh          # Start from empty data
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore", category=RuntimeWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
STOCK_DIR = DATA_DIR / "stock"


def clean_data():
    """Remove all stock domain data."""
    if STOCK_DIR.exists():
        shutil.rmtree(STOCK_DIR)
        print("[CLEAN] Removed data/stock/")
    for d in [DATA_DIR / "transcripts", DATA_DIR / "results"]:
        if d.exists():
            shutil.rmtree(d)
            print(f"[CLEAN] Removed {d.relative_to(PROJECT_ROOT)}/")


def populate_data():
    """Create realistic dummy data for stock domain tests."""
    for d in [
        STOCK_DIR,
        STOCK_DIR / "analysis",
        STOCK_DIR / "transcripts" / "laoli",
        STOCK_DIR / "transcripts" / "meigu",
        STOCK_DIR / "transcripts" / "bantai",
        STOCK_DIR / "review",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    authors_data = [
        {"author": {"name": "老李聊股", "platform": "bilibili", "url": "https://space.bilibili.com/1001", "author_id": "1001"},
         "subscribed_at": "2025-05-01T10:00:00", "score": 0.8, "total_analyses": 15,
         "last_monitored_at": "2026-07-15T08:00:00", "tags": ["A股", "技术分析"], "notes": "", "is_blacklisted": False,
         "id": "sub001"},
        {"author": {"name": "美股研究社", "platform": "youtube", "url": "https://youtube.com/@meigu", "author_id": "2001"},
         "subscribed_at": "2025-06-15T12:00:00", "score": 0.5, "total_analyses": 8,
         "last_monitored_at": "2026-07-14T14:00:00", "tags": ["美股", "宏观"], "notes": "", "is_blacklisted": False,
         "id": "sub002"},
        {"author": {"name": "半导体观察者", "platform": "bilibili", "url": "https://space.bilibili.com/9001", "author_id": "9001"},
         "subscribed_at": "2025-01-15T08:00:00", "score": 0.85, "total_analyses": 25,
         "last_monitored_at": "2026-07-15T10:00:00", "tags": ["半导体", "芯片"], "notes": "高质量", "is_blacklisted": False,
         "id": "sub003"},
        {"author": {"name": "基金定投达人", "platform": "bilibili", "url": "https://space.bilibili.com/11001", "author_id": "11001"},
         "subscribed_at": "2025-06-20T13:00:00", "score": 0.4, "total_analyses": 14,
         "last_monitored_at": "2026-07-14T07:00:00", "tags": ["基金", "定投"], "notes": "", "is_blacklisted": False,
         "id": "sub004"},
        {"author": {"name": "房地产投资", "platform": "douyin", "url": "https://douyin.com/@realestate", "author_id": "10001"},
         "subscribed_at": "2025-10-01T11:00:00", "score": -0.5, "total_analyses": 3,
         "last_monitored_at": "2026-07-10T14:00:00", "tags": ["房地产"], "notes": "", "is_blacklisted": False,
         "id": "sub005"},
    ]
    for sub in authors_data:
        s = sub["score"]
        sub["score_history"] = [
            {"value": round(max(-1.0, s + i * 0.02), 2), "prev": 0.0,
             "changed_at": (datetime.now() - timedelta(days=30 - i * 2)).isoformat()}
            for i in range(min(5, max(1, int(abs(s) * 10))))
        ]

    (STOCK_DIR / "subscriptions.json").write_text(
        json.dumps(authors_data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[DATA] subscriptions.json: {len(authors_data)} authors")

    blacklist = [
        {"author": {"name": "虚假消息号", "platform": "douyin", "author_id": "99001", "url": ""},
         "domain": "stock", "reason": "散布不实投资信息", "blacklisted_at": "2026-06-20T10:00:00"},
    ]
    (STOCK_DIR / "blacklist.json").write_text(
        json.dumps(blacklist, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DATA] blacklist.json: {len(blacklist)} entries")

    sample_titles = ["A股下半年展望", "英伟达财报深度分析", "白酒消费旺季分析",
                     "半导体国产替代进度", "房地产政策影响评估"]
    score_samples = [0.8, 0.75, 0.35, 0.88, -0.45]
    author_samples = ["老李聊股", "美股研究社", "基金定投达人", "半导体观察者", "房地产投资"]
    slug_samples = ["laoli", "meigu", "jijin", "bantai", "fangdichan"]

    for i in range(len(sample_titles)):
        author = author_samples[i]
        analyses = []
        for j in range(1, 4):
            ts = datetime.now() - timedelta(days=j * 3, hours=i)
            analyses.append({
                "title": sample_titles[i],
                "video_id": f"bv{900000 + i * 100 + j}",
                "author": author,
                "timestamp": ts.isoformat(),
                "key_points": [f"观点{i+j}-1: 市场整体趋势向好",
                               f"观点{i+j}-2: 关注政策支持方向"],
                "sentiment": "bullish" if j % 3 != 0 else "neutral",
                "score_contribution": round(score_samples[i] + j * 0.01 - 0.05, 2),
            })
        analysis_file = STOCK_DIR / "analysis" / f"{slug_samples[i]}.json"
        analysis_file.write_text(json.dumps(analyses, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DATA] analysis/*.json: {len(sample_titles) * 3} summaries across {len(sample_titles)} authors")

    for slug, author in zip(slug_samples, author_samples):
        trans_dir = STOCK_DIR / "transcripts" / slug
        trans_dir.mkdir(parents=True, exist_ok=True)
        vid = f"bv{900000 + slug_samples.index(slug) * 100 + 1}"
        (trans_dir / f"{vid}.txt").write_text(
            f"[{slug}] 视频转录全文...\n\n今天我们聊聊近期市场表现。整体来看市场有一定的反弹压力。\n",
            encoding="utf-8")

    print(f"[DATA] transcripts/: {len(slug_samples)} transcript files")

    review_file = STOCK_DIR / "review" / "2026-07-14_14-30.md"
    review_file.write_text(
        "---\ndomain: stock\ndate: 2026-07-14\n---\n\n# 月度复盘报告\n\n## 概述\n本月共监控 5 位作者。\n",
        encoding="utf-8")
    print("[DATA] review/: 1 report")


def test_data_layer() -> int:
    """Test DataManager domain + pipeline methods."""
    from data_manager import DataManager

    dm = DataManager()
    tests = 0

    subs = dm.load_subscriptions("stock")
    assert len(subs) == 5, f"Expected 5 subs, got {len(subs)}"
    for s in subs:
        assert "author" in s and "platform" in s["author"]
    tests += 1
    print(f"[PASS] load_subscriptions: {len(subs)}")

    bl = dm.load_blacklist("stock")
    assert len(bl) == 1
    assert "reason" in bl[0]
    tests += 1
    print(f"[PASS] load_blacklist: {len(bl)}")

    analyses = dm.list_analyses("stock")
    assert len(analyses) >= 10, f"Expected >= 10 analyses, got {len(analyses)}"
    for a in analyses[:3]:
        assert "title" in a and "author" in a
    tests += 1
    print(f"[PASS] list_analyses: {len(analyses)}")

    transcripts = dm.list_transcripts("stock")
    assert len(transcripts) > 0
    for t in transcripts:
        assert "author" in t and "video_id" in t
    tests += 1
    print(f"[PASS] list_transcripts: {len(transcripts)}")

    count = dm.count_analyses_recent(days=30, domain="stock")
    assert count >= 0
    tests += 1
    print(f"[PASS] count_analyses_recent: {count}")

    reports = dm.list_review_reports("stock")
    assert len(reports) >= 1
    tests += 1
    print(f"[PASS] list_review_reports: {len(reports)}")

    return tests


def test_tool_registry() -> int:
    """Test ToolRegistry list_all and individual tool calls."""
    from tools import ToolRegistry

    tests = 0

    tools = ToolRegistry.list_all()
    assert len(tools) >= 14, f"Expected >= 14 tools, got {len(tools)}"
    tests += 1
    print(f"[PASS] ToolRegistry.list_all: {len(tools)} tools")

    result = ToolRegistry.call("get_domain_trends", domain="stock")
    assert result is not None
    assert "top_keywords" in result
    tests += 1
    print(f"[PASS] get_domain_trends")

    result = ToolRegistry.call("get_subscriptions", domain="stock")
    assert len(result) == 5
    tests += 1
    print(f"[PASS] get_subscriptions: {len(result)}")

    result = ToolRegistry.call("get_author_score", author="老李聊股", domain="stock")
    assert result["score"] == 0.8
    tests += 1
    print(f"[PASS] get_author_score: {result['score']}")

    result = ToolRegistry.call("get_author_history", author="老李聊股", domain="stock")
    assert len(result) >= 1
    tests += 1
    print(f"[PASS] get_author_history: {len(result)} entries")

    result = ToolRegistry.call("get_domain_reports", domain="stock")
    assert len(result) >= 1
    tests += 1
    print(f"[PASS] get_domain_reports: {len(result)}")

    result = ToolRegistry.call("get_volume_trends", domain="stock")
    assert result["domain"] == "stock"
    tests += 1
    print(f"[PASS] get_volume_trends")

    return tests


def test_domain_engine() -> int:
    """Test DomainManager basic functionality."""
    from engine import DomainManager

    tests = 0

    dman = DomainManager()
    domains = dman.list_domains()
    assert len(domains) >= 1
    tests += 1
    print(f"[PASS] DomainManager.list_domains: {len(domains)}")

    return tests


def test_review_engine() -> int:
    """Test ReviewEngine prompt building and parsing."""
    from engine.review import ReviewEngine
    from data_manager import DataManager

    tests = 0
    dm = DataManager()
    subs = dm.load_subscriptions("stock")
    blacklist = dm.load_blacklist("stock")
    reports = dm.list_review_reports("stock")

    reviewer = ReviewEngine()
    prompt = reviewer._build_prompt("", "", subs, blacklist, reports)
    assert len(prompt) > 100
    tests += 1
    print(f"[PASS] ReviewEngine._build_prompt: {len(prompt)} chars")

    llm_output = """### 评分调整
| 作者 | 原分 | 新分 | 变动 | 理由 |
|------|------|------|------|------|
| 老李 | 0.8 | 0.9 | +0.1 | 近期分析质量提升 |

### 黑名单
| 作者 | 理由 |
|------|------|
| 虚假消息号 | 散布不实信息 |

### 领域趋势
科技板块热度持续上升。
"""
    parsed = reviewer.parse_llm_output(llm_output)
    assert len(parsed["score_changes"]) == 1
    assert parsed["score_changes"][0]["author"] == "老李"
    assert len(parsed["blacklists"]) == 1
    assert len(parsed["trend"]) > 0
    tests += 1
    print(f"[PASS] ReviewEngine.parse_llm_output: {len(parsed['score_changes'])} changes, {len(parsed['blacklists'])} blacklists")

    return tests


def test_web_routes() -> int:
    """Test all web routes with Litestar TestClient."""
    from litestar.testing import TestClient
    from web.app import app

    tests = 0
    with TestClient(app=app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        tests += 1
        print(f"[PASS] GET /health → {resp.status_code}")

        resp = client.get("/")
        assert resp.status_code == 200
        tests += 1
        print(f"[PASS] GET / → {resp.status_code}")

        resp = client.get("/domains")
        assert resp.status_code == 200
        tests += 1
        print(f"[PASS] GET /domains → {resp.status_code}")

        resp = client.get("/results")
        assert resp.status_code == 200
        tests += 1
        print(f"[PASS] GET /results → {resp.status_code}")

        resp = client.get("/transcripts")
        assert resp.status_code == 200
        tests += 1
        print(f"[PASS] GET /transcripts → {resp.status_code}")

        resp = client.get("/charts/author-trend/stock")
        assert resp.status_code == 200
        data = resp.json()
        assert "xAxis" in data and "series" in data
        tests += 1
        print(f"[PASS] GET /charts/author-trend/stock → {resp.status_code}")

        resp = client.get("/charts/volume-trend/stock")
        assert resp.status_code == 200
        data = resp.json()
        assert "dates" in data and "counts" in data
        tests += 1
        print(f"[PASS] GET /charts/volume-trend/stock → {resp.status_code}")

        resp = client.get("/progress/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "websocket"
        tests += 1
        print(f"[PASS] GET /progress/docs → {resp.status_code}")

        resp = client.get("/ws/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        tests += 1
        print(f"[PASS] GET /ws/tasks → {resp.status_code}")

    return tests


def test_log_module() -> int:
    """Test log module contextvars and pipeline_context."""
    import log
    from log import database

    tests = 0

    log.log("INFO", "test", "test_event", "test message")
    entries = database.tail(5)
    matching = [e for e in entries if e.get("event") == "test_event"]
    assert len(matching) >= 1
    tests += 1
    print(f"[PASS] log.log: event found")

    with log.pipeline_context("test_pipeline"):
        pid = log.get_pipeline_id()
        assert pid is not None
        assert log.current_pipeline() == "test_pipeline"
    tests += 1
    print(f"[PASS] pipeline_context: id={pid}")

    return tests


def main():
    parser = argparse.ArgumentParser(description="Unified external integration test")
    parser.add_argument("--no-web", action="store_true", help="Skip web route tests")
    parser.add_argument("--fresh", action="store_true", help="Start from empty data")
    args = parser.parse_args()

    print("=" * 60)
    print("UNIFIED EXTERNAL INTEGRATION TEST")
    print("=" * 60)

    if args.fresh:
        clean_data()

    print("\n--- Phase 1: Populate Dummy Data ---")
    populate_data()

    print("\n--- Phase 2: Data Layer ---")
    t1 = test_data_layer()

    print("\n--- Phase 3: ToolRegistry ---")
    t2 = test_tool_registry()

    print("\n--- Phase 4: Domain Engine ---")
    t3 = test_domain_engine()

    print("\n--- Phase 5: ReviewEngine ---")
    t4 = test_review_engine()

    print("\n--- Phase 6: Log Module ---")
    t5 = test_log_module()

    total = t1 + t2 + t3 + t4 + t5

    if not args.no_web:
        print("\n--- Phase 7: Web Routes ---")
        t6 = test_web_routes()
        total += t6
    else:
        print("\n--- Phase 7: Web Routes (SKIPPED) ---")
        t6 = 0

    print("\n" + "=" * 60)
    print(f"ALL TESTS PASSED: {total} assertions ✓")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())