import asyncio
import time
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


class Scheduler:
    def __init__(
        self,
        max_concurrency: int = 3,
        request_delay: float = 1.0,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._delay = request_delay
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def run(
        self,
        coro_factory: Callable[..., Coroutine[Any, Any, T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        async with self._semaphore:
            await self._throttle()
            return await coro_factory(*args, **kwargs)

    async def run_all(
        self,
        coro_factories: list[tuple[Callable[..., Coroutine[Any, Any, T]], tuple, dict]],
    ) -> list[T]:
        tasks = [self.run(fn, *args, **kwargs) for fn, args, kwargs in coro_factories]
        results = await asyncio.gather(*tasks, return_exceptions=True)  # type: ignore[misc]
        return [r for r in results if not isinstance(r, BaseException)]

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._delay:
                await asyncio.sleep(self._delay - elapsed)
            self._last_request_time = time.monotonic()

    @property
    def available_permits(self) -> int:
        return self._semaphore._value  # type: ignore[attr-defined]