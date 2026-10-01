import asyncio
from datetime import datetime, timezone, timedelta

from tests.conftest import build_core, make_settings


async def _wait_until(predicate, timeout=5.0, interval=0.05):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def test_scheduler_scan_fires_single_shot_reminder():
    core = await build_core(make_settings(), with_workers=True, provider=None)
    try:
        service = core.get_module("reminders").service
        reminder = service.create({"text": "Разбуди меня", "trigger_at": datetime.now(timezone.utc) - timedelta(seconds=10)})

        await core.workers_connector.scheduler._scan()

        runs = service.runs(str(reminder.id))
        assert len(runs) == 1

        processed = await _wait_until(lambda: service.runs(str(reminder.id))[0].status == "processed")
        assert processed, "worker should process the run"

        notifications = core.get_module("notifications").service.list()
        assert len(notifications) >= 1
        assert notifications[0].text == "Разбуди меня"
    finally:
        await core.workers_connector.stop()
        await core.shutdown()


async def test_scheduler_no_duplicate_runs_for_single_shot():
    core = await build_core(make_settings(), with_workers=True, provider=None)
    try:
        service = core.get_module("reminders").service
        reminder = service.create({"text": "Один раз", "trigger_at": datetime.now(timezone.utc) - timedelta(seconds=5)})

        await core.workers_connector.scheduler._scan()
        await _wait_until(lambda: bool(service.runs(str(reminder.id))), timeout=3.0)
        await core.workers_connector.scheduler._scan()
        await asyncio.sleep(0.5)

        assert len(service.runs(str(reminder.id))) == 1
        assert service.get(str(reminder.id)).status == "triggered"
    finally:
        await core.workers_connector.stop()
        await core.shutdown()


async def test_scheduler_repeating_reminder_advances():
    core = await build_core(make_settings(), with_workers=True, provider=None)
    try:
        service = core.get_module("reminders").service
        reminder = service.create({
            "text": "Каждый день",
            "trigger_at": datetime.now(timezone.utc) - timedelta(seconds=5),
            "repeat_rule": {"freq": "daily", "interval": 1},
        })
        first = reminder.trigger_at
        await core.workers_connector.scheduler._scan()

        refreshed = service.get(str(reminder.id))
        assert refreshed.trigger_at > first
        assert len(service.runs(str(reminder.id))) == 1
    finally:
        await core.workers_connector.stop()
        await core.shutdown()


async def test_scheduler_skips_cancelled_reminder():
    core = await build_core(make_settings(), with_workers=True, provider=None)
    try:
        service = core.get_module("reminders").service
        reminder = service.create({"text": "Отменён", "trigger_at": datetime.now(timezone.utc) - timedelta(seconds=5)})
        service.cancel(str(reminder.id))

        await core.workers_connector.scheduler._scan()
        await asyncio.sleep(0.3)

        assert service.runs(str(reminder.id)) == []
        assert service.get(str(reminder.id)).status == "cancelled"
    finally:
        await core.workers_connector.stop()
        await core.shutdown()