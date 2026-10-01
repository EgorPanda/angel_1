from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger("events")


@dataclass
class Event:
    type: str
    aggregate_type: str = ""
    aggregate_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    user_id: str | None = None
    occurred_at: float = field(default_factory=time.time)


@dataclass
class Command:
    type: str
    aggregate_type: str = ""
    aggregate_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    user_id: str | None = None


EventHandler = Callable[[Event], Awaitable[None] | None]


class EventBus:
    def __init__(self, sink: Callable[[Event], None] | None = None) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._sink = sink
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._subscribers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        try:
            if self._sink is not None:
                self._sink(event)
        except Exception:
            logger.exception("event sink failed", exc_info=True)
        for handler in list(self._subscribers.get(event.type, [])):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    async with self._lock:
                        await result
            except Exception:
                logger.exception("event handler failed for %s", event.type, exc_info=True)

    async def publish_many(self, events: list[Event]) -> None:
        for event in events:
            await self.publish(event)


class InProcessCommandBus:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[Command], Any]] = {}

    def register(self, command_type: str, handler: Callable[[Command], Any]) -> None:
        self._handlers[command_type] = handler

    def dispatch(self, command: Command) -> Any:
        handler = self._handlers.get(command.type)
        if handler is None:
            raise KeyError(f"no handler for command {command.type}")
        return handler(command)