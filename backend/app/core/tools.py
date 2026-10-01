from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from pydantic import BaseModel, ValidationError

from app.core.errors import PermissionDenied, ToolExecutionError, ValidationError as AngelValidationError
from app.core.permissions import PermissionMode


@dataclass
class ToolContext:
    user_id: str | None = None
    correlation_id: str | None = None
    task_id: str | None = None
    core: Any = None
    extra: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = ""
    needs_confirmation: bool = False
    confirmation_id: str | None = None


class Tool:
    name: str = ""
    description: str = ""
    permission: str = ""
    default_mode: PermissionMode = PermissionMode.ALLOW
    input_schema: type[BaseModel] | None = None
    internal: bool = False

    def validate(self, params: dict) -> dict:
        if self.input_schema is None:
            if not isinstance(params, dict):
                raise AngelValidationError("tool arguments must be an object")
            return params
        try:
            model = self.input_schema.model_validate(params)
            return model.model_dump(exclude_none=True)
        except ValidationError as exc:
            raise AngelValidationError(f"invalid arguments for {self.name}", {"errors": exc.errors()})

    async def execute(self, params: dict, ctx: ToolContext) -> ToolResult:
        started = time.monotonic()
        try:
            validated = self.validate(params)
        except AngelValidationError:
            raise
        decision = ctx.core.permissions.request(
            permission=self.permission,
            tool_name=self.name,
            params=validated,
            default=self.default_mode,
            user_id=ctx.user_id,
            message=self.description,
            correlation_id=ctx.correlation_id,
        )
        if decision.needs_confirmation:
            return ToolResult(
                success=True,
                data=None,
                needs_confirmation=True,
                confirmation_id=decision.confirmation_id,
            )
        if not decision.allowed:
            raise PermissionDenied(f"action {self.permission} is forbidden")
        try:
            result = await self.run(validated, ctx)
            ctx.core.activity.log(
                user_id=ctx.user_id, actor="ai", action=f"tool:{self.name}",
                module=self.module, tool=self.name, status="ok", task_id=ctx.task_id,
                correlation_id=ctx.correlation_id,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return ToolResult(success=True, data=result)
        except PermissionDenied:
            raise
        except AngelValidationError:
            raise
        except Exception as exc:  # noqa: BLE001
            ctx.core.activity.log(
                user_id=ctx.user_id, actor="ai", action=f"tool:{self.name}",
                module=self.module, tool=self.name, status="error", task_id=ctx.task_id,
                correlation_id=ctx.correlation_id,
                duration_ms=int((time.monotonic() - started) * 1000),
                metadata={"error": str(exc)},
            )
            raise ToolExecutionError(f"tool {self.name} failed: {exc}") from exc

    module: str = "core"

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        raise NotImplementedError

    def schema_json(self) -> dict:
        if self.input_schema is None:
            return {"type": "object", "properties": {}, "additionalProperties": True}
        return self.input_schema.model_json_schema()


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def require(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"tool {name} not found")
        return tool

    def list(self) -> list[Tool]:
        return list(self._tools.values())