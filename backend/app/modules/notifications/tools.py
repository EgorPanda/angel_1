from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from app.core.permissions import PermissionMode
from app.core.tools import Tool, ToolContext


class SendNotificationInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    title: str = ""
    channel: str = "web"


class SendReminderNotificationInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    title: str = "Напоминание"


class NotificationTool(Tool):
    module = "notifications"

    def __init__(self, service: Any) -> None:
        self.service = service

    async def call(self, text: str, channel: str, user_id: str | None, title: str):
        return await asyncio.to_thread(self.service.send, text, channel, user_id, title)


class SendNotificationTool(NotificationTool):
    name = "send_notification"
    description = "Send a notification to the user via a channel (telegram or web). Requires confirmation."
    permission = "notifications.send"
    default_mode = PermissionMode.CONFIRM
    input_schema = SendNotificationInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        notification = await self.call(
            validated["text"], validated.get("channel", "web"), ctx.user_id, validated.get("title", "")
        )
        return {"notification_id": str(notification.id), "channel": notification.channel, "status": notification.status}


class SendReminderNotificationTool(NotificationTool):
    name = "send_reminder_notification"
    description = "Send a reminder notification triggered by the scheduler. Internal tool."
    permission = "notifications.reminder"
    default_mode = PermissionMode.ALLOW
    internal = True
    input_schema = SendReminderNotificationInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        notification = await self.call(
            validated["text"], "telegram", ctx.user_id, validated.get("title", "Напоминание")
        )
        return {"notification_id": str(notification.id), "channel": notification.channel, "status": notification.status}


def build_tools(service) -> list[Tool]:
    return [
        SendNotificationTool(service),
        SendReminderNotificationTool(service),
    ]