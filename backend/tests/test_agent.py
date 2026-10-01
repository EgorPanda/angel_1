import json

import pytest_asyncio

from tests.conftest import build_core, FakeProvider, make_settings


async def test_agent_single_tool_call():
    provider = FakeProvider([
        '{"tool":"create_note","arguments":{"title":"Агент-заметка","tags":["ai"]}}',
        {"text": "Готово: заметка создана"},
    ])
    core = await build_core(make_settings(), with_workers=False, provider=provider)
    try:
        outcome = await core.ai_runtime.chat("Создай заметку о запуске", user_id=core.user_id())
        assert outcome.status == "completed"
        assert outcome.text == "Готово: заметка создана"
        service = core.get_module("notes").service
        found = service.search(query="Агент-заметка")
        assert len(found) == 1
        assert "ai" in found[0]["tags"]
    finally:
        await core.shutdown()


async def test_agent_multistep():
    provider = FakeProvider([
        '{"tool":"create_note","arguments":{"title":"Поездка"}}',
        '{"tool":"create_reminder","arguments":{"text":"Купить билеты","trigger_at":"2026-10-01T08:00:00+00:00"}}',
        {"text": "Заметка и напоминание созданы"},
    ])
    core = await build_core(make_settings(), with_workers=False, provider=provider)
    try:
        outcome = await core.ai_runtime.chat("Создай проект поездки", user_id=core.user_id())
        assert outcome.status == "completed"
        assert outcome.tool_calls == []
        notes = core.get_module("notes").service.search(query="Поездка")
        reminders = core.get_module("reminders").service.list()
        assert len(notes) == 1
        assert len(reminders) == 1
        assert reminders[0].text == "Купить билеты"
    finally:
        await core.shutdown()


async def test_agent_unknown_tool_is_safe():
    provider = FakeProvider([
        '{"tool":"drop_all_notes","arguments":{}}',
        {"text": "Я не нашёл такой инструмент."},
    ])
    core = await build_core(make_settings(), with_workers=False, provider=provider)
    try:
        outcome = await core.ai_runtime.chat("Сделай что-нибудь опасное", user_id=core.user_id())
        assert outcome.status == "completed"
        assert core.get_module("notes").service.list() == []
    finally:
        await core.shutdown()


async def test_agent_confirmation_flow():
    core = await build_core(make_settings(), with_workers=False, provider=None)
    provider = FakeProvider([
        '{"tool":"delete_note","arguments":{"note_id":"11111111-1111-1111-1111-111111111111"}}',
    ])
    core.llm = provider
    core.ai_runtime.agent = None
    try:
        service = core.get_module("notes").service
        note = service.create({"title": "Будет удалена"})
        real_id = str(note["id"])

        provider.script[:] = [json.dumps({"tool": "delete_note", "arguments": {"note_id": real_id}})]
        outcome = await core.ai_runtime.chat(f"удали заметку {real_id}", user_id=core.user_id())
        assert outcome.status == "awaiting_confirmation"
        assert outcome.confirmation_id is not None
        assert service.get(real_id) is not None

        record = core.permissions.resolve(outcome.confirmation_id, approve=True)
        assert record.status == "approved"

        provider.script[:] = [
            json.dumps({"tool": "delete_note", "arguments": {"note_id": real_id}}),
            {"text": "Заметка удалена"},
        ]
        outcome2 = await core.ai_runtime.chat(f"удали заметку {real_id}", user_id=core.user_id())
        assert outcome2.status == "completed"
        from app.core.errors import NotFound

        try:
            service.get(real_id)
            assert False, "note should be deleted"
        except NotFound:
            pass
    finally:
        await core.shutdown()


async def test_agent_respects_forbidden_permission():
    core = await build_core(make_settings(), with_workers=False, provider=None)
    provider = FakeProvider([
        '{"tool":"delete_note","arguments":{"note_id":"11111111-1111-1111-1111-111111111111"}}',
        {"text": "Удаление запрещено правилами."},
    ])
    core.llm = provider
    core.ai_runtime.agent = None
    core.permissions.set_rule("notes.delete", "forbid", core.user_id())
    try:
        service = core.get_module("notes").service
        note = service.create({"title": "Неприкосновенная"})
        provider.script[:] = [json.dumps({"tool": "delete_note", "arguments": {"note_id": str(note["id"])}})]
        outcome = await core.ai_runtime.chat("удали заметку", user_id=core.user_id())
        assert outcome.status == "completed"
        assert service.get(str(note["id"])) is not None
    finally:
        await core.shutdown()