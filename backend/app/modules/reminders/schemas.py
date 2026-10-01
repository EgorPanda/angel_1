from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RepeatRule(BaseModel):
    freq: Literal["once", "daily", "weekly", "monthly"] = "once"
    interval: int = Field(default=1, ge=1)
    until: datetime | None = None


class ReminderBase(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    trigger_at: datetime
    timezone: str = "UTC"
    repeat_rule: RepeatRule = RepeatRule()
    note_id: str | None = None


class ReminderCreate(ReminderBase):
    pass


class ReminderUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    trigger_at: datetime | None = None
    timezone: str | None = None
    repeat_rule: RepeatRule | None = None
    note_id: str | None = None


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    note_id: str | None = None
    trigger_at: datetime
    timezone: str
    repeat_rule: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ReminderRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reminder_id: str
    occurrence_key: str
    scheduled_at: datetime
    status: str
    attempts: int
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ReminderRunDetail(ReminderRunOut):
    result: dict | None = None