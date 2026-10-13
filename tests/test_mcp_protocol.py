"""Exercise real JSON-RPC over a persistent STDIO connection, not a closed pipe."""
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_entrypoint_suppresses_http_request_urls(monkeypatch):
    import logging
    from mcp_server import server

    previous = {name: logging.getLogger(name).level for name in ("httpx", "httpcore")}
    monkeypatch.setattr(server.mcp, "run", lambda **kwargs: None)
    try:
        server.main()
        assert all(not logging.getLogger(name).isEnabledFor(logging.INFO) for name in previous)
    finally:
        for name, level in previous.items():
            logging.getLogger(name).setLevel(level)


@pytest.mark.asyncio
async def test_stdio_discovery_calls_and_background_job(tmp_path):
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(tmp_path),
        env={"VIDEO_ANALYSIS_DATA_DIR": str(tmp_path / "data"), "VIDEO_ANALYSIS_STATE_DIR": str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1"})
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"batch_download", "get_job", "read_artifact", "manage_domain", "wait_for_platform_login",
                    "save_daily_research", "get_daily_research", "evaluate_daily_forecasts"} <= names
            result = await session.call_tool("get_system_status", {})
            assert not result.isError
            assert result.structuredContent["status"] == "ok"
            journal = await session.call_tool("get_daily_research", {})
            assert journal.structuredContent == {"status": "ok", "trading_dates": []}
            saved = await session.call_tool("save_daily_research", {"record": {
                "trading_date": "2025-01-06", "cutoff_at": "2025-01-06T20:00:00+08:00",
                "market": {"trading_date": "2025-01-06", "is_trading_day": True, "stage": "close",
                           "calendar_source_url": "https://www.sse.com.cn/", "metrics": {}},
                "report": "Simulated protocol test: no transcripts, market evidence unavailable", "gaps": ["No market data"]}})
            assert saved.structuredContent["status"] == "ok"
            read_back = await session.call_tool("get_daily_research", {"trading_date": "2025-01-06", "revision": saved.structuredContent["revision"]})
            assert read_back.structuredContent["record"]["gaps"] == ["No market data"]
            scored = await session.call_tool("evaluate_daily_forecasts", {"previous_trading_date": "2025-01-06", "market": {
                "trading_date": "2025-01-07", "is_trading_day": True, "stage": "close",
                "previous_trading_date": "2025-01-06", "calendar_source_url": "https://www.sse.com.cn/", "metrics": {}}})
            assert scored.structuredContent["baseline_status"] == "late_record"
            batch = await session.call_tool("batch_download", {"videos": [{"platform": "youtube", "url": "file:///forbidden"}, {"platform": "unsupported", "url": "https://example.com"}]})
            assert batch.structuredContent["status"] == "running"
            result = await session.call_tool("get_job", {"job_id": batch.structuredContent["job_id"], "wait_seconds": 10})
            assert result.structuredContent["failed"] == 2
            assert result.structuredContent["completed"] == 2
            assert not result.isError
            invalid = await session.call_tool("manage_subscriptions", {"action": "list", "domain": "../escape"})
            assert invalid.structuredContent["code"] == "invalid_input"
