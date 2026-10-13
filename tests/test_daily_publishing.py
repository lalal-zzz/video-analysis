"""Publication is versioned, private-safe and restricted to report assets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.publish_daily_report import public_report, publish


def saved(root: Path):
    page = root / "github.html"
    page.write_text('<html><script id="daily-data" type="application/json">[]</script></html>', encoding="utf-8")
    source = root / "private-record.json"
    data = {"revision": "a" * 32, "saved_at": "2025-01-07T08:00:00+08:00", "record": {
        "trading_date": "2025-01-06", "cutoff_at": "2025-01-06T23:59:59+08:00",
        "market": {"trading_date": "2025-01-06", "is_trading_day": True, "stage": "close",
                   "calendar_source_url": "https://www.sse.com.cn/", "metrics": {}},
        "report": "# Test report\n\n公开作者的观点与操作条件 [原视频](https://www.bilibili.com/video/BVtest) · transcripts/example.json\n",
        "transcript_artifacts": ["transcripts/example.json"], "coverage": {"公开作者": "ok"}}}
    source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return source


def test_versioned_export_keeps_views_but_removes_internal_artifact_ids(tmp_path):
    source = saved(tmp_path)
    first = publish(source, root=tmp_path)
    report = tmp_path / first["report"]
    text = report.read_text(encoding="utf-8")
    assert "公开作者的观点" in text and "https://www.bilibili.com/video/BVtest" in text
    assert "transcripts/example.json" not in text
    initial = (tmp_path / "html/skills/daily/index.json").read_text(encoding="utf-8")
    publish(source, root=tmp_path)
    assert (tmp_path / "html/skills/daily/index.json").read_text(encoding="utf-8") == initial
    data = json.loads(source.read_text(encoding="utf-8"))
    data["revision"] = "b" * 32
    data["saved_at"] = "2025-01-07T08:30:00+08:00"
    source.write_text(json.dumps(data), encoding="utf-8")
    publish(source, root=tmp_path)
    assert report.is_file()
    index = json.loads((tmp_path / "html/skills/daily/index.json").read_text(encoding="utf-8"))
    assert len(index["reports"]) == 2 and index["reports"][0]["revision"] == "b" * 32


@pytest.mark.parametrize("text", ["Cookie: secret", "SESSDATA=hidden", "person@example.com", "C:\\Users\\private\\file.json", "你的关注列表：甲乙", '"full_text": "entire source"', "{{unfinished}}"])
def test_private_and_unfilled_reports_are_rejected(text):
    with pytest.raises(ValueError):
        public_report(text)


def test_empty_evidence_and_path_traversal_cannot_export(tmp_path):
    source = saved(tmp_path)
    data = json.loads(source.read_text(encoding="utf-8"))
    data["record"]["transcript_artifacts"] = []
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="No transcript"):
        publish(source, root=tmp_path)
    data["record"]["transcript_artifacts"] = ["transcripts/example.json"]
    data["revision"] = "../escape"
    source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="UUID"):
        publish(source, root=tmp_path)
    assert not (tmp_path / "html").exists()


def test_user_staging_is_preserved_and_no_public_files_written(tmp_path, monkeypatch):
    source = saved(tmp_path)
    def git(root, *args):
        if args[0] == "branch":
            return "main"
        if args[0] == "remote":
            return "https://github.com/lalal-zzz/video-analysis.git"
        if args[:3] == ("diff", "--cached", "--name-only"):
            return "user-change.py"
        raise AssertionError("No git mutation is authorized when foreign files are staged")
    monkeypatch.setattr("scripts.publish_daily_report.run_git", git)
    with pytest.raises(ValueError, match="Existing staged"):
        publish(source, root=tmp_path, push=True)
    assert not (tmp_path / "html").exists()


def test_only_public_report_assets_are_committed_and_failed_push_is_explicit(tmp_path, monkeypatch):
    source = saved(tmp_path)
    calls = []
    staged = False
    def git(root, *args):
        nonlocal staged
        calls.append(args)
        if args[0] == "branch":
            return "main"
        if args[0] == "remote":
            return "https://github.com/lalal-zzz/video-analysis.git"
        if args[:3] == ("diff", "--cached", "--name-only"):
            return "github.html" if staged else ""
        if args[0] == "add":
            staged = True
        if args[0] == "rev-parse":
            return "c" * 40
        if args[0] == "push":
            raise RuntimeError("Git operation failed: push; inspect repository status locally")
        return ""
    monkeypatch.setattr("scripts.publish_daily_report.run_git", git)
    result = publish(source, root=tmp_path, push=True)
    assert result["status"] == "push_failed" and result["commit"] == "c" * 40
    added = next(call for call in calls if call[0] == "add")
    assert set(added[2:]) == {result["report"], "html/skills/daily/index.json", "github.html"}
    assert "private-record.json" not in added
    committed = next(call for call in calls if call[0] == "commit")
    assert set(committed[committed.index("--") + 1:]) == set(added[2:])
    assert calls[-1] == ("push", "origin", "main")
