from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.errors import AngelError
from app.modules.reminders.schemas import (
    ReminderCreate,
    ReminderOut,
    ReminderRunDetail,
    ReminderRunOut,
    ReminderUpdate,
)


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


def _serialize_run(run, with_result: bool = False) -> dict:
    data = {
        "id": str(run.id),
        "reminder_id": str(run.reminder_id),
        "occurrence_key": run.occurrence_key,
        "scheduled_at": run.scheduled_at.isoformat(),
        "status": run.status,
        "attempts": run.attempts,
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
    if with_result:
        data["result"] = run.result
    return data


def build_router(service) -> APIRouter:
    router = APIRouter(prefix="/api/v1/reminders", tags=["reminders"])

    def _err(exc: AngelError) -> HTTPException:
        return HTTPException(status_code=exc.http_status, detail=exc.message)

    @router.get("/{reminder_id}/runs", response_model=list[ReminderRunOut])
    def runs(reminder_id: str):
        try:
            return [_serialize_run(r) for r in service.runs(reminder_id)]
        except AngelError as exc:
            raise _err(exc)

    @router.get("/runs/{run_id}", response_model=ReminderRunDetail)
    def run_detail(run_id: str):
        try:
            return _serialize_run(service.get_run(run_id), with_result=True)
        except AngelError as exc:
            raise _err(exc)

    @router.get("", response_model=list[ReminderOut])
    def list_reminders(status: str | None = None):
        return [_serialize(r) for r in service.list(status)]

    @router.post("", response_model=ReminderOut, status_code=201)
    def create_reminder(payload: ReminderCreate):
        try:
            return _serialize(service.create(payload.model_dump()))
        except AngelError as exc:
            raise _err(exc)

    @router.get("/{reminder_id}", response_model=ReminderOut)
    def get_reminder(reminder_id: str):
        try:
            return _serialize(service.get(reminder_id))
        except AngelError as exc:
            raise _err(exc)

    @router.patch("/{reminder_id}", response_model=ReminderOut)
    def update_reminder(reminder_id: str, payload: ReminderUpdate):
        try:
            return _serialize(service.update(reminder_id, payload.model_dump(exclude_unset=True)))
        except AngelError as exc:
            raise _err(exc)

    @router.delete("/{reminder_id}", status_code=204)
    def delete_reminder(reminder_id: str):
        try:
            service.delete(reminder_id)
        except AngelError as exc:
            raise _err(exc)

    @router.post("/{reminder_id}/cancel", response_model=ReminderOut)
    def cancel_reminder(reminder_id: str):
        try:
            return _serialize(service.cancel(reminder_id))
        except AngelError as exc:
            raise _err(exc)

    return router