"""Validate a built wheel from an unrelated working directory with real MCP IO."""
import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="video-analysis-wheel-") as folder:
        root = Path(folder)
        target = root / "installed"
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)], check=True, capture_output=True)
        # Isolated interpreter ignores PYTHONPATH and the source working directory.
        code = (
            "import sys,runpy;sys.path.insert(0,sys.argv[1]);"
            "import mcp_server,cache,config,log,exceptions,data_manager;"
            "assert all(m.__file__.startswith(sys.argv[1]) for m in (mcp_server,cache,config,log,exceptions,data_manager));"
            "runpy.run_module('mcp_server.server',run_name='__main__')"
        )
        params = StdioServerParameters(command=sys.executable, args=["-I", "-c", code, str(target)], cwd=str(root),
            env={"VIDEO_ANALYSIS_DATA_DIR": str(root / "data"), "VIDEO_ANALYSIS_STATE_DIR": str(root / "state")})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool("get_system_status", {})
                assert not result.isError and result.structuredContent["status"] == "ok"
                print(f"Wheel import, isolated STDIO startup and {len(listed.tools)} tools verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    asyncio.run(check(parser.parse_args().wheel.resolve()))
