import uuid

import pytest

from app.core.errors import NotFound, ValidationError
from app.modules.notes import events as note_events


async def _notes_service(core):
    return core.get_module("notes").service


async def test_create_note_with_tags(core):
    service = await _notes_service(core)
    note = service.create({"title": "Архитектура Angel AI", "content": "Текст заметки", "tags": ["angel-ai", "backend"]})
    assert note["title"] == "Архитектура Angel AI"
    assert sorted(note["tags"]) == ["angel-ai", "backend"]
    assert note["path"].startswith("0_Входящие/")
    assert note["note_type"] == "inbox"


async def test_create_note_in_project_folder(core):
    service = await _notes_service(core)
    note = service.create({"title": "Проект", "folder_id": "1_МоиПроекты/ASB"})
    assert note["note_type"] == "project"
    assert note["path"].startswith("1_МоиПроекты/ASB/")


async def test_note_crud(core):
    service = await _notes_service(core)
    note = service.create({"title": "Test"})
    fetched = service.get(str(note["id"]))
    assert fetched["title"] == "Test"
    updated = service.update(str(note["id"]), {"content": "новый контент", "importance": "high"})
    assert updated["content"] == "новый контент"
    assert updated["importance"] == "high"
    assert "новый контент" in service.get(str(note["id"]))["content"]
    service.delete(str(note["id"]))
    with pytest.raises(NotFound):
        service.get(str(note["id"]))


async def test_update_moves_and_renames_file(core):
    service = await _notes_service(core)
    note = service.create({"title": "Старое имя", "folder_id": "0_Входящие"})
    updated = service.update(str(note["id"]), {"title": "Новое имя", "folder_id": "1_МоиПроекты/Вов боты"})
    assert updated["path"].startswith("1_МоиПроекты/Вов боты/")
    assert updated["title"] == "Новое имя"
    assert service.get(updated["path"])["title"] == "Новое имя"


async def test_delete_archives_to_archive_folder(core):
    service = await _notes_service(core)
    note = service.create({"title": "На удаление"})
    service.delete(str(note["id"]))
    assert service.list() == []
    with pytest.raises(NotFound):
        service.get(str(note["id"]))


async def test_tree_by_folders(core):
    service = await _notes_service(core)
    service.create({"title": "Заметка A"})
    service.create({"title": "Заметка Б"})
    service.create({"title": "Проект X", "folder_id": "1_МоиПроекты/ASB"})
    nodes = service.tree()
    ids = {n["id"] for n in nodes}
    assert any("0_Входящие" in n["folder_id"] for n in nodes)
    assert any("1_МоиПроекты/ASB" in n["folder_id"] for n in nodes)
    assert len(ids) == 3


async def test_folders(core):
    service = await _notes_service(core)
    folder = service.create_folder({"name": "Новая папка", "parent_id": "0_Входящие"})
    assert folder["id"] == "0_Входящие/Новая папка"
    folder_ids = [f["id"] for f in service.folders()]
    assert folder["id"] in folder_ids
    note = service.create({"title": "N", "folder_id": folder["id"]})
    assert note["folder_id"] == folder["id"]


async def test_folder_move(core):
    service = await _notes_service(core)
    folder = service.create_folder({"name": "Переезжаю", "parent_id": "0_Входящие"})
    moved = service.update_folder(folder["id"], {"name": "Переехал"})
    assert moved["id"] == "0_Входящие/Переехал"


async def test_categories(core):
    service = await _notes_service(core)
    cats = service.categories()
    all_types = {c["id"] for c in cats}
    assert {"project", "area", "resource", "daily", "template", "inbox", "note"} <= all_types


async def test_relations(core):
    service = await _notes_service(core)
    a = service.create({"title": "A"})
    b = service.create({"title": "B"})
    rel = service.add_relation(str(a["id"]), str(b["id"]), "depends_on")
    assert rel["relation_type"] == "depends_on"
    rels = service.relationships(str(b["id"]))
    assert any(r["relation_type"] == "depends_on" for r in rels)
    service.remove_relation(str(rel["id"]))
    assert service.relationships(str(b["id"])) == []
    with pytest.raises(ValidationError):
        service.add_relation(str(a["id"]), str(a["id"]), "related")


async def test_search(core):
    service = await _notes_service(core)
    service.create({"title": "Покупка подарка", "content": "нужны ножницы и бумага", "tags": ["shopping"]})
    service.create({"title": "Разное", "content": "ничего интересного"})
    results = service.search(query="ножницы")
    assert len(results) == 1
    results2 = service.search(query="подарка")
    assert len(results2) == 1
    by_tag = service.search(tag="shopping")
    assert len(by_tag) == 1


async def test_tags(core):
    service = await _notes_service(core)
    service.update(service.create({"title": "Потегованная"}).get("id"), {"tags": ["ai", "ботаника"]})
    names = {t["name"] for t in service.tags()}
    assert {"ai", "ботаника"} <= names


async def test_events_emitted_on_note_operations(core):
    service = await _notes_service(core)
    session = core.session_factory()
    try:
        note = service.create({"title": "E"})
        import asyncio

        await asyncio.sleep(0.1)
        from sqlalchemy import select

        from app.core.models import EventRecord

        rows = session.execute(select(EventRecord).where(EventRecord.event_type == note_events.NOTE_CREATED)).scalars().all()
        assert len(rows) == 1
        assert rows[0].aggregate_id == str(note["id"])
    finally:
        session.close()