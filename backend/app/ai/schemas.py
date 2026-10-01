from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentOutcome:
    status: str
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    confirmation_id: str | None = None
    error: str = ""
    steps: int = 0
    usage: dict = field(default_factory=dict)


@dataclass
class AgentRequest:
    text: str
    user_id: str | None = None
    correlation_id: str | None = None
    tool_names: list[str] | None = None
    kind: str = "chat"
    max_steps: int = 8
    native_tools: bool = True