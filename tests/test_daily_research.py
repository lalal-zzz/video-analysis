from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mcp_server.daily import DailyResearchStore
from mcp_server.storage import Paths, atomic_json
from models.daily_research import DailyResearch


def market(day="2025-01-07", *, stage="close", value=0.8, unit="pct"):
    return {"trading_date": day, "is_trading_day": True, "stage": stage,
            "previous_trading_date": "2025-01-06", "next_trading_date": "2025-01-08",
            "calendar_source_url": "https://www.sse.com.cn/", "metrics": {
                "sh_change_pct": {"value": value, "unit": unit, "source_url": "https://www.sse.com.cn/market/",
                                  "observed_at": f"{day}T15:01:00+08:00"}}}


def record():
    return {"trading_date": "2025-01-06", "cutoff_at": "2025-01-06T20:00:00+08:00",
            "market": {**market("2025-01-06"), "previous_trading_date": "2025-01-03", "next_trading_date": "2025-01-07"},
            "report": "# Simulated test report", "transcript_artifacts": ["transcripts/source.json"],
            "forecasts": [{"id": "f1", "creator": "Test creator", "creator_url": "https://space.bilibili.com/123",
                "source_url": "https://www.bilibili.com/video/BVtest", "source_published_at": "2025-01-06T16:00:00+08:00",
                "transcript_artifact": "transcripts/source.json", "timestamp_seconds": 3, "statement": "Next session closes higher",
                "target_trading_date": "2025-01-07", "metric": "sh_change_pct", "unit": "pct", "operator": "gt", "threshold": 0,
                "scorable": True}]}


def store(tmp_path):
    paths = Paths(tmp_path / "data", tmp_path / "state")
    atomic_json(paths.artifacts / "transcripts" / "source.json", {
        "video": {"platform": "bilibili", "video_id": "BVtest", "title": "Test", "author": "Test creator",
                  "url": "https://www.bilibili.com/video/BVtest"},
        "segments": [{"start": 3, "end": 7, "text": "Next session closes higher"}],
        "full_text": "Next session closes higher", "source": "subtitle"})
    return DailyResearchStore(paths)


def save_at(journal, monkeypatch, payload, stamp="2025-01-06T21:00:00+08:00"):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(stamp).astimezone(tz or timezone.utc)
    monkeypatch.setattr("mcp_server.daily.datetime", Clock)
    return journal.save(payload)


def test_revision_freeze_prevents_hindsight(tmp_path, monkeypatch):
    journal = store(tmp_path)
    first = save_at(journal, monkeypatch, record())
    changed = record()
    changed["forecasts"][0]["operator"] = "lt"
    second = save_at(journal, monkeypatch, changed, "2025-01-07T16:00:00+08:00")
    assert journal.read("2025-01-06")["revision"] == second["revision"]
    assert journal.read("2025-01-06", first["revision"])["record"]["forecasts"][0]["operator"] == "gt"
    result = journal.evaluate("2025-01-06", market())
    assert result["baseline_revision"] == first["revision"]
    assert result["counts"]["hit"] == 1 and result["hit_rate"] == 1
    assert len(journal._revisions("2025-01-06")) == 2


@pytest.mark.parametrize("value,outcome", [(0.8, "hit"), (0.0, "miss"), (-1.2, "miss")])
def test_actual_metric_direction(tmp_path, monkeypatch, value, outcome):
    journal = store(tmp_path)
    save_at(journal, monkeypatch, record())
    assert journal.evaluate("2025-01-06", market(value=value))["evaluations"][0]["outcome"] == outcome


@pytest.mark.parametrize("problem,outcome", [("intraday", "pending"), ("missing", "missing_data"), ("unit", "incompatible_unit"), ("time", "missing_data")])
def test_incomplete_evidence_never_counts_as_miss(tmp_path, monkeypatch, problem, outcome):
    journal = store(tmp_path)
    save_at(journal, monkeypatch, record())
    facts = market()
    if problem == "intraday":
        facts["stage"] = "intraday"
    elif problem == "missing":
        facts["metrics"] = {}
    elif problem == "unit":
        facts["metrics"]["sh_change_pct"]["unit"] = "ratio"
    else:
        facts["metrics"]["sh_change_pct"]["observed_at"] = "2025-01-07T12:00:00+08:00"
    result = journal.evaluate("2025-01-06", facts)
    assert result["evaluations"][0]["outcome"] == outcome
    assert result["scored_count"] == 0 and result["hit_rate"] is None


