from __future__ import annotations

import asyncio
import time
import uuid

from app.core.logging import get_logger, log_extra

logger = get_logger("workers.pool")


class WorkItem:
    def __init__(self, task_id: str, kind: str, payload: dict, retries: int) -> None:
        self.id = task_id
        self.kind = kind
        self.payload = payload
        self.remaining_retries = retries
        self.delay_until: float = 0.0
        self.created_at = time.time()
        self.attempts = 0

    def delay(self, seconds: float) -> None:
        self.delay_until = time.monotonic() + seconds


class WorkerPool:
    def __init__(self, concurrency: int = 2, retry_policy: int = 3, retry_delay: float = 5.0,
                 requeue_interval: float = 2.0) -> None:
        self.concurrency = max(1, concurrency)
        self.retry_policy = retry_policy
        self.retry_delay = retry_delay
        self.requeue_interval = requeue_interval
        self._handlers: dict[str, object] = {}
        self._queue: asyncio.Queue[WorkItem] = asyncio.Queue()
        self._consumers: list[asyncio.Task] = []
        self._running = False
        self._stats = {"processed": 0, "failed": 0, "enqueued": 0, "active": 0}

    def register(self, kind: str, handler) -> None:
        self._handlers[kind] = handler

    def handler_for(self, kind: str):
        return self._handlers.get(kind)

    @property
    def available_kinds(self) -> list[str]:
        return list(self._handlers.keys())

    def enqueue(self, kind: str, payload: dict, task_id: str | None = None, retries: int | None = None) -> str:
        if kind not in self._handlers:
            raise KeyError(f"no worker handler registered for {kind}")
        item = WorkItem(task_id or str(uuid.uuid4()), kind, payload, retries if retries is not None else self.retry_policy)
        self._queue.put_nowait(item)
        self._stats["enqueued"] += 1
        logger.info("task enqueued", extra=log_extra({"task_id": item.id, "kind": kind}))
        return item.id

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for _ in range(self.concurrency):
            self._consumers.append(asyncio.create_task(self._consume()))

    async def stop(self) -> None:
        self._running = False
        for task in self._consumers:
            task.cancel()
        for task in self._consumers:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._consumers.clear()

    async def _consume(self) -> None:
        while self._running:
            item = await self._queue.get()
            if item.delay_until and time.monotonic() < item.delay_until:
                await asyncio.sleep(self.requeue_interval)
                self._queue.put_nowait(item)
                self._queue.task_done()
                continue
            handler = self._handlers.get(item.kind)
            self._stats["active"] += 1
            item.attempts += 1
            try:
                if handler is None:
                    raise KeyError(f"no handler for {item.kind}")
                await handler(item.payload, item)
                self._stats["processed"] += 1
            except Exception as exc:  # noqa: BLE001
                self._stats["failed"] += 1
                if item.remaining_retries > 0:
                    item.remaining_retries -= 1
                    item.delay(self.retry_delay)
                    logger.warning("task failed, retrying (%s left): %s", item.remaining_retries, exc)
                    self._queue.put_nowait(item)
                else:
                    logger.error("task failed permanently: %s", exc, exc_info=True)
            finally:
                self._stats["active"] -= 1
                self._queue.task_done()

    def status(self) -> dict:
        return {
            "concurrency": self.concurrency,
            "queue_size": self._queue.qsize(),
            "running": self._running,
            "handlers": list(self._handlers.keys()),
            **self._stats,
        }