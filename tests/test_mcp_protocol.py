"""Exercise real JSON-RPC over a persistent STDIO connection, not a closed pipe."""
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_discovery_calls_and_background_job(tmp_path):
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(tmp_path),
        env={"VIDEO_ANALYSIS_DATA_DIR": str(tmp_path / "data"), "VIDEO_ANALYSIS_STATE_DIR": str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1"})
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"batch_download", "get_job", "read_artifact", "manage_domain", "wait_for_platform_login"} <= names
            result = await session.call_tool("get_system_status", {})
            assert not result.isError
            assert result.structuredContent["status"] == "ok"
            batch = await session.call_tool("batch_download", {"videos": [{"platform": "youtube", "url": "file:///forbidden"}, {"platform": "unsupported", "url": "https://example.com"}]})
            assert batch.structuredContent["status"] == "running"
            result = await session.call_tool("get_job", {"job_id": batch.structuredContent["job_id"], "wait_seconds": 10})
            assert result.structuredContent["failed"] == 2
            assert result.structuredContent["completed"] == 2
            assert not result.isError
            invalid = await session.call_tool("manage_subscriptions", {"action": "list", "domain": "../escape"})
            assert invalid.structuredContent["code"] == "invalid_input"
