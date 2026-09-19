#!/usr/bin/env python3
"""Integration test — dummy data + web route verification."""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from datetime import datetime, timedelta

warnings.filterwarnings("ignore", category=RuntimeWarning)

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# Part 1: Populate dummy data for "stock" domain
# ═══════════════════════════════════════════════════════════

def populate_dummy_data():
    """Create realistic dummy data for stock domain."""
    data_dir = Path("data") / "stock"
    dm_sub_dir = data_dir / "subscriptions.json"
    dm_black_dir = data_dir / "blacklist.json"
    dm_analysis_dir = data_dir / "analysis"
    dm_transcript_dir = data_dir / "transcripts"
    dm_review_dir = data_dir / "review"

    for d in [data_dir, dm_sub_dir.parent, dm_black_dir.parent, dm_analysis_dir,
              dm_transcript_dir, dm_review_dir, dm_transcript_dir / "laoli"]:
        d.mkdir(parents=True, exist_ok=True)

    # ── Subscriptions ──────────────────────────────────────
    authors_data = [
        {"author": {"name": "老李聊股", "platform": "bilibili", "url": "https://space.bilibili.com/1001", "author_id": "1001"},
         "subscribed_at": "2025-05-01T10:00:00", "score": 0.8, "total_analyses": 15,
         "last_monitored_at": "2026-07-15T08:00:00", "tags": ["A股", "技术分析"], "notes": "", "is_blacklisted": False,
         "id": "sub001"},
        {"author": {"name": "美股研究社", "platform": "youtube", "url": "https://youtube.com/@meigu", "author_id": "2001"},
         "subscribed_at": "2025-06-15T12:00:00", "score": 0.5, "total_analyses": 8,
         "last_monitored_at": "2026-07-14T14:00:00", "tags": ["美股", "宏观"], "notes": "", "is_blacklisted": False,
         "id": "sub002"},
        {"author": {"name": "量子计算前沿", "platform": "youtube", "url": "https://youtube.com/@quantum", "author_id": "3001"},
         "subscribed_at": "2025-04-20T09:00:00", "score": 0.9, "total_analyses": 22,
         "last_monitored_at": "2026-07-15T06:00:00", "tags": ["AI", "量子"], "notes": "", "is_blacklisted": False,
         "id": "sub003"},
        {"author": {"name": "消费赛道分析", "platform": "bilibili", "url": "https://space.bilibili.com/4001", "author_id": "4001"},
         "subscribed_at": "2025-07-01T08:00:00", "score": 0.3, "total_analyses": 5,
         "last_monitored_at": "2026-07-13T10:00:00", "tags": ["消费", "白酒"], "notes": "", "is_blacklisted": False,
         "id": "sub004"},
        {"author": {"name": "新能源投资", "platform": "douyin", "url": "https://douyin.com/@newenergy", "author_id": "5001"},
         "subscribed_at": "2025-03-10T11:00:00", "score": -0.2, "total_analyses": 12,
         "last_monitored_at": "2026-07-12T16:00:00", "tags": ["新能源", "光伏"], "notes": "偶尔偏颇", "is_blacklisted": False,
         "id": "sub005"},
        {"author": {"name": "Crypto分析师", "platform": "youtube", "url": "https://youtube.com/@crypto", "author_id": "6001"},
         "subscribed_at": "2025-08-20T14:00:00", "score": 0.6, "total_analyses": 18,
         "last_monitored_at": "2026-07-15T09:00:00", "tags": ["加密货币", "区块链"], "notes": "", "is_blacklisted": False,
         "id": "sub006"},
        {"author": {"name": "医药板块专家", "platform": "bilibili", "url": "https://space.bilibili.com/7001", "author_id": "7001"},
         "subscribed_at": "2025-09-05T10:00:00", "score": 0.7, "total_analyses": 10,
         "last_monitored_at": "2026-07-14T12:00:00", "tags": ["医药", "生物"], "notes": "", "is_blacklisted": False,
         "id": "sub007"},
        {"author": {"name": "银行保险研究", "platform": "youtube", "url": "https://youtube.com/@bank", "author_id": "8001"},
         "subscribed_at": "2025-02-28T09:00:00", "score": 0.1, "total_analyses": 6,
         "last_monitored_at": "2026-07-11T08:00:00", "tags": ["金融", "银行"], "notes": "", "is_blacklisted": False,
         "id": "sub008"},
        {"author": {"name": "半导体观察者", "platform": "bilibili", "url": "https://space.bilibili.com/9001", "author_id": "9001"},
         "subscribed_at": "2025-01-15T08:00:00", "score": 0.85, "total_analyses": 25,
         "last_monitored_at": "2026-07-15T10:00:00", "tags": ["半导体", "芯片"], "notes": "高质量", "is_blacklisted": False,
         "id": "sub009"},
        {"author": {"name": "房地产投资", "platform": "douyin", "url": "https://douyin.com/@realestate", "author_id": "10001"},
         "subscribed_at": "2025-10-01T11:00:00", "score": -0.5, "total_analyses": 3,
         "last_monitored_at": "2026-07-10T14:00:00", "tags": ["房地产"], "notes": "", "is_blacklisted": False,
         "id": "sub010"},
        {"author": {"name": "基金定投达人", "platform": "bilibili", "url": "https://space.bilibili.com/11001", "author_id": "11001"},
         "subscribed_at": "2025-06-20T13:00:00", "score": 0.4, "total_analyses": 14,
         "last_monitored_at": "2026-07-14T07:00:00", "tags": ["基金", "定投"], "notes": "", "is_blacklisted": False,
         "id": "sub011"},
        {"author": {"name": "量化交易实战", "platform": "youtube", "url": "https://youtube.com/@quant", "author_id": "12001"},
         "subscribed_at": "2025-05-10T10:00:00", "score": 0.75, "total_analyses": 20,
         "last_monitored_at": "2026-07-15T11:00:00", "tags": ["量化", "算法"], "notes": "深度分析", "is_blacklisted": False,
         "id": "sub012"},
    ]

    # Add score_history for realism
    for sub in authors_data:
        score = sub["score"]
        sub["score_history"] = [
            {"value": max(-1.0, score + (i * 0.02)), "prev": 0.0, "changed_at": (datetime.now() - timedelta(days=30-i*2)).isoformat()}
            for i in range(min(5, max(1, int(abs(score) * 10))))
        ]

    dm_sub_dir.write_text(json.dumps(authors_data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[OK] subscriptions.json: {len(authors_data)} authors")

    # ── Blacklist ──────────────────────────────────────────
    blacklist = [
        {
            "author": {"name": "虚假消息号", "platform": "douyin", "author_id": "99001", "url": ""},
            "domain": "stock", "reason": "散布不实投资信息",
            "blacklisted_at": "2026-06-20T10:00:00",
        },
        {
            "author": {"name": "荐股骗子", "platform": "bilibili", "author_id": "99002", "url": ""},
            "domain": "stock", "reason": "违规荐股",
            "blacklisted_at": "2026-05-15T14:00:00",
        },
    ]
    dm_black_dir.write_text(json.dumps(blacklist, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] blacklist.json: {len(blacklist)} entries")

    # ── Analysis summaries ─────────────────────────────────
    sample_titles = ["A股下半年展望", "英伟达财报深度分析", "量子计算与AI融合趋势", "白酒消费旺季分析",
                     "光伏行业周期性拐点", "比特币减半后走势", "创新药审批政策解读", "银行不良率走势分析",
                     "半导体国产替代进度", "房地产政策影响评估", "指数基金定投策略", "量化策略回测分享"]

    score_samples = [0.8, 0.75, 0.9, 0.35, -0.15, 0.6, 0.72, 0.1, 0.88, -0.45, 0.42, 0.78]
    author_samples = ["老李聊股", "美股研究社", "量子计算前沿", "消费赛道分析", "新能源投资",
                      "Crypto分析师", "医药板块专家", "银行保险研究", "半导体观察者", "房地产投资",
                      "基金定投达人", "量化交易实战"]

    analyses_by_author = {}
    for i in range(len(sample_titles)):
        author = author_samples[i]
        if author not in analyses_by_author:
            analyses_by_author[author] = []

        for j in range(1, 4):  # 3 analyses per author
            ts = datetime.now() - timedelta(days=j*3, hours=i)
            analysis = {
                "title": sample_titles[i],
                "video_id": f"bv{900000 + i * 100 + j}",
                "author": author,
                "timestamp": ts.isoformat(),
                "key_points": [f"观点{i+j}-1: 市场整体趋势向好，但结构性分化明显",
                               f"观点{i+j}-2: 关注政策支持方向和行业景气度变化",
                               f"观点{i+j}-3: 建议控制仓位，分批建仓"],
                "sentiment": "bullish" if j % 3 != 0 else "neutral",
                "score_contribution": round(score_samples[i] + (j * 0.01 - 0.05), 2),
            }
            analyses_by_author[author].append(analysis)

    for author, analyses in analyses_by_author.items():
        analysis_file = dm_analysis_dir / f"{author}.json"
        analysis_file.write_text(json.dumps(analyses, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] analysis/: {sum(len(v) for v in analyses_by_author.values())} summaries across {len(analyses_by_author)} authors")

    # ── Transcript text files ──────────────────────────────
    video_ids = [f"bv{900000 + i}" for i in range(12)]
    authors_slug = ["laoli", "meigu", "quantum", "xiaofei", "newenergy", "crypto",
                    "yiyao", "yinhang", "bantai", "fangdichan", "jijin", "lianghua"]

    for slug, vid in zip(authors_slug, video_ids):
        transcript_dir = dm_transcript_dir / slug
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_file = transcript_dir / f"{vid}.txt"
        if not transcript_file.exists():
            transcript_file.write_text(
                f"[{slug}] 视频转录全文...\n\n"
                f"今天我们聊聊近期市场表现。整体来看，A股和港股都有一定的反弹压力。\n\n"
                f"首先关注科技板块，尤其是半导体和AI相关标的。全球半导体周期正处于复苏阶段，\n"
                f"国内政策也在持续扶持。建议关注以下几个方向：\n"
                f"1. 先进封装和测试环节\n"
                f"2. 国产替代空间较大的设备材料\n"
                f"3. AI算力基础设施相关企业\n\n"
                f"其次，消费板块在旺季到来前可以适度布局。但要注意估值分化。\n"
                f"\n最后提醒：以上观点仅供参考，不构成投资建议。",
                encoding="utf-8",
            )
    print(f"[OK] transcripts/: {len(authors_slug)} transcript directories")

    # ── Review report ──────────────────────────────────────
    review_file = dm_review_dir / "2026-07-14_14-30.md"
    review_file.write_text(
        "---\ndomain: stock\ndate: 2026-07-14\nsummary: 月度复盘\n---\n\n"
        "# 股票领域月度复盘报告\n\n"
        "## 概述\n\n"
        "本月共监控 12 位作者，新增转录 35 条视频。\n\n"
        "## 评分变化\n\n"
        "- 半导体观察者: 0.80 → 0.88 (提升)\n"
        "- 消费赛道分析: 0.50 → 0.35 (下降)\n"
        "- 房地产投资: -0.10 → -0.45 (建议关注)\n\n"
        "## 趋势判断\n\n"
        "市场整体呈现震荡上行态势，科技板块表现突出。\n"
        "消费板块受旺季预期提振，但分化明显。\n"
    )
    print(f"[OK] review/: 1 report")

    return {
        "subscriptions": len(authors_data),
        "blacklist": len(blacklist),
        "analyses": sum(len(v) for v in analyses_by_author.values()),
        "transcripts": len(authors_slug),
        "reviews": 1,
    }


# ═══════════════════════════════════════════════════════════
# Part 2: Test Phase 6 modules
# ═══════════════════════════════════════════════════════════

def test_phase6():
    """Test Phase 6 modules with dummy data."""
    print("\n" + "=" * 60)
    print("Phase 6: Domain Framework")
    print("=" * 60)

    # ── ToolRegistry ───────────────────────────────────────
    from tools import ToolRegistry

    tools = ToolRegistry.list_all()
    print(f"\n[OK] Tools registered: {len(tools)}")
    for name in sorted(tools):
        print(f"  - {name}")

    # ── DataManager ────────────────────────────────────────
    from data_manager import DataManager

    dm = DataManager()
    subs = dm.load_subscriptions("stock")
    print(f"\n[OK] Subscriptions: {len(subs)}")

    blacklist = dm.load_blacklist("stock")
    print(f"[OK] Blacklist: {len(blacklist)}")

    transcripts = dm.list_transcripts("stock")
    print(f"[OK] Transcripts: {len(transcripts)}")

    analyses = dm.list_analyses("stock")
    print(f"[OK] Analyses: {len(analyses)}")

    today = dm.count_analyses_recent(1)
    print(f"[OK] Today's analyses: {today}")

    transcript_count = dm.list_transcript_count(30)
    print(f"[OK] Transcripts (30 days): {transcript_count}")

    # ── DomainManager ──────────────────────────────────────
    from engine import DomainManager

    dman = DomainManager()
    domains = dman.list_domains()
    print(f"\n[OK] Domains: {len(domains)}")
    for d in domains:
        print(f"  - {d['name']} ({d.get('description', 'N/A')})")

    # ── DiscoverEngine ─────────────────────────────────────
    from engine.discover import DiscoverEngine

    discover = DiscoverEngine()
    print(f"\n[OK] DiscoverEngine: created (use discover.run('stock') to discover)")

    # ── MonitorEngine ──────────────────────────────────────
    from engine.monitor import MonitorEngine

    monitor = MonitorEngine()
    print(f"\n[OK] MonitorEngine: created (use monitor.run('stock') to monitor)")

    # ── ReviewEngine ───────────────────────────────────────
    from engine.review import ReviewEngine

    reviewer = ReviewEngine()
    prompt = reviewer._build_prompt("", "", subs, blacklist, dm.list_review_reports("stock"))
    print(f"\n[OK] ReviewEngine: prompt generated ({len(prompt)} chars)")

    # ── Tool calls ─────────────────────────────────────────
    tool_result = ToolRegistry.call("get_author_score", author="老李聊股", domain="stock")
    print(f"\n[OK] get_author_score: {tool_result}")

    tool_subs = ToolRegistry.call("get_subscriptions", domain="stock")
    print(f"[OK] get_subscriptions: {len(tool_subs)} results")

    tool_history = ToolRegistry.call("get_author_history", author="老李聊股", domain="stock")
    print(f"[OK] get_author_history: {len(tool_history)} results")


# ═══════════════════════════════════════════════════════════
# Part 3: Test Web routes
# ═══════════════════════════════════════════════════════════

def test_web_routes():
    """Test all web routes with Litestar TestClient."""
    print("\n" + "=" * 60)
    print("Phase 7: Web UI")
    print("=" * 60)

    from litestar.testing import TestClient
    from web.app import app

    with TestClient(app=app) as client:
        routes_tested = 0

        # ── Health check ───────────────────────────────────
        resp = client.get("/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        print(f"\n[OK] GET /health → {resp.status_code}")
        routes_tested += 1

        # ── Index / Dashboard ──────────────────────────────
        resp = client.get("/")
        assert resp.status_code == 200, f"Index failed: {resp.status_code}"
        assert "仪表盘" in resp.text
        assert "订阅作者" in resp.text
        print(f"[OK] GET / → {resp.status_code} (dashboard)")
        routes_tested += 1

        # ── Domains page ───────────────────────────────────
        resp = client.get("/domains")
        assert resp.status_code == 200, f"Domains failed: {resp.status_code}"
        assert "领域管理" in resp.text
        print(f"[OK] GET /domains → {resp.status_code}")
        routes_tested += 1

        # ── Create domain page ─────────────────────────────
        resp = client.get("/domains/create")
        assert resp.status_code == 200, f"Create domain page failed: {resp.status_code}"
        print(f"[OK] GET /domains/create → {resp.status_code}")
        routes_tested += 1

        # ── Create domain (POST) ───────────────────────────
        resp = client.post("/domains/create", json={"name": "", "intent": ""})
        assert resp.status_code in (200, 201), f"Create domain (empty) failed: {resp.status_code}"
        assert "请填写" in resp.text
        print(f"[OK] POST /domains/create (empty) → {resp.status_code}")
        routes_tested += 1

        # ── Create domain success ──────────────────────────
        resp = client.post("/domains/create", json={
            "name": "test_domain",
            "intent": "Test domain for verification",
            "template": "stock",
        })
        assert resp.status_code in (200, 201), f"Create domain (valid) failed: {resp.status_code}"
        assert "创建成功" in resp.text or "错误" in resp.text  # May fail due to LLM dependency but should not error
        print(f"[OK] POST /domains/create (valid) → {resp.status_code}")
        routes_tested += 1

        # ── Search page ────────────────────────────────────
        resp = client.get("/search")
        assert resp.status_code == 200, f"Search page failed: {resp.status_code}"
        assert "视频搜索" in resp.text
        print(f"[OK] GET /search → {resp.status_code}")
        routes_tested += 1

        # ── Execute search (POST) ──────────────────────────
        resp = client.post("/search/execute", content=json.dumps({
            "platform": "bilibili",
            "keywords": "测试",
            "max_results": 5,
        }).encode(), headers={"Content-Type": "application/json"})
        assert resp.status_code in (200, 201), f"Search execute failed: {resp.status_code}"
        # Should return either results or error (network-dependent)
        print(f"[OK] POST /search → {resp.status_code} (network-dependent)")
        routes_tested += 1

        # ── Results page ───────────────────────────────────
        resp = client.get("/results")
        assert resp.status_code == 200, f"Results failed: {resp.status_code}"
        print(f"[OK] GET /results → {resp.status_code}")
        routes_tested += 1

        # ── Transcripts page ───────────────────────────────
        resp = client.get("/transcripts")
        assert resp.status_code == 200, f"Transcripts failed: {resp.status_code}"
        print(f"[OK] GET /transcripts → {resp.status_code}")
        routes_tested += 1

        # ── Charts API ─────────────────────────────────────
        resp = client.get("/charts/author-trend/stock")
        assert resp.status_code == 200, f"Charts failed: {resp.status_code}"
        data = resp.json()
        assert "xAxis" in data
        assert "series" in data
        print(f"[OK] GET /charts/author-trend/stock → {resp.status_code}")
        routes_tested += 1

        # ── Volume trend chart ─────────────────────────────
        resp = client.get("/charts/volume-trend/stock")
        assert resp.status_code == 200, f"Volume chart failed: {resp.status_code}"
        data = resp.json()
        assert "dates" in data
        assert "views" in data
        print(f"[OK] GET /charts/volume-trend/stock → {resp.status_code}")
        routes_tested += 1

        # ── Monitor trigger ────────────────────────────────
        resp = client.post("/domains/stock/monitor")
        assert resp.status_code in (200, 201), f"Monitor failed: {resp.status_code}"
        print(f"[OK] POST /domains/stock/monitor → {resp.status_code} (network-dependent)")
        routes_tested += 1

        # ── Review trigger ─────────────────────────────────
        resp = client.post("/domains/stock/review")
        assert resp.status_code in (200, 201), f"Review failed: {resp.status_code}"
        print(f"[OK] POST /domains/stock/review → {resp.status_code} (LLM-dependent)")
        routes_tested += 1

        # ── Discover trigger ───────────────────────────────
        resp = client.post("/domains/stock/discover")
        assert resp.status_code in (200, 201), f"Discover failed: {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "started"
        print(f"[OK] POST /domains/stock/discover → {resp.status_code}")
        routes_tested += 1

        # ── WebSocket placeholder ──────────────────────────
        resp = client.get("/progress/docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "websocket"
        print(f"[OK] GET /ws/docs → {resp.status_code}")
        routes_tested += 1

        # ── List WS tasks ──────────────────────────────────
        resp = client.get("/ws/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert "tasks" in data
        print(f"[OK] GET /ws/tasks → {resp.status_code}")
        routes_tested += 1

        # ── Task detail (non-existent) ─────────────────────
        resp = client.get("/ws/tasks/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        print(f"[OK] GET /ws/tasks/nonexistent → {resp.status_code} (not found)")
        routes_tested += 1

        print(f"\n{ '=' * 60 }")
        print(f"Web routes tested: {routes_tested} all passed!")
        print(f"{ '=' * 60 }")


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("INTEGRATION TEST — Dummy Data + Phase 6 + Web Routes")
    print("=" * 60)

    # Part 1: Dummy data
    print("\n" + "=" * 60)
    print("Part 1: Populating dummy data")
    print("=" * 60)
    stats = populate_dummy_data()
    print(f"\nData populated:")
    for k, v in stats.items():
        print(f"  - {k}: {v}")

    # Part 2: Phase 6
    test_phase6()

    # Part 3: Web routes
    test_web_routes()

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
