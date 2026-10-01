from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    role: str
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    call_id: str = ""


@dataclass
class Completion:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    usage: dict = field(default_factory=dict)


class LLMProvider(ABC):
    name: str = "base"
    supports_tool_calling: bool = True

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout: float = 60.0,
    ) -> Completion:
        ...

    @abstractmethod
    def available(self) -> bool:
        ...

    def health_check(self) -> tuple[bool, str]:
        try:
            ok = self.available()
            return ok, "ok" if ok else "provider unavailable"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"

    async def simple(self, text: str, temperature: float = 0.5, max_tokens: int = 512) -> str:
        completion = await self.complete(
            [Message(role="user", content=text)], None, temperature=temperature, max_tokens=max_tokens
        )
        return completion.text