"""Durable progress for batches; interrupted processes never look successful."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp_server.storage import atomic_json, batch_result, failure, identifier


class Jobs:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.tasks: dict[str, asyncio.Task] = {}
        self.records: dict[str, dict[str, Any]] = {}

    def get(self, job_id: str) -> dict[str, Any]:
        identifier(job_id)
        file = self.root / f"{job_id}.json"
        if job_id not in self.records:
            if not file.is_file():
                raise FileNotFoundError("Unknown job")
            record = json.loads(file.read_text(encoding="utf-8"))
            if record["status"] == "running":
                record["status"] = "interrupted"
                atomic_json(file, record)
            self.records[job_id] = record
        return self.records[job_id]

    def submit(self, kind: str, items: list[dict[str, Any]], worker: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]], concurrency: int) -> dict[str, Any]:
        if not 1 <= len(items) <= 500:
            raise ValueError("batch size must be 1-500")
        if sum(not t.done() for t in self.tasks.values()) >= 8:
            raise ValueError("Too many active batches")
        job_id = uuid.uuid4().hex
        record = {"job_id": job_id, "kind": kind, "status": "running", "total": len(items), "completed": 0, "results": [None] * len(items)}
        self.records[job_id] = record
        atomic_json(self.root / f"{job_id}.json", record)
        self.tasks[job_id] = asyncio.create_task(self._run(record, items, worker, concurrency))
        return {"status": "running", "job_id": job_id, "total": len(items)}

    async def _run(self, record: dict[str, Any], items: list[dict[str, Any]], worker: Callable, concurrency: int) -> None:
        semaphore = asyncio.Semaphore(max(1, min(concurrency, 8)))

        async def one(index: int, item: dict[str, Any]) -> None:
            async with semaphore:
                try:
                    result = await worker(item)
                except Exception as exc:
                    result = failure(exc)
                record["results"][index] = {"index": index, **result}
                record["completed"] += 1
                atomic_json(self.root / f"{record['job_id']}.json", record)

        try:
            await asyncio.gather(*(one(i, item) for i, item in enumerate(items)))
            record.update(batch_result(record["results"]))
        except asyncio.CancelledError:
            record["status"] = "interrupted"
            raise
        finally:
            atomic_json(self.root / f"{record['job_id']}.json", record)
            self.tasks.pop(record["job_id"], None)

    async def wait(self, job_id: str, seconds: int) -> dict[str, Any]:
        record = self.get(job_id)
        task = self.tasks.get(job_id)
        if task:
            await asyncio.wait({task}, timeout=max(0, min(seconds, 30)))
        return dict(record)

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
