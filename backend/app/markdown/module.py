from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.core.module import Module
from app.core.module_config import ConfigField
from app.markdown.sync import MarkdownSyncService
from app.modules.notes import events as note_events

logger = get_logger("markdown.module")


class MarkdownModule(Module):
    name = "markdown"
    version = "0.2.0"
    description = "Projects PostgreSQL notes into an Obsidian-compatible Markdown vault."
    description_ru = "Проекция заметок в Markdown-хранилище (Obsidian-совместимое)."
    capabilities = ["markdown.sync", "markdown.vault"]
    dependencies = ["notes"]

    config_fields = [
        ConfigField("vault_path", "Путь к хранилищу", default="",
                    hint="Абсолютный или относительный путь к папке vault; пусто — из настроек программы"),
        ConfigField("enabled", "Включено", field_type="bool", default=True, value_type="bool"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.sync: MarkdownSyncService | None = None

    def effective_vault_path(self) -> str:
        cfg = self.config_values()
        return str(cfg.get("vault_path") or self.core.settings.vault_path)

    def _build_sync(self) -> None:
        self.sync = MarkdownSyncService(self.core.session_factory, self.effective_vault_path())

    def on_register(self, core) -> None:
        self.core = core
        self._build_sync()
        if self.sync.enabled():
            self.event_subscriptions = {
                note_events.NOTE_CREATED: self._on_note_changed,
                note_events.NOTE_UPDATED: self._on_note_changed,
                note_events.NOTE_DELETED: self._on_note_deleted,
                note_events.FOLDER_CREATED: self._on_folder_changed,
                note_events.FOLDER_UPDATED: self._on_folder_changed,
                note_events.FOLDER_DELETED: self._on_folder_changed,
            }
        super().on_register(core)

    async def reconfigure(self) -> None:
        self._build_sync()

    async def start(self) -> None:
        await super().start()
        if self.sync is not None and self.sync.enabled():
            try:
                await self._run_full_sync()
            except Exception:  # noqa: BLE001
                logger.error("initial markdown sync failed", exc_info=True)

    async def _run_full_sync(self) -> None:
        import asyncio

        await asyncio.to_thread(self.sync.full_sync)

    def health_check(self) -> tuple[bool, str]:
        if self.sync is None:
            return False, "sync service not initialized"
        if not self.sync.enabled():
            return True, "vault sync disabled"
        root = Path(self.sync.vault_path)
        ok = root.exists()
        return ok, "ok" if ok else "vault path does not exist"

    def info(self) -> dict:
        data = super().info()
        data["vault_path"] = self.effective_vault_path() if self.sync else None
        return data

    async def _on_note_changed(self, event) -> None:
        note_id = event.payload.get("note_id")
        if not note_id:
            return
        core = self.core
        try:
            core.worker_pool.enqueue("sync_markdown", {"action": "note", "note_id": note_id})
        except KeyError:
            pass

    async def _on_note_deleted(self, event) -> None:
        await self._enqueue({"action": "delete", "note_id": event.payload.get("note_id")})

    async def _on_folder_changed(self, event) -> None:
        folder_id = event.payload.get("folder_id") or event.aggregate_id
        if not folder_id:
            return
        await self._enqueue({"action": "folder", "folder_id": folder_id})

    async def _enqueue(self, payload: dict) -> None:
        core = self.core
        try:
            core.worker_pool.enqueue("sync_markdown", payload)
        except KeyError:
            pass