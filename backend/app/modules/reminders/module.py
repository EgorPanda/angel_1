from __future__ import annotations

from app.core.module import Module
from app.modules.reminders.api import build_router
from app.modules.reminders.service import RemindersService


class RemindersModule(Module):
    name = "reminders"
    version = "0.1.0"
    description = "Reminders with schedules, repetitions, state and run history."
    description_ru = "Напоминания: расписания, повторения, состояния и история запусков."
    capabilities = ["reminders.crud", "reminders.schedule", "reminders.repeat", "reminders.history"]
    dependencies = ["notes"]

    def __init__(self) -> None:
        super().__init__()
        self.service: RemindersService | None = None

    def on_register(self, core) -> None:
        self.service = RemindersService(core.session_factory, core.publish)
        from app.modules.reminders import tools as reminders_tools

        self.tools = reminders_tools.build_tools(self.service)
        self.routers = [build_router(self.service)]
        super().on_register(core)

    def health_check(self) -> tuple[bool, str]:
        if self.service is None:
            return False, "service not initialized"
        return True, "ok"

    def info(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
        }