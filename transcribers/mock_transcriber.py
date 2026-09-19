"""Mock 转录器 — 模拟视频转录，不依赖 Whisper 等真实模型。

用于测试完整流程（搜索 → 转录 → 分析）而不调用任何真实 API。
"""

from __future__ import annotations

from datetime import datetime

from models.video import VideoMetadata
from transcribers.base import BaseTranscriber
from models.transcript import VideoTranscript, TranscriptSegment


# ── 模拟转录文本 ──────────────────────────────────────────────

_MOCK_TRANSCRIPTS = [
    "大家好，欢迎来到今天的财经分享。今天我们来聊聊A股下半年的投资策略。从整体来看，市场呈现出结构性分化的特征。科技板块无疑是今年最耀眼的明星，尤其是半导体和AI算力产业链。全球半导体周期正处于复苏阶段，国内政策也在持续扶持，建议重点关注先进封装、国产替代设备等方向。其次是消费板块，旺季预期可能会带来一定反弹，但要注意估值分化。最后提醒，市场仍面临宏观不确定性，建议控制仓位，分批建仓。以上观点仅供参考。",
    "今天我们深入分析半导体行业。国产替代是当前最确定的投资主线之一。从设计到制造，从设备到材料，整个产业链都在加速国产替代进程。先进封装和测试环节是国内企业最有竞争力的方向，因为技术门槛相对较低，而需求又非常大。另外，AI算力基础设施也是一个重要方向，大模型训练需要大量GPU，这对相关产业链都带来巨大机会。",
    "新能源板块近期回调较多，但我觉得中长期逻辑没有改变。光伏行业虽然面临产能过剩压力，但储能和海外市场仍然是重要增长动力。尤其是欧洲能源转型的推进，为国内光伏企业提供了广阔的市场空间。建议大家不要恐慌性抛售，可以关注那些有海外渠道和储能业务的公司。",
    "白酒行业的数据大家都看到了，旺季确实带来了一定的销售增长，但是分化也很明显。高端白酒依然稳健，中低端品牌压力较大。从估值角度看，目前部分消费股确实不算便宜，需要精选个股。建议大家关注那些有品牌护城河、渠道能力强的龙头企业。",
]


class MockTranscriber(BaseTranscriber):
    """模拟转录器 — 为每个视频返回预定义的模拟转录文本。"""

    async def supports(self, video: VideoMetadata) -> bool:
        """Mock 支持所有视频。"""
        return True

    async def get_transcript(self, video: VideoMetadata) -> VideoTranscript:
        """返回模拟的转录内容。"""
        # 基于视频ID的最后一位选择不同模板
        try:
            idx = int(video.video_id[-1]) % len(_MOCK_TRANSCRIPTS)
        except (ValueError, IndexError):
            idx = 0

        full_text = _MOCK_TRANSCRIPTS[idx]

        # 构建带时间戳的段落
        segments = []
        sentences = [
            full_text[i:i + 50]
            for i in range(0, len(full_text), 50)
            if full_text[i:i + 50].strip()
        ]
        for i, sentence in enumerate(sentences):
            start = i * 12.5
            end = start + 12.5
            segments.append(TranscriptSegment(
                start=start,
                end=end,
                text=sentence,
            ))

        return VideoTranscript(
            video=video,
            segments=segments,
            full_text=full_text,
            source="mock",
        )
