from __future__ import annotations

from abc import ABC
from typing import Any

from app.core.events import EventHandler
from app.core.lifecycle import ModuleStatus
from app.core.module_config import ConfigField


class Module(ABC):
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    description_ru: str = ""
    dependencies: list[str] = []
    capabilities: list[str] = []
    enabled: bool = True
    config_fields: list[ConfigField] = []

    def __init__(self) -> None:
        self.status = ModuleStatus.STOPPED
        self.tools: list[Any] = []
        self.routers: list[Any] = []
        self.event_subscriptions: dict[str, EventHandler] = {}
        self.core: Any = None

    async def start(self) -> None:
        self.status = ModuleStatus.RUNNING

    async def stop(self) -> None:
        self.status = ModuleStatus.STOPPED

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    async def reconfigure(self) -> None:
        """Перестраивает модуль под текущую конфигурацию (после stop, перед start)."""
        return None

    def on_register(self, core: Any) -> None:
        self.core = core
        for tool in self.tools:
            core.tools.register(tool)
        for event_type, handler in self.event_subscriptions.items():
            core.events.subscribe(event_type, handler)
        if self.routers:
            core.include_module_router(self)

    def on_unregister(self, core: Any) -> None:
        for tool in self.tools:
            core.tools.unregister(tool.name)
        for event_type, handler in self.event_subscriptions.items():
            core.events.unsubscribe(event_type, handler)

    def health_check(self) -> tuple[bool, str]:
        return True, "ok"

    def info(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "description_ru": self.description_ru or self.description,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
        }

    # ----- конфигурация модуля -----

    def config_values(self) -> dict:
        """Объединяет дефолты полей с сохранёнными в БД значениями (БД приоритетнее)."""
        stored = {}
        if self.core is not None:
            stored = self.core.module_config.all(self.name)
        result: dict[str, Any] = {}
        for field in self.config_fields:
            value = stored.get(field.key, field.default)
            result[field.key] = field.cast(value) if value is not None else field.default
        return result

    def save_config(self, values: dict) -> dict:
        """Сохраняет только заявленные поля, приводит значения к типам полей."""
        if self.core is None:
            raise RuntimeError("module not registered")
        cleaned: dict[str, Any] = {}
        for field in self.config_fields:
            if field.key in values:
                cleaned[field.key] = field.cast(values[field.key])
        if cleaned:
            self.core.module_config.set_many(self.name, cleaned)
        return cleaned