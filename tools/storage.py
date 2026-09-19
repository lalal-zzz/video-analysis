"""工具调用结果持久化."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from models.domain import ToolCallRecord

logger = logging.getLogger(__name__)


def save_tool_result(domain: str, record: ToolCallRecord) -> Path:
    """保存工具调用结果到 data/{domain}/tools/{tool_name}_{date}.json."""
    tool_dir = Path("data") / domain / "tools"
    tool_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    safe_name = record.tool_name.replace(" ", "_").replace("/", "_")
    filepath = tool_dir / f"{safe_name}_{date_str}.json"

    # 追加到已存在文件
    records: list[dict] = []
    if filepath.exists():
        try:
            records = json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            records = []

    records.append(json.loads(record.model_dump_json()))
    filepath.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def load_tool_results(domain: str, tool_name: str) -> list[dict]:
    """加载指定工具的调用结果（最近一次）."""
    tool_dir = Path("data") / domain / "tools"
    if not tool_dir.exists():
        return []
    safe_name = tool_name.replace(" ", "_").replace("/", "_")
    files = sorted(tool_dir.glob(f"{safe_name}_*.json"), reverse=True)
    if not files:
        return []
    latest = files[0]
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
