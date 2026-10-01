from __future__ import annotations

import enum
from typing import Any


class SystemState(str, enum.Enum):
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"


class ModuleStatus(str, enum.Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    DISABLED = "disabled"


class Lifecycle:
    def __init__(self) -> None:
        self.state = SystemState.STARTING
        self._listeners: list[Any] = []

    def transition(self, state: SystemState) -> None:
        self.state = state
        for listener in self._listeners:
            listener(state)

    def on_change(self, listener: Any) -> None:
        self._listeners.append(listener)