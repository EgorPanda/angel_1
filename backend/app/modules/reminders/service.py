from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.errors import Conflict, NotFound
from app.modules.reminders import events as rem_events
from app.modules.reminders.models import Reminder, ReminderRun


def to_utc(dt: datetime, tz_name: str = "UTC") -> datetime:
    if dt.tzinfo is None:
        try:
            tz = ZoneInfo(tz_name or "UTC")
        except Exception:  # noqa: BLE001
            tz = timezone.utc
        return dt.replace(tzinfo=tz).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def next_occurrence(trigger_at: datetime, repeat_rule: dict) -> datetime | None:
    freq = (repeat_rule or {}).get("freq", "once")
    interval = int((repeat_rule or {}).get("interval", 1) or 1)
    until = repeat_rule.get("until")
    tz = trigger_at.tzinfo or timezone.utc
    if freq == "once":
        return None
    if freq == "daily":
        nxt = trigger_at + timedelta(days=interval)
    elif freq == "weekly":
        nxt = trigger_at + timedelta(weeks=interval)
    elif freq == "monthly":
        year = trigger_at.year + (trigger_at.month + interval - 1) // 12
        month = (trigger_at.month + interval - 1) % 12 + 1
        day = min(trigger_at.day, 28)
        nxt = trigger_at.replace(year=year, month=month, day=day)
    else:
        return None
    if until is not None:
        until_dt = to_utc(until).astimezone(tz)
        if nxt > until_dt:
            return None
    return nxt.astimezone(timezone.utc)


def occurrence_key(scheduled_at: datetime) -> str:
    return scheduled_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")


