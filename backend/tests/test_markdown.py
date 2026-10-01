import asyncio
import os

import yaml

from app.modules.notes.markdown_parser import parse_frontmatter
from tests.conftest import build_core, make_settings


def find_file_in_vault(vault_path: str, note_id: str) -> str | None:
    for root, _dirs, files in os.walk(vault_path):
        for name in files:
            if not name.endswith(".md"):
                continue
            full = os.path.join(root, name)
            if ".obsidian" in full or "Attachments" in full:
                continue
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    text = f.read(4000)
            except OSError:
                continue
            if f"id: {note_id}" in text:
                return os.path.relpath(full, vault_path).replace("\\", "/")
    return None


async def test_markdown_note_written_to_vault_with_frontmatter():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        notes = core.get_module("notes").service
        note = notes.create({"title": "Главная заметка", "content": "Проект Angel AI", "tags": ["ai"], "importance": "high"})

        rel = find_file_in_vault(settings.markdown_vault_path, str(note["id"]))
        assert rel is not None, "note should be written to vault"
        assert rel.startswith("0_Входящие/")

        full = os.path.join(settings.markdown_vault_path, rel)
        with open(full, encoding="utf-8") as f:
            text = f.read()
        data = parse_frontmatter(text)
        assert data["id"] == str(note["id"])
        assert data["title"] == "Главная заметка"
        assert "ai" in data["tags"]
        assert data["importance"] == "high"
        assert "Проект Angel AI" in text
    finally:
        await core.shutdown()


async def test_markdown_deleting_note_moves_to_archive():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        notes = core.get_module("notes").service
        note = notes.create({"title": "Временная"})
        rel = find_file_in_vault(settings.markdown_vault_path, str(note["id"]))
        assert rel is not None

        notes.delete(str(note["id"]))
        moved = find_file_in_vault(settings.markdown_vault_path, str(note["id"]))
        assert moved is not None, "deleted note should move to archive folder"
        assert moved.startswith("4_Архив/Архивированные/")
    finally:
        await core.shutdown()


async def test_markdown_full_sync_generates_moc():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        notes = core.get_module("notes").service
        note = notes.create({"title": "Синк МОК"})

        from app.markdown.sync import MarkdownSyncService

        await asyncio.to_thread(MarkdownSyncService(core.session_factory, settings.vault_path).full_sync)

        moc_path = os.path.join(settings.markdown_vault_path, "0_Входящие", "0_Входящие_MOC.md")
        assert os.path.exists(moc_path)
        with open(moc_path, encoding="utf-8") as f:
            assert "Синк МОК" in f.read()
    finally:
        await core.shutdown()


async def test_markdown_module_syncs_on_create():
    settings = make_settings()
    core = await build_core(settings, with_workers=True, provider=None)
    try:
        service = core.get_module("notes").service
        note = service.create({"title": "Событийная заметка"})
        ok = False
        for _ in range(100):
            if find_file_in_vault(settings.markdown_vault_path, str(note["id"])):
                ok = True
                break
            await asyncio.sleep(0.1)
        assert ok, "note should be written to vault"
        await core.workers_connector.stop()
    finally:
        await core.shutdown()