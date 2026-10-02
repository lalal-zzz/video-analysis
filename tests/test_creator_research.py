from __future__ import annotations

from pathlib import Path

import pytest

from mcp_server.research import CreatorWatchlistStore
from mcp_server.service import VideoService
from mcp_server.storage import Paths


def creator(name: str = "财经作者", platform: str = "youtube") -> dict:
    return {"name": name, "platform": platform, "url": f"https://www.youtube.com/@{name}"}


def config() -> dict:
    return {"description": "固定博主研究", "creators": [creator()]}


def test_watchlist_store_is_separate_from_domains(tmp_path: Path):
    paths = Paths(tmp_path / "data", tmp_path / "state")
    store = CreatorWatchlistStore(paths)
    result = store.result("create", "stocks", config())
    assert result["watchlist"]["name"] == "stocks"
    assert store.list() == ["stocks"]
    assert store.result("read", "stocks")["watchlist"]["creators"][0]["platform"] == "youtube"
    assert (paths.root / "watchlists" / "stocks.json").is_file()
    assert not (paths.domains / "stocks.json").exists()


def test_watchlist_requires_a_creator(tmp_path: Path):
    store = CreatorWatchlistStore(Paths(tmp_path / "data", tmp_path / "state"))
    with pytest.raises(ValueError, match="at least one creator"):
        store.result("create", "empty", {"creators": []})
    with pytest.raises(ValueError, match="platform"):
        store.result("create", "bad-platform", {"creators": [{**creator(), "platform": "unknown"}]})


@pytest.mark.asyncio
async def test_research_watchlist_returns_transcription_items(tmp_path: Path, monkeypatch):
    service = VideoService(Paths(tmp_path / "data", tmp_path / "state"))
    try:
        service.watchlists.result("create", "stocks", {"creators": [creator()]})
        calls = []

        async def latest(platform, authors, limit, refresh=False):
            calls.append((platform, authors, limit, refresh))
            return {"status": "ok", "videos": [{"platform": platform, "video_id": "v1", "url": authors[0]}]}

        monkeypatch.setattr(service, "latest", latest)
        result = await service.research_watchlist("stocks", refresh=True)
        assert result["status"] == "ok"
        assert result["transcription_items"] == result["videos"]
        assert calls == [("youtube", ["https://www.youtube.com/@财经作者"], 5, True)]
        with pytest.raises(ValueError, match="1-50"):
            await service.research_watchlist("stocks", max_per_creator=0)
    finally:
        await service.close()