class RemindersService:
    def __init__(self, session_factory, event_publish) -> None:
        self._sf = session_factory
        self._publish = event_publish

    def create(self, data: dict, user_id: str | None = None) -> Reminder:
        session = self._sf()
        try:
            reminder = Reminder(
                user_id=_u(user_id),
                text=data["text"],
                trigger_at=to_utc(data["trigger_at"], data.get("timezone", "UTC")),
                timezone=data.get("timezone", "UTC"),
                repeat_rule=data.get("repeat_rule") or {},
                note_id=_u(data.get("note_id")),
            )
            session.add(reminder)
            session.commit()
            session.refresh(reminder)
            self._emit(rem_events.REMINDER_CREATED, reminder, user_id)
            return reminder
        finally:
            session.close()

    def get(self, reminder_id: str) -> Reminder:
        session = self._sf()
        try:
            reminder = session.get(Reminder, uuid.UUID(reminder_id))
            if reminder is None:
                raise NotFound(f"reminder {reminder_id} not found")
            return reminder
        finally:
            session.close()

    def list(self, status: str | None = None) -> list[Reminder]:
        session = self._sf()
        try:
            stmt = select(Reminder).order_by(Reminder.trigger_at)
            if status:
                stmt = stmt.where(Reminder.status == status)
            return list(session.execute(stmt).scalars().all())
        finally:
            session.close()

    def update(self, reminder_id: str, data: dict) -> Reminder:
        session = self._sf()
        try:
            reminder = session.get(Reminder, uuid.UUID(reminder_id))
            if reminder is None:
                raise NotFound(f"reminder {reminder_id} not found")
            if reminder.status not in ("scheduled",):
                raise Conflict("only scheduled reminders can be updated")
            if data.get("text"):
                reminder.text = data["text"]
            if data.get("trigger_at") is not None:
                reminder.trigger_at = to_utc(data["trigger_at"], data.get("timezone", reminder.timezone))
            if data.get("timezone"):
                reminder.timezone = data["timezone"]
            if data.get("repeat_rule") is not None:
                reminder.repeat_rule = data["repeat_rule"]
            if "note_id" in data:
                reminder.note_id = _u(data["note_id"])
            session.commit()
            session.refresh(reminder)
            self._emit(rem_events.REMINDER_UPDATED, reminder, reminder.user_id)
            return reminder
        finally:
            session.close()

    def delete(self, reminder_id: str) -> None:
        session = self._sf()
        try:
            reminder = session.get(Reminder, uuid.UUID(reminder_id))
            if reminder is None:
                raise NotFound(f"reminder {reminder_id} not found")
            reminder_id_str = str(reminder.id)
            session.delete(reminder)
            session.commit()
            self._emit(rem_events.REMINDER_DELETED, reminder_id_str, reminder.user_id)
        finally:
            session.close()

    def cancel(self, reminder_id: str) -> Reminder:
        session = self._sf()
        try:
            reminder = session.get(Reminder, uuid.UUID(reminder_id))
            if reminder is None:
                raise NotFound(f"reminder {reminder_id} not found")
            reminder.status = "cancelled"
            session.commit()
            session.refresh(reminder)
            self._emit(rem_events.REMINDER_CANCELLED, reminder, reminder.user_id)
            return reminder
        finally:
            session.close()

    def due(self, now: datetime) -> list[Reminder]:
        session = self._sf()
        try:
            stmt = select(Reminder).where(
                Reminder.status == "scheduled", Reminder.trigger_at <= now.astimezone(timezone.utc)
            ).order_by(Reminder.trigger_at)
            return list(session.execute(stmt).scalars().all())
        finally:
            session.close()

    def create_run(self, reminder: Reminder, scheduled_at: datetime | None = None) -> ReminderRun:
        session = self._sf()
        try:
            attached = session.get(Reminder, reminder.id)
            if attached is None:
                raise NotFound("reminder not found")
            scheduled = scheduled_at or attached.trigger_at
            key = occurrence_key(scheduled)
            existing = self._find_run(session, attached.id, key)
            if existing is not None:
                return existing
            run = ReminderRun(reminder_id=attached.id, occurrence_key=key, scheduled_at=scheduled)
            session.add(run)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                existing = self._find_run(session, attached.id, key)
                if existing is not None:
                    return existing
                raise
            freq = (attached.repeat_rule or {}).get("freq", "once")
            if freq != "once":
                nxt = next_occurrence(scheduled, attached.repeat_rule)
                if nxt is None:
                    attached.status = "completed"
                else:
                    attached.trigger_at = nxt
            else:
                attached.status = "triggered"
            session.commit()
            session.refresh(run)
            self._emit(rem_events.REMINDER_RUN_CREATED, str(run.reminder_id),
                       payload={**_run_payload(run), "text": attached.text})
            return run
        finally:
            session.close()

    @staticmethod
    def _find_run(session, reminder_id, key: str) -> ReminderRun | None:
        return session.execute(
            select(ReminderRun).where(ReminderRun.reminder_id == reminder_id, ReminderRun.occurrence_key == key)
        ).scalar_one_or_none()

    def runs(self, reminder_id: str) -> list[ReminderRun]:
        session = self._sf()
        try:
            stmt = select(ReminderRun).where(ReminderRun.reminder_id == uuid.UUID(reminder_id)).order_by(ReminderRun.scheduled_at.desc())
            return list(session.execute(stmt).scalars().all())
        finally:
            session.close()

    def get_run(self, run_id: str) -> ReminderRun:
        session = self._sf()
        try:
            run = session.get(ReminderRun, uuid.UUID(run_id))
            if run is None:
                raise NotFound(f"reminder run {run_id} not found")
            return run
        finally:
            session.close()

    def run_for_occurrence(self, reminder_id: str, key: str) -> ReminderRun | None:
        session = self._sf()
        try:
            return session.execute(
                select(ReminderRun).where(
                    ReminderRun.reminder_id == uuid.UUID(reminder_id), ReminderRun.occurrence_key == key
                )
            ).scalar_one_or_none()
        finally:
            session.close()

    def update_run(self, run_id: str, status: str, result: dict | None = None,
                   error: str | None = None, attempts: int | None = None, task_id: str | None = None) -> ReminderRun:
        session = self._sf()
        try:
            run = session.get(ReminderRun, uuid.UUID(run_id))
            if run is None:
                raise NotFound(f"reminder run {run_id} not found")
            if status is not None:
                run.status = status
            if result is not None:
                run.result = result
            if error is not None:
                run.error = error
            if attempts is not None:
                run.attempts = attempts
            if task_id is not None:
                run.task_id = task_id
            if status in ("processed", "failed"):
                run.completed_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(run)
            return run
        finally:
            session.close()

    def _emit(self, event_type: str, subject, user_id: str | None = None, payload: dict | None = None) -> None:
        subject_id = subject if isinstance(subject, str) else str(subject.id)
        if payload is None:
            payload = {"text": subject.text} if hasattr(subject, "text") else {}
        try:
            self._publish(event_type=event_type, aggregate_type="reminder",
                          aggregate_id=subject_id, payload=payload, user_id=user_id)
        except Exception:  # noqa: BLE001
            pass


def _u(value):
    if value in (None, ""):
        return None
    return uuid.UUID(str(value))


def _run_payload(run: ReminderRun) -> dict:
    return {
        "run_id": str(run.id),
        "reminder_id": str(run.reminder_id),
        "occurrence_key": run.occurrence_key,
        "scheduled_at": run.scheduled_at.isoformat(),
    }