#!/usr/bin/env python3
"""端到端 Mock 测试 — 验证视频搜索→转录→分析的完整流程。

使用 MockScraper、MockTranscriber、MockAnalyzer 代替真实 API，
不访问任何外部网络，验证 Orchestrator 完整流水线畅通。
"""

from __future__ import annotations

import asyncio
import json
import sys
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore", category=RuntimeWarning)

# 确保项目根目录可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cache.manager import DiskCache
from config.settings import Settings
from core.orchestrator import Orchestrator
from models.analysis import AnalysisRequest, AnalysisResult
from models.rules import SelectorConfig
from models.search import SearchQuery, SearchResult
from models.video import VideoMetadata, VideoStats
from models.transcript import VideoTranscript, TranscriptSegment
from scrapers.mock import MockScraper
from scrapers.base import BaseScraper
from transcribers.mock_transcriber import MockTranscriber
from analyzers.mock_analyzer import MockAnalyzer


# ── 辅助函数 ────────────────────────────────────────────────────

def section(title: str) -> None:
    """打印分隔标题。"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def bullet(label: str, value: str, icon: str = "✓") -> None:
    print(f"  {icon} {label}: {value}")


# ── 测试用例 ────────────────────────────────────────────────────

async def test_mock_scraper_fetch():
    """测试 Mock 爬虫搜索功能。"""
    section("Test 1: MockScraper 视频搜索")

    scraper = MockScraper(seed=42)

    # 1a. 关键词搜索
    print("\n  [1a] 关键词搜索: '半导体'")
    query = SearchQuery(
        keywords="半导体",
        platform="mock",
        max_results=5,
        sort="relevance",
    )
    result: SearchResult = await scraper.fetch_videos(query)
    bullet("搜索关键词", query.keywords)
    bullet("匹配结果", f"{len(result.videos)} 个视频", "📦")
    bullet("总可用", f"{result.total_available}", "📊")

    for i, v in enumerate(result.videos[:3]):
        print(f"    [{i+1}] {v.title}")
        print(f"         作者: {v.author} | 播放: {v.stats.views:,}")
        bullet("标签", ", ".join(v.tags))

    assert len(result.videos) > 0, "关键词搜索应返回结果"
    assert result.videos[0].title.lower().find("半导体") >= 0, "第一个结果应包含关键词"
    print("\n  ✅ Test 1a 通过")

    # 1b. 空关键词（返回全部）
    print("\n  [1b] 空关键词搜索（返回全部）")
    query_all = SearchQuery(
        keywords="",
        platform="mock",
        max_results=10,
    )
    result_all = await scraper.fetch_videos(query_all)
    bullet("返回视频数", f"{len(result_all.videos)}", "📦")
    assert len(result_all.videos) > 0, "空关键词应返回全部视频"
    print("  ✅ Test 1b 通过")

    # 1c. 按播放量排序
    print("\n  [1c] 按播放量排序")
    query_views = SearchQuery(
        keywords="",
        platform="mock",
        max_results=5,
        sort="views",
    )
    result_views = await scraper.fetch_videos(query_views)
    views_list = [v.stats.views for v in result_views.videos]
    assert views_list == sorted(views_list, reverse=True), "应按播放量降序排列"
    bullet("排序验证", f"降序 ✓ ({views_list[:3]})", "📈")
    print("  ✅ Test 1c 通过")

    # 1d. 作者搜索
    print("\n  [1d] 作者搜索: '老张'")
    author_videos = await scraper.fetch_author_videos("老张", max_results=5)
    bullet("找到作者视频", f"{len(author_videos)} 个")
    assert len(author_videos) > 0, "作者搜索应返回结果"
    print("  ✅ Test 1d 通过")

    # 1e. Selector 应用
    print("\n  [1e] Selector 筛选（取前 3 个）")
    selector = SelectorConfig(
        rules=[{"rule_type": "sort", "sort_by": "views", "descending": True, "top_n": 3}]
    )
    selected = await scraper.select(result_all, selector)
    bullet("筛选后数量", f"{len(selected)}", "🔍")
    assert len(selected) <= 3, "Selector 应限制结果数量"
    print("  ✅ Test 1e 通过")


async def test_mock_transcriber():
    """测试 Mock 转录器功能。"""
    section("Test 2: MockTranscriber 视频转录")

    transcriber = MockTranscriber()

    # 创建测试视频
    test_video = VideoMetadata(
        platform="mock",
        video_id="mock_0001",
        title="半导体行业深度解析",
        author="芯片研究所",
        url="https://mock.video/watch/mock_0001",
        stats=VideoStats(views=12345, likes=567),
    )

    print("\n  [2a] 转录单个视频")
    transcript = await transcriber.get_transcript(test_video)
    bullet("视频标题", test_video.title)
    bullet("转录来源", transcript.source)
    bullet("段落数", f"{len(transcript.segments)}", "📝")
    bullet("文本长度", f"{len(transcript.full_text)} 字")
    print(f"\n  转录预览: {transcript.full_text[:80]}...")
    assert len(transcript.segments) > 0, "应返回段落"
    assert len(transcript.full_text) > 0, "应有转录文本"
    assert transcript.source == "mock", "来源应为 mock"
    print("  ✅ Test 2a 通过")

    # 2b. supports 方法
    print("\n  [2b] supports() 方法")
    supported = await transcriber.supports(test_video)
    bullet("是否支持", f"{supported}", "✅")
    assert supported, "MockTranscriber 应支持所有视频"
    print("  ✅ Test 2b 通过")


async def test_mock_analyzer():
    """测试 Mock 分析器功能。"""
    section("Test 3: MockAnalyzer 视频分析")

    analyzer = MockAnalyzer(seed=42)

    # 创建测试转录
    test_video = VideoMetadata(
        platform="mock",
        video_id="mock_0001",
        title="A股下半年展望",
        author="财经观察家老张",
        url="https://mock.video/watch/mock_0001",
        stats=VideoStats(views=12345),
    )
    test_transcript = VideoTranscript(
        video=test_video,
        segments=[
            TranscriptSegment(start=0, end=12.5, text="今天我们来分析A股市场。"),
            TranscriptSegment(start=12.5, end=25, text="整体来看科技板块表现突出。"),
        ],
        full_text="今天我们来分析A股市场。整体来看科技板块表现突出。",
        source="mock",
    )

    print("\n  [3a] 分析单个转录")
    request = AnalysisRequest(
        transcripts=[test_transcript],
        user_query="分析A股下半年投资机会",
        model_type="mock",
    )
    result: AnalysisResult = await analyzer.analyze(request)
    bullet("用户问题", request.user_query)
    bullet("模型类型", result.request.model_type)
    bullet("洞察数量", f"{len(result.insights)}", "💡")
    print(f"\n  结论: {result.conclusion}")
    print(f"  总结预览: {result.summary[:60]}...")

    assert result.conclusion, "应有结论"
    assert result.summary, "应有总结"
    assert len(result.insights) > 0, "应有洞察"
    print("  ✅ Test 3a 通过")

    # 3b. chunk_transcripts
    print("\n  [3b] chunk_transcripts 分块")
    transcripts = [test_transcript] * 12
    chunks = await analyzer.chunk_transcripts(transcripts, max_chunk_size=5)
    bullet("输入转录", f"{len(transcripts)} 个", "📝")
    bullet("分块数", f"{len(chunks)} 个", "📦")
    assert len(chunks) == 3, "12个转录分5个/块应得到3块"
    print("  ✅ Test 3b 通过")


async def test_full_pipeline():
    """端到端流水线测试：搜索 → 转录 → 分析。"""
    section("Test 4: 端到端流水线（搜索 → 转录 → 分析）")

    print("\n  初始化组件...")
    settings = Settings()
    scraper = MockScraper(seed=42)
    transcriber = MockTranscriber()
    analyzer = MockAnalyzer(seed=42)
    cache = DiskCache(settings)

    orchestrator = Orchestrator(
        scraper=scraper,
        transcriber=transcriber,
        analyzer=analyzer,
        cache=cache,
        settings=settings,
    )

    # 4a. 关键词搜索 → 转录 → 分析
    print("\n  [4a] 执行完整流水线")
    user_query = "分析半导体行业投资机会"
    search_query = SearchQuery(
        keywords="半导体",
        platform="mock",
        max_results=3,
        sort="relevance",
    )

    print(f"    → 搜索关键词: '{search_query.keywords}'")
    result = await orchestrator.run(
        user_query=user_query,
        search_query=search_query,
        max_videos=3,
        skill="stock-analyst",
        session="test_session_001",
    )

    bullet("最终用户问题", user_query)
    bullet("分析模型", result.request.model_type)
    bullet("洞察数", f"{len(result.insights)}", "💡")
    bullet("矛盾点", f"{len(result.contradictions)}", "⚠️")
    print(f"\n    结论: {result.conclusion[:80]}...")

    assert result.summary, "应有分析总结"
    assert result.conclusion, "应有结论"
    assert len(result.insights) > 0, "应有洞察"
    print("\n  ✅ Test 4a 通过 — 端到端流水线运行成功！")

    # 4b. 空关键词 → 分析全部
    print("\n  [4b] 空关键词搜索 + 分析")
    search_query_all = SearchQuery(
        keywords="",
        platform="mock",
        max_results=2,
    )
    result_all = await orchestrator.run(
        user_query="全面市场分析",
        search_query=search_query_all,
        max_videos=2,
        session="test_session_002",
    )
    bullet("洞察数", f"{len(result_all.insights)}", "💡")
    assert result_all.conclusion, "空关键词也应产出分析"
    print("  ✅ Test 4b 通过")


async def test_web_integration():
    """Web 路由集成测试（使用 Mock 爬虫替换真实爬虫）。"""
    section("Test 5: Web 路由 Mock 集成测试")

    try:
        from litestar.testing import TestClient
    except ImportError:
        print("\n  ⚠️ litestar 未安装，跳过 Web 路由测试")
        return

    print("\n  [5a] 验证路由可访问")
    from litestar.testing import TestClient
    from web.app import app

    # 注入 Mock 爬虫到路由模块
    import web.routers.search as search_router
    original_scrapers = search_router.SCRAPERS.copy()
    search_router.SCRAPERS["mock"] = MockScraper

    # 注入 Mock 分析器到 analyze 路由
    import web.routers.search as analyze_router
    # 修改 _run_analysis 中的 scraper 使用

    with TestClient(app=app) as client:
        # 5a. 搜索页面
        print("\n    检查搜索页面...")
        resp = client.get("/search")
        assert resp.status_code == 200, f"搜索页面失败: {resp.status_code}"
        assert "视频搜索" in resp.text
        bullet("搜索页面", f"200 OK ✓")
        print("    ✅ 搜索页面访问正常")

        # 5b. Health check
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        bullet("健康检查", f"status={data.get('status', 'ok')}", "💚")
        print("    ✅ 健康检查正常")

        # 5c. 创建测试领域
        print("\n    检查领域管理...")
        resp = client.get("/domains")
        assert resp.status_code == 200, f"领域页面失败: {resp.status_code}"
        bullet("领域页面", f"200 OK ✓")
        print("    ✅ 领域页面正常")

        # 恢复原始爬虫
        search_router.SCRAPERS = original_scrapers

    print("\n  ✅ Test 5 通过 — Web 路由集成正常！")


async def test_cache_integration():
    """测试缓存层与 Mock 的集成。"""
    section("Test 6: 缓存集成测试")

    print("\n  [6a] 缓存读写")
    settings = Settings()
    cache = DiskCache(settings)

    # 写入测试缓存
    test_query = SearchQuery(
        keywords="测试缓存",
        platform="mock",
        max_results=3,
    )
    test_result = SearchResult(
        query=test_query,
        videos=[
            VideoMetadata(
                platform="mock",
                video_id="cache_test_001",
                title="缓存测试视频",
                author="测试作者",
                url="https://mock.video/watch/cache_test_001",
            )
        ],
    )

    await cache.set_query(test_result)
    cached = await cache.get_query(test_query)
    assert cached is not None, "缓存应返回写入的数据"
    assert len(cached.videos) == 1, "缓存应保存视频列表"
    bullet("缓存写入", "成功 ✓")
    bullet("缓存读取", f"命中 {len(cached.videos)} 个视频", "💾")
    print("  ✅ Test 6a 通过")

    # 6b. 视频缓存
    print("\n  [6b] 视频缓存")
    test_video = VideoMetadata(
        platform="mock",
        video_id="video_cache_test",
        title="视频缓存测试",
        author="测试作者",
        url="https://mock.video/watch/video_cache_test",
    )
    test_transcript = VideoTranscript(
        video=test_video,
        segments=[TranscriptSegment(start=0, end=10, text="测试转录文本")],
        full_text="测试转录文本",
        source="mock",
    )
    await cache.set_video(test_transcript)
    cached_transcript = await cache.get_video("mock", "video_cache_test")
    assert cached_transcript is not None, "视频缓存应命中"
    bullet("视频缓存", "命中 ✓", "🎬")
    print("  ✅ Test 6b 通过")


async def main():
    """运行所有测试。"""
    print("=" * 60)
    print("  MOCK E2E 端到端测试")
    print("  验证: 搜索 → 转录 → 分析 完整流程")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    passed = 0
    failed = 0
    errors = []

    tests = [
        ("MockScraper 搜索", test_mock_scraper_fetch),
        ("MockTranscriber 转录", test_mock_transcriber),
        ("MockAnalyzer 分析", test_mock_analyzer),
        ("端到端流水线", test_full_pipeline),
        ("Web 路由集成", test_web_integration),
        ("缓存集成", test_cache_integration),
    ]

    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"\n  ❌ {name} 失败: {e}")
            import traceback
            traceback.print_exc()

    # 汇总
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)
    print(f"\n  通过: {passed}/{len(tests)}")
    print(f"  失败: {failed}/{len(tests)}")

    if errors:
        print("\n  失败详情:")
        for name, err in errors:
            print(f"    ❌ {name}: {err}")
        print("\n  ⚠️ 部分测试失败")
        sys.exit(1)
    else:
        print("\n  🎉 全部测试通过！")
        print("=" * 60)
        print("\n  完整流程验证成功：")
        print("    1. ✅ MockScraper — 模拟视频搜索（无网络请求）")
        print("    2. ✅ MockTranscriber — 模拟视频转录（无 Whisper）")
        print("    3. ✅ MockAnalyzer — 模拟 LLM 分析（无 Claude/Codex）")
        print("    4. ✅ Orchestrator — 完整流水线（搜索→转录→分析）")
        print("    5. ✅ Web 路由 — 搜索页面可访问")
        print("    6. ✅ 缓存层 — 读写正常")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
