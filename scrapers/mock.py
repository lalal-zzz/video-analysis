"""Mock 爬虫 — 模拟视频搜索结果，不依赖真实网络。

用于测试完整流程（搜索 → 转录 → 分析）而不访问任何真实平台 API。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from models.rules import SelectorConfig
from models.search import SearchQuery, SearchResult
from models.video import VideoMetadata, VideoStats
from scrapers.base import BaseScraper


# ── 模拟视频数据模板 ──────────────────────────────────────────

_VIDEO_TEMPLATES = [
    {
        "title": "2026年下半年A股投资策略：科技主线还是消费复苏？",
        "author": "财经观察家老张",
        "tags": ["A股", "投资策略", "科技"],
    },
    {
        "title": "半导体行业深度解析：国产替代加速进行时",
        "author": "芯片研究所",
        "tags": ["半导体", "国产替代", "芯片"],
    },
    {
        "title": "新能源板块：光伏储能还有机会吗？",
        "author": "绿能投研社",
        "tags": ["新能源", "光伏", "储能"],
    },
    {
        "title": "白酒消费数据解读：旺季是否带动业绩增长",
        "author": "消费研究员小王",
        "tags": ["消费", "白酒", "行业分析"],
    },
    {
        "title": "量化交易入门：如何用Python构建你的第一个策略",
        "author": "量化小课堂",
        "tags": ["量化", "Python", "策略"],
    },
    {
        "title": "AI算力产业链全景梳理：从芯片到应用",
        "author": "AI投资笔记",
        "tags": ["AI", "算力", "产业链"],
    },
    {
        "title": "医药板块：创新药审批加速后的投资机会",
        "author": "医研社",
        "tags": ["医药", "创新药", "政策"],
    },
    {
        "title": "美股科技股：英伟达财报后的投资启示",
        "author": "美股研究社",
        "tags": ["美股", "英伟达", "AI芯片"],
    },
    {
        "title": "宏观经济展望：利率政策转向对股市的影响",
        "author": "宏观经济学人",
        "tags": ["宏观", "利率", "政策"],
    },
    {
        "title": "加密货币市场：比特币减半后的走势分析",
        "author": "Crypto前沿",
        "tags": ["加密货币", "比特币", "区块链"],
    },
    {
        "title": "A股财报季：哪些行业盈利超预期",
        "author": "财报解读达人",
        "tags": ["财报", "A股", "盈利"],
    },
    {
        "title": "指数基金定投策略：普通人如何稳健投资",
        "author": "定投笔记",
        "tags": ["基金", "定投", "指数"],
    },
]

_AUTHOR_POOL = [
    "财经观察家老张", "芯片研究所", "绿能投研社", "消费研究员小王",
    "量化小课堂", "AI投资笔记", "医研社", "美股研究社",
    "宏观经济学人", "Crypto前沿", "财报解读达人", "定投笔记",
]


class MockScraper(BaseScraper):
    """模拟爬虫 — 返回预定义的模拟视频数据。"""

    platform = "mock"

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        # 为每个种子预生成一批数据，保证结果一致性
        self._cached_videos: list[VideoMetadata] = self._generate_pool()

    def _generate_pool(self) -> list[VideoMetadata]:
        """预生成一批模拟视频数据。"""
        videos: list[VideoMetadata] = []
        now = datetime.now()

        for i, tmpl in enumerate(_VIDEO_TEMPLATES):
            # 基于索引和种子产生确定性随机值
            self._rng.seed(i + (self._rng.randint(0, 2**31)))
            days_ago = self._rng.randint(1, 180)
            pub_time = now - timedelta(days=days_ago, hours=self._rng.randint(0, 23))

            # 生成与关键词相关的随机ID
            platform_id = f"mock_{i:04d}"
            if i >= 10:
                platform_id = f"mock_{i}"

            view_base = 1000 + self._rng.randint(0, 500000)
            like_base = max(10, view_base // self._rng.randint(20, 100))
            comment_base = max(5, like_base // self._rng.randint(3, 15))

            videos.append(VideoMetadata(
                platform="mock",
                video_id=platform_id,
                title=tmpl["title"],
                author=tmpl["author"],
                author_url=f"https://mock.video/user/{tmpl['author']}",
                url=f"https://mock.video/watch/{platform_id}",
                duration=float(self._rng.randint(180, 7200)),
                thumbnail_url=f"https://mock.video/thumb/{platform_id}.jpg",
                stats=VideoStats(
                    views=view_base,
                    likes=like_base,
                    comments=comment_base,
                    shares=max(1, like_base // self._rng.randint(5, 30)),
                ),
                publish_time=pub_time,
                tags=tmpl["tags"],
                description=f"这是一条关于「{tmpl['title']}」的模拟视频，仅供测试使用。",
            ))

        return videos

    async def fetch_videos(self, query: SearchQuery) -> SearchResult:
        """根据查询关键词模拟搜索。"""
        keywords = query.keywords.lower() if query.keywords else ""

        # 如果有关键词，按关键词匹配（模糊匹配 title、author、tags）
        if keywords:
            matched = []
            for v in self._cached_videos:
                score = 0
                if keywords in v.title.lower():
                    score += 10
                if keywords in v.author.lower():
                    score += 8
                if any(keywords in tag.lower() for tag in v.tags):
                    score += 5
                if score > 0:
                    matched.append((score, v))

            # 如果没有关键词匹配，返回全部
            if not matched:
                matched = [(0, v) for v in self._cached_videos]

            # 按分数排序
            matched.sort(key=lambda x: -x[0])
            selected = [v for _, v in matched]
        else:
            # 没有关键词，随机打乱返回
            pool = list(self._cached_videos)
            self._rng.shuffle(pool)
            selected = pool

        # 按 sort 参数排序
        sort = query.sort or "relevance"
        if sort == "publish_time":
            selected.sort(key=lambda v: v.publish_time or datetime.min, reverse=True)
        elif sort == "views":
            selected.sort(key=lambda v: v.stats.views or 0, reverse=True)

        # 取前 N 个
        n = min(query.max_results, len(selected))
        return SearchResult(
            query=query,
            videos=selected[:n],
            total_available=len(self._cached_videos),
        )

    async def fetch_author_videos(
        self, author: str, max_results: int = 50
    ) -> list[VideoMetadata]:
        """根据作者名模拟返回该作者的视频列表。"""
        author_lower = author.lower()
        matched = [
            v for v in self._cached_videos
            if author_lower in v.author.lower()
        ]

        # 如果完全匹配失败，尝试模糊匹配
        if not matched:
            # 取所有包含作者名部分字符的作者
            author_words = [w for w in author if w.strip()]
            for v in self._cached_videos:
                if any(
                    word in v.author.lower()
                    for word in author_words[:2]
                    if len(word) > 1
                ):
                    matched.append(v)

        if not matched:
            # 兜底：返回前 max_results 个视频
            matched = self._cached_videos[:max_results]

        return matched[:max_results]

    async def select(self, result: SearchResult, selector: SelectorConfig) -> list[VideoMetadata]:
        """应用选择器。Mock 简化为只取前 N 个。"""
        # 尝试从 rules 中提取 top_n（SortRule）
        max_count = 999
        for rule in selector.rules:
            if hasattr(rule, 'top_n') and rule.top_n is not None:
                max_count = rule.top_n
                break
        return result.videos[:max_count]
