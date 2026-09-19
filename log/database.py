from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any

from models.log import LogEntry


_LOG_DIR: Path | None = None


def set_log_dir(path: str | Path) -> None:
    global _LOG_DIR
    _LOG_DIR = Path(path)


def _get_log_dir() -> Path:
    if _LOG_DIR is not None:
        return _LOG_DIR
    default = Path("data") / "logs"
    default.mkdir(parents=True, exist_ok=True)
    return default


def _log_path(dt: date | None = None) -> Path:
    d = dt or date.today()
    return _get_log_dir() / f"{d.isoformat()}.jsonl"


def append(entry: LogEntry | dict[str, Any]) -> None:
    if isinstance(entry, LogEntry):
        entry = entry.model_dump(mode="json", exclude_none=True)
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_event(
    level: str,
    module: str,
    event: str,
    message: str = "",
    *,
    pipeline: str | None = None,
    pipeline_id: str | None = None,
    detail: dict[str, Any] | None = None,
    error: str | None = None,
    duration_ms: float | None = None,
) -> None:
    append(LogEntry(
        level=level,
        module=module,
        event=event,
        message=message,
        pipeline=pipeline,
        pipeline_id=pipeline_id,
        detail=detail,
        error=error,
        duration_ms=duration_ms,
    ))


def query(
    level: str | None = None,
    module: str | None = None,
    pipeline: str | None = None,
    event: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    log_dir = _get_log_dir()
    log_files = sorted(log_dir.glob("*.jsonl"), reverse=True)

    if since:
        since_str = since.date().isoformat()
        log_files = [f for f in log_files if f.stem >= since_str]

    for lf in log_files:
        if len(results) >= offset + limit:
            break
        with open(lf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if level and entry.get("level") != level:
                    continue
                if module and (entry.get("module") or "").find(module) == -1:
                    continue
                if pipeline and entry.get("pipeline") != pipeline:
                    continue
                if event and entry.get("event") != event:
                    continue
                ts = datetime.fromisoformat(entry["timestamp"])
                if since and ts < since:
                    continue
                if until and ts > until:
                    continue
                results.append(entry)
                if len(results) >= offset + limit:
                    break

    return results[offset:]


def tail(n: int = 20) -> list[dict[str, Any]]:
    return query(limit=n)


def stats() -> dict[str, Any]:
    counts: dict[str, int] = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0}
    pipelines: dict[str, int] = {}
    total = 0
    log_dir = _get_log_dir()
    for lf in sorted(log_dir.glob("*.jsonl"), reverse=True)[:7]:
        with open(lf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                lvl = entry.get("level", "INFO")
                if lvl in counts:
                    counts[lvl] += 1
                pl = entry.get("pipeline") or "_none"
                pipelines[pl] = pipelines.get(pl, 0) + 1
    return {"total": total, "by_level": counts, "by_pipeline": pipelines, "log_files": len(list(_get_log_dir().glob("*.jsonl")))}


def list_pipelines() -> list[str]:
    pipelines: set[str] = set()
    log_dir = _get_log_dir()
    for lf in log_dir.glob("*.jsonl"):
        with open(lf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pl = entry.get("pipeline") or "_none"
                pipelines.add(pl)
    return sorted(pipelines - {"_none"})