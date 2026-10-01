from __future__ import annotations

from app.core.module import Module
from app.modules.notes.api import build_router
from app.modules.notes.service import NotesService


class NotesModule(Module):
    name = "notes"
    version = "0.1.0"
    description = "Notes, folders, categories, tags, hierarchy, relationships and search."
    description_ru = "Заметки, папки, категории, теги, иерархия, связи и поиск."
    capabilities = ["notes.crud", "notes.hierarchy", "notes.folders", "notes.categories", "notes.tags", "notes.relations", "notes.search"]

    def __init__(self) -> None:
        super().__init__()
        self.service: NotesService | None = None

    def on_register(self, core) -> None:
        self.service = NotesService(core.session_factory, core.publish, vault_path=core.settings.vault_path)
        from app.modules.notes import tools as notes_tools

        self.tools = notes_tools.build_tools(self.service)
        self.routers = [build_router(self.service)]
        super().on_register(core)

    async def start(self) -> None:
        await super().start()

    def health_check(self) -> tuple[bool, str]:
        if self.service is None:
            return False, "service not initialized"
        return True, "ok"

    def info(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
        }