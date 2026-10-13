"""Export a saved daily revision and optionally push only its public report assets."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from models.daily_research import SavedDailyResearch

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    r"(?i)(?:SESSDATA|bili_jct|authorization|api[_-]?key|password|cookie)\s*[:=]\s*\S+",
    r"(?i)(?:github_pat_|ghp_|sk-)[A-Za-z0-9_-]{16,}",
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    r"(?i)(?:(?<![A-Za-z0-9])[A-Z]:[\\/]|file://|(?<![:\w./])/(?:Users|home)/)",
    r"account_following|following_count|(?:你|我|用户|个人)(?:的)?关注列表",
    r'"(?:full_text|segments|cookies|account_id)"\s*:',
)


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        # No credentials, command output or signed URLs are echoed in a public report.
        raise RuntimeError(f"Git operation failed: {args[0]}; inspect repository status locally")
    return result.stdout.strip()


def public_report(report: str) -> str:
    # Internal artifact IDs/absolute archive locations belong only in local reports.
    text = re.sub(r"\btranscripts/[\w./-]+\.json", "[内部转录引用省略]", report)
    for pattern in FORBIDDEN:
        if re.search(pattern, text):
            raise ValueError("Report contains potentially private content; review before publishing")
    if re.search(r"\{\{[^}]+\}\}", text):
        raise ValueError("Unfilled report template cannot be published")
    if not text.strip():
        raise ValueError("Public report cannot be empty")
    return text.rstrip() + "\n"


def publish(record_path: Path, root: Path = ROOT, push: bool = False) -> dict[str, Any]:
    saved = SavedDailyResearch.model_validate_json(record_path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"[a-f0-9]{32}", saved.revision):
        raise ValueError("Saved revision must be a generated UUID hex ID")
    if not saved.record.transcript_artifacts and not saved.record.market.metrics:
        raise ValueError("No transcript or market evidence; do not publish an empty failure report")
    text = public_report(saved.record.report)
    if push:
        if run_git(root, "branch", "--show-current") != "main":
            raise ValueError("Daily publishing requires main; old branches must not be pushed")
        remote = run_git(root, "remote", "get-url", "origin")
        if remote.rstrip("/") not in ("https://github.com/lalal-zzz/video-analysis.git", "https://github.com/lalal-zzz/video-analysis", "git@github.com:lalal-zzz/video-analysis.git"):
            raise ValueError("Unexpected origin repository; refusing automatic publication")
        if run_git(root, "diff", "--cached", "--name-only"):
            raise ValueError("Existing staged changes; preserve them and stop automatic publication")
        if run_git(root, "diff", "--name-only", "--", "github.html", "html/skills/daily"):
            raise ValueError("Existing edits to publication assets need review before automatic publication")
    day = saved.record.trading_date.isoformat()
    relative = f"html/skills/daily/{day}/{saved.revision}.md"
    report_path = root / relative
    if report_path.exists() and report_path.read_text(encoding="utf-8") != text:
        raise ValueError("Published revision cannot be overwritten; save a new research revision")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    index_path = root / "html/skills/daily/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"reports": []}
    item = {"trading_date": day, "revision": saved.revision, "path": relative,
            "saved_at": saved.saved_at.isoformat(), "creators": len(saved.record.coverage),
            "transcripts": len(saved.record.transcript_artifacts), "stage": saved.record.market.stage}
    reports = [r for r in index["reports"] if not (r["trading_date"] == day and r["revision"] == saved.revision)]
    reports.append(item)
    reports.sort(key=lambda r: (r["trading_date"], r["saved_at"], r["revision"]), reverse=True)
    index_path.write_text(json.dumps({"reports": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    page_path = root / "github.html"
    page = page_path.read_text(encoding="utf-8")
    if '<script id="daily-data" type="application/json">' not in page:
        raise ValueError("Showcase is missing the daily report index slot")
    embedded = json.dumps(reports, ensure_ascii=False).replace("<", "\\u003c")
    page = re.sub(r'(<script id="daily-data" type="application/json">).*?(</script>)', lambda m: m[1] + embedded + m[2], page, flags=re.DOTALL)
    page_path.write_text(page, encoding="utf-8")
    result: dict[str, Any] = {"status": "exported", "report": relative, "revision": saved.revision}
    if push:
        paths = [relative, "html/skills/daily/index.json", "github.html"]
        run_git(root, "add", "--", *paths)
        if run_git(root, "diff", "--cached", "--name-only"):
            run_git(root, "diff", "--cached", "--check")
            run_git(root, "commit", "-m", f"Publish A-share daily review for {day}", "--", *paths)
            result["commit"] = run_git(root, "rev-parse", "HEAD")
        else:
            result["commit"] = None
        # A previous local commit can still be pending, so normal push also runs on no-change retries.
        try:
            run_git(root, "push", "origin", "main")
            result["status"] = "pushed"
        except RuntimeError as error:
            result.update(status="push_failed", error=str(error))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--push", action="store_true", help="Explicitly authorized publication to GitHub origin/main")
    args = parser.parse_args()
    result = publish(args.record, push=args.push)
    print(json.dumps(result, ensure_ascii=True))
    if result["status"] == "push_failed":
        sys.exit(1)
