import asyncio

from sqlalchemy import select

from app.core.events import Event
from app.core.models import EventRecord


async def test_event_bus_dispatches_to_subscribers(core):
    received = []
    core.events.subscribe("test.thing", lambda event: received.append(event.type))

    event = Event(type="test.thing", aggregate_type="note", aggregate_id="abc", payload={"x": 1})
    await core.events.publish(event)

    assert received == ["test.thing"]


async def test_event_is_persisted(core):
    event = Event(type="notes.note_created", aggregate_type="note", aggregate_id="abc", payload={"note_id": "abc"})
    await core.events.publish(event)

    session = core.session_factory()
    row = session.execute(select(EventRecord)).scalar_one()
    assert row.event_type == "notes.note_created"
    assert row.aggregate_id == "abc"
    session.close()


async def test_command_bus(core):
    holder = {}

    def handler(command):
        holder["seen"] = command.payload

    core.command_bus.register("do.thing", handler)
    core.command_bus.dispatch(core.command("do.thing", {"ok": True}))
    assert holder["seen"] == {"ok": True}


async def test_module_registry_lifecycle(core):
    info = core.modules.info()
    names = {m["name"] for m in info}
    assert {"notes", "reminders", "notifications", "ai", "markdown"} <= names
    statuses = core.modules.statuses()
    assert statuses["notes"] == "running"
    assert statuses["reminders"] == "running"