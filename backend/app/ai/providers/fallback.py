from __future__ import annotations

from app.ai.providers.base import Completion, LLMProvider, Message, ToolCall
from app.core.errors import LLMError
from app.core.logging import get_logger

logger = get_logger("llm.fallback")


class FallbackProvider(LLMProvider):
    name = "fallback"

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    @property
    def supports_tool_calling(self) -> bool:
        return self.primary.supports_tool_calling or self.fallback.supports_tool_calling

    async def complete(self, messages, tools=None, temperature=0.3, max_tokens=1024, timeout=60.0) -> Completion:
        try:
            return await self.primary.complete(messages, tools, temperature, max_tokens, timeout)
        except LLMError as primary_error:
            logger.warning("primary LLM failed, using fallback: %s", primary_error)
            try:
                return await self.fallback.complete(messages, tools, temperature, max_tokens, timeout)
            except LLMError as fallback_error:
                raise LLMError(f"primary and fallback LLM failed: {primary_error}; {fallback_error}") from fallback_error

    def available(self) -> bool:
        return self.primary.available() or self.fallback.available()

    def health_check(self) -> tuple[bool, str]:
        primary_ok = self.primary.available()
        if primary_ok:
            return True, f"primary ok ({self.primary.name})"
        fallback_ok = self.fallback.available()
        if fallback_ok:
            return True, f"primary down, fallback ok ({self.fallback.name})"
        return False, "no LLM provider reachable"