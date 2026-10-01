from datetime import datetime, timezone, timedelta

import pytest

from app.modules.reminders.service import RemindersService, next_occurrence, to_utc, occurrence_key


def test_to_utc_naive_with_tz():
    dt = datetime(2026, 1, 1, 21, 0)
    result = to_utc(dt, "Europe/Moscow")
    assert result.utcoffset().total_seconds() == 0
    assert result.hour in (18, 19)


def test_next_occurrence_daily():
    base = to_utc(datetime(2026, 1, 1, 10, 0))
    nxt = next_occurrence(base, {"freq": "daily", "interval": 1})
    assert nxt - base == timedelta(days=1)


def test_next_occurrence_weekly():
    base = to_utc(datetime(2026, 1, 1, 9, 0))
    nxt = next_occurrence(base, {"freq": "weekly", "interval": 2})
    assert nxt - base == timedelta(weeks=2)


def test_next_occurrence_monthly_boundary():
    base = to_utc(datetime(2026, 1, 31, 12, 0))
    nxt = next_occurrence(base, {"freq": "monthly", "interval": 1})
    assert nxt.month == 2
    assert nxt.day == 28


def test_next_occurrence_once():
    base = to_utc(datetime(2026, 1, 1, 8, 0))
    assert next_occurrence(base, {}) is None


def test_occurrence_key_format():
    dt = to_utc(datetime(2026, 1, 5, 9, 30))
    assert occurrence_key(dt) == "20260105T093000"


async def test_reminder_crud_and_due(core):
    service: RemindersService = core.get_module("reminders").service
    reminder = service.create({"text": "Купить ножницы", "trigger_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
    due = service.due(datetime.now(timezone.utc))
    assert any(str(r.id) == str(reminder.id) for r in due)

    service.update(str(reminder.id), {"text": "Купить ножницы и бумагу"})
    assert service.get(str(reminder.id)).text == "Купить ножницы и бумагу"

    service.delete(str(reminder.id))
    with pytest.raises(Exception):
        service.get(str(reminder.id))


async def test_reminder_repeating_advances_trigger(core):
    service: RemindersService = core.get_module("reminders").service
    reminder = service.create({
        "text": "Зарядка",
        "trigger_at": datetime.now(timezone.utc) - timedelta(seconds=5),
        "repeat_rule": {"freq": "daily", "interval": 1},
    })
    initial = reminder.trigger_at
    run = service.create_run(reminder, scheduled_at=initial)
    assert run.status == "scheduled"
    again = service.create_run(reminder, scheduled_at=initial)
    assert str(again.id) == str(run.id)

    refreshed = service.get(str(reminder.id))
    assert refreshed.trigger_at > initial


async def test_reminder_single_shot_marked_triggered(core):
    service: RemindersService = core.get_module("reminders").service
    reminder = service.create({"text": "Разовое", "trigger_at": datetime.now(timezone.utc) - timedelta(seconds=5)})
    service.create_run(reminder)
    refreshed = service.get(str(reminder.id))
    assert refreshed.status == "triggered"


async def test_reminder_run_history(core):
    service: RemindersService = core.get_module("reminders").service
    reminder = service.create({
        "text": "Повторное",
        "trigger_at": datetime.now(timezone.utc) - timedelta(days=2),
        "repeat_rule": {"freq": "daily", "interval": 1},
    })
    initial = reminder.trigger_at
    service.create_run(reminder, scheduled_at=initial)
    service.create_run(service.get(str(reminder.id)), scheduled_at=initial + timedelta(days=1))
    runs = service.runs(str(reminder.id))
    assert len(runs) == 2
    assert runs[0].status == "scheduled"


async def test_reminder_cancel(core):
    service: RemindersService = core.get_module("reminders").service
    reminder = service.create({"text": "Отменить меня", "trigger_at": datetime.now(timezone.utc) + timedelta(days=1)})
    updated = service.cancel(str(reminder.id))
    assert updated.status == "cancelled"
    assert service.due(datetime.now(timezone.utc)) == []