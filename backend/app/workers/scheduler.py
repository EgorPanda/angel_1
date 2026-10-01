from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from app.core.logging import get_logger, log_extra
from app.modules.reminders import events as reminder_events
from app.modules.reminders.service import occurrence_key

logger = get_logger("workers.scheduler")


class Scheduler:
    def __init__(self, core, interval: float = 5.0) -> None:
        self.core = core
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._running = False
        self.last_tick: float = 0.0
        self.last_scan_at: datetime | None = None
        self.scanned = 0
        self.triggered = 0
        self.last_error: str = ""

    @property
    def status(self) -> str:
        return "running" if self._running else "stopped"

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("scheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._scan()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.error("scheduler scan failed: %s", exc, exc_info=True)
            self.last_tick = time.time()
            await asyncio.sleep(self.interval)

    async def _scan(self) -> None:
        reminders_module = self.core.modules.get("reminders")
        if reminders_module is None or reminders_module.service is None:
            return
        service = reminders_module.service
        due = await asyncio.to_thread(service.due, datetime.now(timezone.utc))
        self.scanned += len(due)
        self.last_scan_at = datetime.now(timezone.utc)
        for reminder in due:
            await asyncio.to_thread(self._dispatch, service, reminder)
        if due:
            logger.info("scheduler dispatched %s due reminders", len(due))

    def _dispatch(self, service, reminder) -> None:
        key = occurrence_key(reminder.trigger_at)
        run = service.run_for_occurrence(str(reminder.id), key)
        if run is not None:
            return
        run = service.create_run(reminder)
        self.triggered += 1
        logger.info("reminder triggered", extra=log_extra({"reminder_id": str(reminder.id), "run_id": str(run.id)}))
        self.core.publish(
            self.core.event(
                event_type=reminder_events.REMINDER_TRIGGERED,
                aggregate_type="reminder",
                aggregate_id=str(reminder.id),
                payload={"run_id": str(run.id), "reminder_id": str(reminder.id), "text": reminder.text},
                user_id=reminder.user_id,
            )
        )

    def health_check(self) -> tuple[bool, str]:
        if not self._running:
            return False, "scheduler not running"
        return True, f"ok (last tick {time.time() - self.last_tick:.1f}s ago)"