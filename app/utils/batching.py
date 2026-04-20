import asyncio
from typing import Any, Callable, Awaitable
import structlog

log = structlog.get_logger()


class AsyncBatcher:
    """
    Collects incoming items for a short window (max_wait_ms)
    then processes them as a single batch. Falls back gracefully
    on handler errors, resolving each future individually.
    """

    def __init__(
        self,
        handler: Callable[[list[Any]], Awaitable[list[Any]]],
        max_batch_size: int = 16,
        max_wait_ms: int = 10,
        name: str = "batcher",
    ):
        self.handler = handler
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self.name = name
        self.queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Must be called inside a running event loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._worker(), name=f"batcher-{self.name}")

    async def submit(self, item: Any) -> Any:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self.queue.put((item, future))
        return await future

    async def _worker(self) -> None:
        while True:
            try:
                item, fut = await self.queue.get()
                batch: list[tuple[Any, asyncio.Future]] = [(item, fut)]

                # Collect more items within the wait window
                deadline = asyncio.get_running_loop().time() + self.max_wait_ms / 1000
                while len(batch) < self.max_batch_size:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        extra = self.queue.get_nowait()
                        batch.append(extra)
                    except asyncio.QueueEmpty:
                        await asyncio.sleep(min(remaining, 0.001))

                inputs = [b[0] for b in batch]
                futures = [b[1] for b in batch]

                try:
                    results = await self.handler(inputs)
                    for future, result in zip(futures, results):
                        if not future.done():
                            future.set_result(result)
                except Exception as exc:
                    log.error("batcher_handler_error", batcher=self.name, error=str(exc))
                    for future in futures:
                        if not future.done():
                            future.set_exception(exc)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("batcher_worker_error", batcher=self.name, error=str(exc))
                await asyncio.sleep(0.1)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
