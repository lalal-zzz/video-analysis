"""Mock 分析器 — 模拟 LLM 自动回复，不依赖任何真实模型。

用于测试完整流程（搜索 → 转录 → 分析）而不调用 Claude/Codex。
"""

from __future__ import annotations

from datetime import datetime

from analyzers.base import BaseAnalyzer
from models.analysis import AnalysisInsight, AnalysisRequest, AnalysisResult
from models.transcript import VideoTranscript


# ── 模拟分析模板（中文） ──────────────────────────────────────

_ANALYSIS_TEMPLATES = [
    """## 视频内容分析

### 核心观点汇总

通过对 {n} 个视频的转录内容分析，提炼出以下关键观点：

1. **市场整体趋势**：多数分析师认为当前市场处于结构性分化阶段，科技板块表现突出，但消费板块仍需观察。
2. **政策支持方向**：政策持续向半导体、AI 算力、新能源等领域倾斜，这些方向受到广泛认可。
3. **风险提示**：多个视频提到需关注全球宏观不确定性，建议控制仓位，分批建仓。

### 观点一致性分析

- **共识方向**：{n} 位分析师均看好科技主线（半导体、AI），一致看好度较高
- **分歧领域**：对消费板块未来走势存在分歧，部分看好消费复苏，部分持谨慎态度
- **情绪倾向**：整体偏乐观，乐观度约 {pct}%

### 结论

综合上述视频内容，市场对科技板块（尤其是半导体和AI算力）持高度乐观态度，对消费板块态度分化。建议重点关注政策受益方向，同时注意控制风险。""",
]

_INSIGHT_TEMPLATES = [
    {
        "summary": "大多数视频分析师对科技板块（半导体、AI算力）持乐观态度，认为政策支持力度加大是核心驱动力。",
        "confidence": 0.85,
    },
    {
        "summary": "消费板块存在分歧，部分分析师认为旺季可带来业绩提升，部分认为估值偏高需谨慎。",
        "confidence": 0.65,
    },
    {
        "summary": "多个视频提到宏观不确定性（利率政策、全球经济）是主要风险因素，建议保持仓位灵活。",
        "confidence": 0.75,
    },
]

_CONTRADICTIONS = [
    "部分分析师看好消费板块的复苏，而另一部分则认为估值偏高，建议回避，存在明显分歧。",
    "对于半导体板块的未来走势，多数持乐观态度，但个别分析师指出需警惕周期性下行风险。",
]


class MockAnalyzer(BaseAnalyzer):
    """模拟分析器 — 返回预定义格式的模拟分析结果，不做任何网络请求。"""

    model_type = "mock"

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed) if seed else None

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """生成模拟分析结果。"""
        transcript_count = len(request.transcripts)

        # 构建视频标题列表
        video_titles = [t.video.title for t in request.transcripts]
        if not video_titles:
            video_titles = ["[无转录视频]"]

        # 选择洞察（根据视频数量动态决定数量）
        n_insights = min(len(_INSIGHT_TEMPLATES), max(1, transcript_count))
        if self._rng:
            insights_pool = self._rng.sample(_INSIGHT_TEMPLATES, n_insights)
        else:
            insights_pool = _INSIGHT_TEMPLATES[:n_insights]

        insights = [
            AnalysisInsight(
                summary=item["summary"],
                video_titles=video_titles[:3],
                confidence=item["confidence"],
            )
            for item in insights_pool
        ]

        # 生成总结文本
        template = self._rng.choice(_ANALYSIS_TEMPLATES) if self._rng else _ANALYSIS_TEMPLATES[0]
        summary = template.format(
            n=transcript_count,
            pct=int(70 + (self._rng.randint(0, 25)) if self._rng else 80),
        )

        # 选择矛盾点
        n_contra = min(len(_CONTRADICTIONS), max(1, transcript_count // 3))
        if self._rng:
            contra_pool = self._rng.sample(_CONTRADICTIONS, n_contra)
        else:
            contra_pool = _CONTRADICTIONS[:n_contra]

        return AnalysisResult(
            request=request,
            summary=summary,
            insights=insights,
            contradictions=contra_pool,
            conclusion="综合多个视频的观点，市场整体偏向乐观，重点关注科技主线和政策支持方向。",
            raw_response=f"[Mock 模拟分析结果 — {datetime.now().isoformat()}]\n\n基于 {transcript_count} 个视频的转录内容，生成以下分析。",
        )

    async def chunk_transcripts(
        self,
        transcripts: list[VideoTranscript],
        max_chunk_size: int = 5,
    ) -> list[list[VideoTranscript]]:
        """将转录按 chunk 分组。"""
        chunks: list[list[VideoTranscript]] = []
        for i in range(0, len(transcripts), max_chunk_size):
            chunks.append(transcripts[i : i + max_chunk_size])
        return chunks


# 导入 random（MockAnalyzer 需要）
import random  # noqa: E402 (模块顶部 already imported above, but keeping explicit for clarity)
