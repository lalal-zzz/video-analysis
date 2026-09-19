import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from cache.base import BaseCache
from config.settings import Settings
from models.cache import CacheEntry, CacheStatus
from models.search import SearchQuery, SearchResult
from models.transcript import VideoTranscript


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _video_cache_key(platform: str, video_id: str) -> str:
    return f"video:{platform}:{video_id}"


def _query_cache_key(query: SearchQuery) -> str:
    return f"query:{query.cache_key()}"


class DiskCache(BaseCache):
    def __init__(self, settings: Settings | None = None) -> None:
        cfg = (settings or Settings()).cache
        self._storage_dir = Path(cfg.storage_dir)
        self._video_dir = self._storage_dir / "video"
        self._query_dir = self._storage_dir / "query"
        self._video_ttl = timedelta(hours=cfg.video_ttl_hours)
        self._query_ttl = timedelta(hours=cfg.query_ttl_hours)
        self._video_dir.mkdir(parents=True, exist_ok=True)
        self._query_dir.mkdir(parents=True, exist_ok=True)
        self._hits: int = 0
        self._misses: int = 0

    def _entry_path(self, key: str) -> Path:
        return self._video_dir / f"{_key_hash(key)}.json"

    def _query_entry_path(self, key: str) -> Path:
        return self._query_dir / f"{_key_hash(key)}.json"

    def _read_entry(self, path: Path) -> CacheEntry | None:
        try:
            data = json.loads(path.read_bytes())
            entry = CacheEntry(**data)
            if entry.is_expired:
                path.unlink(missing_ok=True)
                return None
            return entry
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    def _write_entry(self, path: Path, entry: CacheEntry) -> None:
        path.write_text(entry.model_dump_json(), encoding="utf-8")

    async def get_video(self, platform: str, video_id: str) -> VideoTranscript | None:
        key = _video_cache_key(platform, video_id)
        path = self._entry_path(key)
        entry = await asyncio.to_thread(self._read_entry, path)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        return VideoTranscript(**entry.value)

    async def set_video(self, transcript: VideoTranscript) -> None:
        key = _video_cache_key(transcript.video.platform, transcript.video.video_id)
        path = self._entry_path(key)
        entry = CacheEntry(
            key=key,
            value=json.loads(transcript.model_dump_json()),
            expires_at=datetime.now() + self._video_ttl,
        )
        await asyncio.to_thread(self._write_entry, path, entry)

    async def get_query(self, query: SearchQuery) -> SearchResult | None:
        key = _query_cache_key(query)
        path = self._query_entry_path(key)
        entry = await asyncio.to_thread(self._read_entry, path)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        return SearchResult(**entry.value)

    async def set_query(self, result: SearchResult) -> None:
        key = _query_cache_key(result.query)
        path = self._query_entry_path(key)
        entry = CacheEntry(
            key=key,
            value=json.loads(result.model_dump_json()),
            expires_at=datetime.now() + self._query_ttl,
        )
        await asyncio.to_thread(self._write_entry, path, entry)

    async def clear_expired(self) -> int:
        cleared = 0
        for d in (self._video_dir, self._query_dir):
            for f in d.iterdir():
                if f.suffix == ".json":
                    entry = await asyncio.to_thread(self._read_entry, f)
                    if entry is None:
                        cleared += 1
        return cleared

    @property
    def status(self) -> CacheStatus:
        video_count = len(list(self._video_dir.glob("*.json")))
        query_count = len(list(self._query_dir.glob("*.json")))
        return CacheStatus(
            video_hits=self._hits,
            video_misses=self._misses,
            query_hits=0,
            query_misses=0,
            total_entries=video_count + query_count,
        )