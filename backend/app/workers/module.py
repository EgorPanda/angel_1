from __future__ import annotations

import asyncio
import uuid

from app.core.logging import get_logger, log_extra
from app.modules.reminders import events as reminder_events
from app.workers.runner import WorkerPool
from app.workers.scheduler import Scheduler

logger = get_logger("workers.module")

TASK_PROCESS_REMINDER = "process_reminder"
TASK_SYNC_MARKDOWN = "sync_markdown"


class WorkersModuleConnector:
    def __init__(self, core) -> None:
        self.core = core
        self.scheduler: Scheduler | None = None

    def install(self) -> None:
        pool = self.core.worker_pool
        pool.register(TASK_PROCESS_REMINDER, self._process_reminder)
        pool.register(TASK_SYNC_MARKDOWN, self._sync_markdown)
        self.core.events.subscribe(reminder_events.REMINDER_TRIGGERED, self._on_reminder_triggered)
        self.scheduler = Scheduler(self.core, self.core.settings.scheduler_interval)
        self.core.health.register("scheduler", lambda: (True, "ok") if self.scheduler and self.scheduler.status == "running" else (False, "scheduler not running"))
        self.core.health.register("workers", lambda: (True, pool.status()) if pool.status()["running"] else (False, "worker pool not running"))

    async def start(self) -> None:
        await self.core.worker_pool.start()
        await self.scheduler.start()

    async def stop(self) -> None:
        if self.scheduler:
            await self.scheduler.stop()
        await self.core.worker_pool.stop()

    async def _on_reminder_triggered(self, event) -> None:
        run_id = event.payload.get("run_id")
        if not run_id:
            return
        try:
            self.core.worker_pool.enqueue(TASK_PROCESS_REMINDER, {"run_id": run_id})
        except KeyError:
            logger.error("reminder triggered before worker registered")

    async def _process_reminder(self, payload, item) -> None:
        run_id = payload["run_id"]
        core = self.core
        reminders = core.modules.get("reminders")
        notifications = core.modules.get("notifications")
        if reminders is None or notifications is None:
            raise RuntimeError("reminder or notification module not available")
        run = await asyncio.to_thread(reminders.service.get_run, run_id)
        if run.status == "processed":
            return
        await asyncio.to_thread(reminders.service.update_run, run_id, "processing", attempts=run.attempts + 1, task_id=item.id)
        reminder = await asyncio.to_thread(reminders.service.get, str(run.reminder_id))
        user_id = str(reminder.user_id) if reminder.user_id else None
        outcome = None
        if core.llm is not None and getattr(core, "ai_runtime", None) is not None:
            outcome = await core.ai_runtime.chat(
                text=(
                    f"Наступил срок напоминания: «{reminder.text}»."
                    "Придумай короткое дружелюбное сообщение-напоминание для пользователя"
                    " и отправь его инструментом send_reminder_notification."
                ),
                user_id=user_id,
                tool_names=["send_reminder_notification"],
                kind="reminder_process",
            )
        result = {"outcome": outcome.status if outcome else "fallback", "text": reminder.text}
        if outcome is None or outcome.status not in ("completed", "awaiting_confirmation"):
            await asyncio.to_thread(notifications.service.send, reminder.text, "telegram", user_id, "Напоминание")
            result["mode"] = "template"
        else:
            result["mode"] = "ai"
        await asyncio.to_thread(reminders.service.update_run, run_id, "processed", result=result)

    async def _sync_markdown(self, payload, item) -> None:
        markdown = self.core.modules.get("markdown")
        if markdown is None or markdown.sync is None:
            return
        action = payload.get("action")
        if action == "note":
            await asyncio.to_thread(markdown.sync.sync_note, payload["note_id"])
        elif action == "delete":
            await asyncio.to_thread(markdown.sync.delete_note, payload["note_id"])
        elif action == "folder":
            await asyncio.to_thread(markdown.sync.sync_folder, payload["folder_id"])
        elif action == "full":
            await asyncio.to_thread(markdown.sync.full_sync)