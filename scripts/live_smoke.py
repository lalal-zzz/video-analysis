"""Opt-in real downloads. Not collected by pytest; no login secrets are printed."""
import argparse
import asyncio
import json
from pathlib import Path

from mcp_server.service import VideoService
from mcp_server.storage import Paths


async def run(args: argparse.Namespace) -> None:
    root = Path(args.output).resolve()
    service = VideoService(Paths(root / "data", root / "state"))
    try:
        result = await service.media.download(args.platform, args.url, root / "downloads")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        await service.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=["bilibili", "youtube", "douyin"])
    parser.add_argument("url")
    parser.add_argument("--output", default="data/live-smoke")
    asyncio.run(run(parser.parse_args()))
