"""Append-only daily evidence and comparison storage, separate from account state."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from models.daily_research import DailyResearch, MarketSnapshot, SavedDailyResearch
from models.transcript import VideoTranscript
from mcp_server.storage import Paths, atomic_json, atomic_text, identifier, within

SHANGHAI = timezone(timedelta(hours=8))


class DailyResearchStore:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.root = paths.root / "daily-research"

    def save(self, raw: dict[str, Any]) -> dict[str, Any]:
        record = DailyResearch.model_validate(raw)
        now = datetime.now(timezone.utc)
        if record.cutoff_at > now:
            raise ValueError("cutoff cannot be in the future")
        for source in record.transcript_artifacts:
            if not source.startswith("transcripts/"):
                raise ValueError("daily sources must reference existing transcript artifacts")
            path = within(self.paths.artifacts / "transcripts", source[len("transcripts/"):])
            if not path.is_file():
                raise ValueError("daily sources must reference existing transcript artifacts")
            transcript = VideoTranscript.model_validate_json(path.read_text(encoding="utf-8"))
            if not transcript.full_text.strip():
                raise ValueError("daily transcript cannot be empty")
            for forecast in (f for f in record.forecasts if f.transcript_artifact == source):
                evidence_url = urlparse(transcript.video.url)
                claimed_url = urlparse(str(forecast.source_url))
                if (evidence_url.netloc, evidence_url.path.rstrip("/")) != (claimed_url.netloc, claimed_url.path.rstrip("/")):
                    raise ValueError("forecast source URL must match its transcript video")
                if transcript.video.publish_time:
                    published = transcript.video.publish_time
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=SHANGHAI)
                    if published > record.cutoff_at:
                        raise ValueError("transcript publication is after the report cutoff")
                    if published != forecast.source_published_at:
                        raise ValueError("forecast publication time must match its transcript video")
                if not any(s.start <= forecast.timestamp_seconds <= s.end and s.text.strip() for s in transcript.segments):
                    raise ValueError("forecast timestamp must point to a nonempty transcript segment")
        revision = uuid.uuid4().hex
        folder = self.root / record.trading_date.isoformat()
        saved = SavedDailyResearch(revision=revision, saved_at=now, record=record)
        atomic_json(folder / f"{revision}.json", saved.model_dump(mode="json"))
        atomic_text(folder / f"{revision}.md", record.report)
        # Revision files are never overwritten. Latest is only a convenience pointer.
        atomic_json(folder / "latest.json", {"revision": revision})
        return {"status": "ok", "trading_date": record.trading_date.isoformat(), "revision": revision,
                "saved_at": now.isoformat(), "report_path": str(folder / f"{revision}.md")}

    def _revisions(self, trading_date: str) -> list[SavedDailyResearch]:
        folder = self.root / date.fromisoformat(trading_date).isoformat()
        return sorted((SavedDailyResearch.model_validate_json(p.read_text(encoding="utf-8"))
                       for p in folder.glob("*.json") if p.name != "latest.json"), key=lambda r: r.saved_at)

    def read(self, trading_date: str, revision: str = "latest") -> dict[str, Any]:
        day = date.fromisoformat(trading_date).isoformat()
        folder = self.root / day
        if revision == "latest":
            revision = json.loads((folder / "latest.json").read_text(encoding="utf-8"))["revision"]
        identifier(revision)
        saved = SavedDailyResearch.model_validate_json((folder / f"{revision}.json").read_text(encoding="utf-8"))
        return {"status": "ok", **saved.model_dump(mode="json")}

    def list(self, limit: int = 30) -> dict[str, Any]:
        if not 1 <= limit <= 366:
            raise ValueError("limit must be 1-366")
        days = sorted((p.name for p in self.root.iterdir() if p.is_dir() and (p / "latest.json").is_file()), reverse=True) if self.root.exists() else []
        return {"status": "ok", "trading_dates": days[:limit]}

    def evaluate(self, previous_date: str, raw_market: dict[str, Any]) -> dict[str, Any]:
        market = MarketSnapshot.model_validate(raw_market)
        previous = date.fromisoformat(previous_date)
        if previous >= market.trading_date:
            raise ValueError("baseline must precede outcome date")
        if market.previous_trading_date != previous:
            raise ValueError("baseline must match verified previous trading date")
        # Freeze the most recent version saved BEFORE today's opening auction (09:15).
        freeze = datetime.combine(market.trading_date, time(9, 15), SHANGHAI)
        revisions = self._revisions(previous_date)
        if not revisions:
            return {"status": "ok", "baseline_status": "missing", "evaluations": [], "message": "没有昨日记录，不能补造历史判断。"}
        eligible = [r for r in revisions if r.saved_at < freeze and r.record.cutoff_at < freeze]
        if not eligible:
            return {"status": "ok", "baseline_status": "late_record", "evaluations": [], "message": "历史记录在今日开盘后保存，只能展示回顾，不能作为事前预测计分。"}
        baseline = eligible[-1]
        evaluations = []
        for forecast in baseline.record.forecasts:
            if forecast.target_trading_date != market.trading_date:
                continue
            result: dict[str, Any] = {"forecast_id": forecast.id, "creator": forecast.creator, "statement": forecast.statement,
                                     "source_url": str(forecast.source_url), "timestamp_seconds": forecast.timestamp_seconds}
            observed = market.metrics.get(forecast.metric or "")
            if market.stage != "close" or not market.is_trading_day:
                result.update(outcome="pending", reason="交易日尚未收盘或为休市日")
            elif not forecast.scorable:
                result.update(outcome="not_scorable", reason=forecast.not_scorable_reason, condition=forecast.condition)
            elif observed is None:
                result.update(outcome="missing_data", reason="目标指标缺失，不能判错")
            elif observed.unit != forecast.unit:
                result.update(outcome="incompatible_unit", reason="指标单位与事前规则不一致")
            elif observed.observed_at.astimezone(SHANGHAI).date() != market.trading_date or observed.observed_at.astimezone(SHANGHAI).time().replace(tzinfo=None) < time(15, 0):
                result.update(outcome="missing_data", reason="指标时间不是目标交易日收盘，不能当作收盘结果")
            else:
                value, threshold = observed.value, forecast.threshold
                operations = {"gt": lambda: value > threshold, "gte": lambda: value >= threshold,
                              "lt": lambda: value < threshold, "lte": lambda: value <= threshold,
                              "between": lambda: threshold <= value <= forecast.upper}
                hit = operations[forecast.operator]()
                result.update(outcome="hit" if hit else "miss", observed=value, unit=observed.unit,
                              source_url_actual=str(observed.source_url), operator=forecast.operator,
                              threshold=threshold, upper=forecast.upper)
            evaluations.append(result)
        counts = {key: sum(r["outcome"] == key for r in evaluations) for key in ("hit", "miss", "pending", "not_scorable", "missing_data", "incompatible_unit")}
        scored = counts["hit"] + counts["miss"]
        return {"status": "ok", "baseline_status": "frozen", "baseline_revision": baseline.revision,
                "previous_trading_date": previous_date, "trading_date": market.trading_date.isoformat(),
                "evaluations": evaluations, "counts": counts, "scored_count": scored,
                "hit_rate": counts["hit"] / scored if scored else None,
                "message": "仅按事前明确定义的规则判定；命中率不代表投资收益或因果解释成立。"}
