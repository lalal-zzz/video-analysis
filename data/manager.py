"""统一数据管理器 — Domain + Pipeline 所有持久化操作."""

from __future__ import annotations

import json
import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from models.analysis import AnalysisResult
from models.transcript import VideoTranscript

logger = logging.getLogger(__name__)


def _sanitize(name: str) -> str:
    """安全文件名（简短版，给 domain 数据用）."""
    slug = name.replace(" ", "_")
    slug = "".join(c if c.isalnum() or c in "_-" else "_" for c in slug)
    return slug[:50]


def _sanitize_filename(s: str, max_len: int = 60) -> str:
    """安全文件名（详细版，给 pipeline 数据用）."""
    s = re.sub(r'[^\w\s\u4e00-\u9fff-]', '', s)
    s = re.sub(r'[-\s]+', '-', s)
    return s.strip('-')[:max_len].rstrip('-')


class DataManager:
    """统一数据管理器 — 读写 data/ 下所有 JSON/MD/TXT 文件."""

    def __init__(self, data_dir: str | Path = "data") -> None:
        self._root = Path(data_dir)

    # ── 领域: 订阅 ─────────────────────────────────────────

    def load_subscriptions(self, domain: str) -> list[dict]:
        filepath = self._root / domain / "subscriptions.json"
        if filepath.exists():
            return json.loads(filepath.read_text(encoding="utf-8"))
        return []

    def save_subscriptions(self, domain: str, subs: list[dict]) -> None:
        filepath = self._root / domain / "subscriptions.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            json.dumps(subs, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def load_blacklist(self, domain: str) -> list[dict]:
        filepath = self._root / domain / "blacklist.json"
        if filepath.exists():
            return json.loads(filepath.read_text(encoding="utf-8"))
        return []

    def save_blacklist(self, domain: str, entries: list[dict]) -> None:
        filepath = self._root / domain / "blacklist.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def unblacklist_author(self, domain: str, author: str) -> bool:
        """从黑名单移除作者 (取消关注时调用)."""
        bl_file = self._root / domain / "blacklist.json"
        if not bl_file.exists():
            return False
        bl: list[dict] = json.loads(bl_file.read_text(encoding="utf-8"))
        original_len = len(bl)
        bl = [b for b in bl if b.get("author", {}).get("name") != author]
        if len(bl) < original_len:
            bl_file.write_text(json.dumps(bl, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            return True
        return False

    # ── 领域: 转录文本 ─────────────────────────────────────

    def save_transcript_text(self, domain: str, author: str, video_id: str, full_text: str) -> Path:
        author_slug = _sanitize(author)
        filepath = self._root / domain / "transcripts" / author_slug / f"{video_id}.txt"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(full_text, encoding="utf-8")
        return filepath

    def load_transcript_text(self, domain: str, author: str, video_id: str) -> str | None:
        author_slug = _sanitize(author)
        filepath = self._root / domain / "transcripts" / author_slug / f"{video_id}.txt"
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return None

    def list_transcripts(self, domain: str) -> list[dict]:
        trans_dir = self._root / domain / "transcripts"
        if not trans_dir.exists():
            return []
        results = []
        for author_dir in sorted(trans_dir.iterdir()):
            if not author_dir.is_dir():
                continue
            for f in sorted(author_dir.glob("*.txt"), reverse=True):
                results.append({
                    "author": author_dir.name,
                    "video_id": f.stem,
                    "file": str(f),
                    "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "size": f.stat().st_size,
                })
        return results

    def list_transcript_count(self, days: int | None = None, domain: str | None = None) -> int:
        """Return transcript count, optionally limited to a recent number of days."""
        cutoff = datetime.now().timestamp() - days * 86400 if days is not None else None
        total = 0
        search_root = (self._root / domain) if domain else self._root
        for d in search_root.rglob("transcripts"):
            for f in d.rglob("*.txt"):
                if cutoff is None or f.stat().st_mtime >= cutoff:
                    total += 1
        return total

    # ── 领域: 分析摘要 ─────────────────────────────────────

    def save_analysis_summary(self, domain: str, author: str, summary: dict) -> None:
        author_slug = _sanitize(author)
        filepath = self._root / domain / "analysis" / f"{author_slug}.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        summaries: list[dict] = []
        if filepath.exists():
            try:
                summaries = json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                summaries = []
        summaries.append(summary)
        if len(summaries) > 100:
            summaries = summaries[-100:]
        filepath.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_analyses(self, domain: str) -> list[dict]:
        results = []
        analysis_dir = self._root / domain / "analysis"
        if not analysis_dir.exists():
            return []
        for f in sorted(analysis_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    results.extend(data)
            except (json.JSONDecodeError, OSError):
                pass
        return results

    def count_analyses_recent(self, days: int = 7, domain: str | None = None) -> int:
        cutoff_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        total = 0
        if domain:
            scan_dir = self._root / domain / "analysis"
            domains_to_scan = [scan_dir] if scan_dir.exists() else []
        else:
            scan_dir = self._root / "analysis"
            if not scan_dir.exists():
                return 0
            domains_to_scan = [d for d in scan_dir.iterdir() if d.is_dir()]
        for d in domains_to_scan:
            for author_file in d.glob("*.json"):
                try:
                    data = json.loads(author_file.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        for item in data:
                            ts = item.get("timestamp", item.get("analyzed_at", ""))
                            if ts and ts[:10] >= cutoff_str:
                                total += 1
                except (json.JSONDecodeError, OSError):
                    pass
        return total

    # ── 领域: 复盘报告 ─────────────────────────────────────

    def save_review_report(self, domain: str, content: str, metadata: dict | None = None) -> Path:
        report_dir = self._root / domain / "review"
        report_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        filename = now.strftime("%Y-%m-%d_%H-%M") + ".md"
        filepath = report_dir / filename
        if metadata:
            header = "---\n" + "\n".join(f"{k}: {v}" for k, v in metadata.items()) + "\n---\n\n"
        else:
            header = ""
        filepath.write_text(header + content, encoding="utf-8")
        return filepath

    def list_review_reports(self, domain: str, limit: int = 10) -> list[dict]:
        review_dir = self._root / domain / "review"
        if not review_dir.exists():
            return []
        files = sorted(review_dir.glob("*.md"), reverse=True)[:limit]
        results = []
        for f in files:
            results.append({
                "file": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
        return results

    # ── Pipeline: 转录文件 (.md) ──────────────────────────

    def save_transcript(self, transcript: VideoTranscript, session: str = "") -> Path:
        v = transcript.video
        slug = _sanitize_filename(v.title)
        subdir = self._root / "transcripts"
        if session:
            subdir = subdir / session
        subdir = subdir / v.platform
        subdir.mkdir(parents=True, exist_ok=True)

        filename = f"{v.video_id}_{slug}.md"
        filepath = subdir / filename

        lines = [
            f"# {v.title}",
            "",
            f"- **Author**: {v.author}",
            f"- **URL**: {v.url}",
            f"- **Platform**: {v.platform}",
            f"- **Published**: {v.publish_time or 'N/A'}",
            f"- **Duration**: {v.duration or 0}s",
            f"- **Views**: {v.stats.views}",
            f"- **Likes**: {v.stats.likes}",
            f"- **Transcript source**: {transcript.source}",
            "",
            "## Transcript",
            "",
        ]
        if transcript.segments:
            for seg in transcript.segments:
                lines.append(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
        else:
            lines.append(transcript.full_text or "")

        filepath.write_text("\n".join(lines), encoding="utf-8")
        return filepath

    def save_transcripts(self, transcripts: list[VideoTranscript], session: str = "") -> list[Path]:
        return [self.save_transcript(t, session) for t in transcripts]

    def list_pipeline_transcripts(self, platform: str = "", skill: str = "", session: str = "") -> list[Path]:
        subdir = self._root / "transcripts"
        if session:
            subdir = subdir / session
        if platform:
            subdir = subdir / platform
        if not subdir.exists():
            return []
        return sorted(subdir.rglob("*.md"))

    # ── Pipeline: 分析结果 ─────────────────────────────────

    def save_result(self, result: AnalysisResult, skill: str = "", session: str = "") -> Path:
        slug = _sanitize_filename(result.request.user_query or "analysis") or "analysis"
        timestamp = result.analyzed_at.strftime("%Y%m%d_%H%M%S")
        subdir = self._root / "results"
        if skill:
            subdir = subdir / skill
        if session:
            subdir = subdir / session
        subdir.mkdir(parents=True, exist_ok=True)

        filepath = subdir / f"{timestamp}_{slug}.md"

        lines = [
            "# Analysis Result",
            "",
            f"- **Analyzed at**: {result.analyzed_at}",
            f"- **Model**: {result.request.model_type or 'N/A'}",
            f"- **Skill**: {skill or 'N/A'}",
            f"- **Query**: {result.request.user_query}",
            "",
            "## Videos Analyzed",
            "",
        ]
        for t in result.request.transcripts:
            v = t.video
            lines.append(f"- [{v.title}]({v.url}) by {v.author}")

        lines.extend([
            "",
            "## Summary",
            "",
            result.summary or "(no summary)",
            "",
            "## Conclusion",
            "",
            result.conclusion or "(no conclusion)",
            "",
            "## Raw Response",
            "",
            result.raw_response or "(no raw response)",
        ])

        filepath.write_text("\n".join(lines), encoding="utf-8")
        return filepath

    def list_results(self, skill: str = "", session: str = "") -> list[Path]:
        subdir = self._root / "results"
        if skill:
            subdir = subdir / skill
        if session:
            subdir = subdir / session
        if not subdir.exists():
            return []
        return sorted(subdir.rglob("*.md"))

    # ── 公共访问器 ─────────────────────────────────────────

    @property
    def root(self) -> Path:
        return self._root
