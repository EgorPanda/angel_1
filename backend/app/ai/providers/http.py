from __future__ import annotations

from typing import Any

import httpx

from app.ai.providers.base import Completion, LLMProvider, Message, ToolCall
from app.core.errors import LLMError
from app.core.logging import get_logger

logger = get_logger("llm.http")


class HttpProvider(LLMProvider):
    name = "http"

    def __init__(self, api_url: str, api_key: str = "", model: str = "default",
                 supports_tool_calling: bool = True, timeout: float = 60.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.supports_tool_calling = supports_tool_calling
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _endpoint(self) -> str:
        if self.api_url.endswith("/v1"):
            return f"{self.api_url}/chat/completions"
        if "/chat/completions" not in self.api_url:
            return f"{self.api_url}/v1/chat/completions"
        return self.api_url

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        timeout: float = 60.0,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools and self.supports_tool_calling:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self._endpoint(), json=payload, headers=self._headers())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM HTTP request failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"LLM request failed: {exc}") from exc
        try:
            choice = data["choices"][0]
            message = choice.get("message", {})
            text = message.get("content") or ""
            tool_calls: list[ToolCall] = []
            for raw in message.get("tool_calls", []) or []:
                fn = raw.get("function", {})
                arguments = fn.get("arguments", "{}")
                try:
                    args = json_loads(arguments)
                except Exception:  # noqa: BLE001
                    args = {}
                tool_calls.append(ToolCall(name=fn.get("name", ""), arguments=args, call_id=raw.get("id", "")))
            usage = data.get("usage", {})
            return Completion(text=text, tool_calls=tool_calls, raw=data, usage=usage)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected LLM response shape: {exc}") from exc

    def available(self) -> bool:
        import httpx

        try:
            response = httpx.get(self._endpoint(), timeout=3.0, headers=self._headers())
            return response.status_code < 500
        except Exception:  # noqa: BLE001
            return False


def json_loads(text: str) -> Any:
    import json

    return json.loads(text)