def test_missing_and_late_baselines(tmp_path, monkeypatch):
    journal = store(tmp_path)
    assert journal.evaluate("2025-01-06", market())["baseline_status"] == "missing"
    save_at(journal, monkeypatch, record(), "2025-01-07T16:00:00+08:00")
    assert journal.evaluate("2025-01-06", market())["baseline_status"] == "late_record"


def test_vague_conditional_and_wrong_horizon(tmp_path, monkeypatch):
    journal = store(tmp_path)
    data = record()
    item = data["forecasts"][0]
    item.update(scorable=False, condition="If volume increases", not_scorable_reason="Condition needs source verification")
    tomorrow = copy.deepcopy(item)
    tomorrow.update(id="f2", target_trading_date="2025-01-08")
    data["forecasts"].append(tomorrow)
    save_at(journal, monkeypatch, data)
    result = journal.evaluate("2025-01-06", market())
    assert len(result["evaluations"]) == 1
    assert result["counts"]["not_scorable"] == 1 and result["scored_count"] == 0


def test_holiday_and_nonadjacent_days(tmp_path, monkeypatch):
    journal = store(tmp_path)
    save_at(journal, monkeypatch, record())
    facts = market()
    facts.update(is_trading_day=False, stage="holiday")
    assert journal.evaluate("2025-01-06", facts)["counts"]["pending"] == 1
    facts["previous_trading_date"] = "2025-01-03"
    with pytest.raises(ValueError, match="previous trading date"):
        journal.evaluate("2025-01-06", facts)


@pytest.mark.parametrize("problem", ["source_after_cutoff", "same_day", "missing_artifact", "conditional_auto", "nan", "different_market_date", "duplicate_id"])
def test_record_rejects_invalid_evidence(problem):
    data = record()
    if problem == "source_after_cutoff":
        data["forecasts"][0]["source_published_at"] = "2025-01-07T08:00:00+08:00"
    elif problem == "same_day":
        data["forecasts"][0]["target_trading_date"] = "2025-01-06"
    elif problem == "missing_artifact":
        data["transcript_artifacts"] = []
    elif problem == "conditional_auto":
        data["forecasts"][0]["condition"] = "If volume increases"
    elif problem == "nan":
        data["forecasts"][0]["threshold"] = float("nan")
    elif problem == "different_market_date":
        data["market"] = market()
    else:
        data["forecasts"].append(copy.deepcopy(data["forecasts"][0]))
    with pytest.raises(ValueError):
        DailyResearch.model_validate(data)


def test_transcript_path_escape_and_empty_rejected(tmp_path, monkeypatch):
    journal = store(tmp_path)
    data = record()
    data["forecasts"] = []
    data["transcript_artifacts"] = ["transcripts/../results/secret.json"]
    with pytest.raises(ValueError, match="inside"):
        save_at(journal, monkeypatch, data)
    atomic_json(journal.paths.artifacts / "transcripts" / "source.json", {
        "video": {"platform": "bilibili", "video_id": "v1", "url": "https://www.bilibili.com/video/v1"}, "full_text": ""})
    data["transcript_artifacts"] = ["transcripts/source.json"]
    with pytest.raises(ValueError):
        save_at(journal, monkeypatch, data)


@pytest.mark.parametrize("problem", ["url", "timestamp", "publication"])
def test_forecast_must_match_transcript_evidence(tmp_path, monkeypatch, problem):
    journal = store(tmp_path)
    data = record()
    if problem == "url":
        data["forecasts"][0]["source_url"] = "https://www.bilibili.com/video/another-video"
    elif problem == "timestamp":
        data["forecasts"][0]["timestamp_seconds"] = 200
    else:
        path = journal.paths.artifacts / "transcripts" / "source.json"
        import json
        transcript = json.loads(path.read_text(encoding="utf-8"))
        transcript["video"]["publish_time"] = "2025-01-07T16:00:00+08:00"
        atomic_json(path, transcript)
    with pytest.raises(ValueError):
        save_at(journal, monkeypatch, data)
