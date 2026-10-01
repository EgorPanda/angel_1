from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.core.permissions import PermissionMode
from app.core.tools import Tool, ToolContext


class RepeatRuleInput(BaseModel):
    freq: str = "once"
    interval: int = 1
    until: str | None = None


class CreateReminderInput(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    trigger_at: datetime
    timezone: str = "UTC"
    repeat_rule: RepeatRuleInput | None = None
    note_id: str | None = None


class UpdateReminderInput(BaseModel):
    reminder_id: str
    text: str | None = None
    trigger_at: datetime | None = None
    timezone: str | None = None
    repeat_rule: RepeatRuleInput | None = None
    note_id: str | None = None


class DeleteReminderInput(BaseModel):
    reminder_id: str


class CancelReminderInput(BaseModel):
    reminder_id: str
    reason: str | None = None


class ListRemindersInput(BaseModel):
    status: str | None = None


def _serialize(reminder) -> dict:
    return {
        "id": str(reminder.id),
        "text": reminder.text,
        "note_id": str(reminder.note_id) if reminder.note_id else None,
        "trigger_at": reminder.trigger_at.isoformat(),
        "timezone": reminder.timezone,
        "repeat_rule": reminder.repeat_rule,
        "status": reminder.status,
        "created_at": reminder.created_at.isoformat() if reminder.created_at else None,
        "updated_at": reminder.updated_at.isoformat() if reminder.updated_at else None,
    }


class RemindersTool(Tool):
    module = "reminders"

    def __init__(self, service: Any) -> None:
        self.service = service

    async def call(self, method: str, *args, **kwargs):
        return await asyncio.to_thread(getattr(self.service, method), *args, **kwargs)


class CreateReminderTool(RemindersTool):
    name = "create_reminder"
    description = "Create a reminder that fires at a specific time (UTC ISO datetime), optionally repeating daily/weekly/monthly."
    permission = "reminders.create"
    input_schema = CreateReminderInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        rule = validated.get("repeat_rule")
        if rule:
            rule = {k: v for k, v in rule.items() if v is not None}
        data = {
            "text": validated["text"],
            "trigger_at": _ensure_aware(validated["trigger_at"]),
            "timezone": validated.get("timezone", "UTC"),
            "repeat_rule": rule or {},
            "note_id": validated.get("note_id"),
        }
        reminder = await self.call("create", data, ctx.user_id)
        return _serialize(reminder)


class UpdateReminderTool(RemindersTool):
    name = "update_reminder"
    description = "Update an existing scheduled reminder."
    permission = "reminders.update"
    input_schema = UpdateReminderInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        reminder_id = validated["reminder_id"]
        data: dict = {}
        for field in ("text", "timezone", "note_id"):
            if validated.get(field) is not None:
                data[field] = validated[field]
        if validated.get("trigger_at") is not None:
            data["trigger_at"] = _ensure_aware(validated["trigger_at"])
        if validated.get("repeat_rule"):
            rule = validated["repeat_rule"]
            data["repeat_rule"] = {k: v for k, v in rule.items() if v is not None}
        reminder = await self.call("update", reminder_id, data)
        return _serialize(reminder)


class DeleteReminderTool(RemindersTool):
    name = "delete_reminder"
    description = "Permanently delete a reminder. Requires confirmation."
    permission = "reminders.delete"
    default_mode = PermissionMode.CONFIRM
    input_schema = DeleteReminderInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        await self.call("delete", validated["reminder_id"])
        return {"deleted": True, "reminder_id": validated["reminder_id"]}


class CancelReminderTool(RemindersTool):
    name = "cancel_reminder"
    description = "Cancel a scheduled reminder without deleting its history."
    permission = "reminders.update"
    input_schema = CancelReminderInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        reminder = await self.call("cancel", validated["reminder_id"])
        return _serialize(reminder)


class ListRemindersTool(RemindersTool):
    name = "list_reminders"
    description = "List reminders, optionally filtered by status."
    permission = "reminders.read"
    input_schema = ListRemindersInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        reminders = await self.call("list", validated.get("status"))
        return [_serialize(r) for r in reminders]


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_tools(service) -> list[Tool]:
    return [
        CreateReminderTool(service),
        UpdateReminderTool(service),
        DeleteReminderTool(service),
        CancelReminderTool(service),
        ListRemindersTool(service),
    ]