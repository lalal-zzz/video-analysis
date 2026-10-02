"""Persistent creator watchlists used by the research workflow."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from models.creator_research import CreatorWatchlist
from mcp_server.storage import Paths, atomic_json, identifier, platform_name


class CreatorWatchlistStore:
    """Read and write fixed-creator lists without mixing them with cookies."""

    def __init__(self, paths: Paths) -> None:
        self.root = paths.root / "watchlists"

    def _file(self, name: str) -> Path:
        identifier(name)
        return self.root / f"{name}.json"

    def list(self) -> list[str]:
        return sorted(path.stem for path in self.root.glob("*.json") if path.is_file())

    def read(self, name: str) -> CreatorWatchlist:
        file = self._file(name)
        if not file.is_file():
            raise FileNotFoundError("Unknown creator watchlist")
        return CreatorWatchlist.model_validate_json(file.read_text(encoding="utf-8"))

    def save(self, name: str, config: dict[str, Any], *, create: bool) -> CreatorWatchlist:
        file = self._file(name)
        if create and file.exists():
            raise ValueError("Creator watchlist already exists")
        if not create and not file.exists():
            raise FileNotFoundError("Unknown creator watchlist")
        model = CreatorWatchlist.model_validate({**config, "name": name, "updated_at": datetime.now()})
        if not model.creators:
            raise ValueError("Creator watchlist requires at least one creator")
        for creator in model.creators:
            platform_name(creator.platform)
            if not creator.url.strip().startswith(("https://", "http://")):
                raise ValueError("creator url must be an http(s) URL")
        atomic_json(file, model.model_dump(mode="json"))
        return model

    def result(self, action: str, name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        if action == "list":
            return {"status": "ok", "watchlists": self.list()}
        if action == "read":
            return {"status": "ok", "watchlist": self.read(name).model_dump(mode="json")}
        if action in {"create", "update"}:
            if config is None:
                raise ValueError("config is required")
            model = self.save(name, config, create=action == "create")
            return {"status": "ok", "watchlist": model.model_dump(mode="json")}
        raise ValueError("action must be list, read, create or update")
