from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from app.core.permissions import PermissionMode
from app.core.tools import Tool, ToolContext


class CreateNoteInput(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    content: str = ""
    folder_id: str | None = None
    category_id: str | None = None
    parent_id: str | None = None
    importance: str = "medium"
    tags: list[str] = []


class GetNoteInput(BaseModel):
    note_id: str


class UpdateNoteInput(BaseModel):
    note_id: str
    title: str | None = None
    content: str | None = None
    folder_id: str | None = None
    category_id: str | None = None
    parent_id: str | None = None
    importance: str | None = None
    tags: list[str] | None = None


class DeleteNoteInput(BaseModel):
    note_id: str


class SearchNotesInput(BaseModel):
    query: str = ""
    category_id: str | None = None
    tag: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ListNotesInput(BaseModel):
    folder_id: str | None = None
    parent_id: str | None = None


class CreateFolderInput(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str = ""
    parent_id: str | None = None
    category_id: str | None = None


class UpdateFolderInput(BaseModel):
    folder_id: str
    name: str | None = None
    description: str | None = None
    parent_id: str | None = None
    category_id: str | None = None


class DeleteFolderInput(BaseModel):
    folder_id: str


class CreateCategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str = "#8b5cf6"


class RenameCategoryInput(BaseModel):
    category_id: str
    name: str = Field(min_length=1, max_length=128)
    color: str | None = None


class DeleteCategoryInput(BaseModel):
    category_id: str


def _to_dict(service_call):
    if hasattr(service_call, "id"):
        return _serialize(service_call)
    return [_serialize(item) for item in service_call]


def _serialize(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    data = {
        "id": str(obj.id),
        "created_at": obj.created_at.isoformat() if hasattr(obj, "created_at") and obj.created_at else None,
    }
    if hasattr(obj, "updated_at") and getattr(obj, "updated_at"):
        data["updated_at"] = obj.updated_at.isoformat()
    for attr in ("title", "content", "name", "description", "importance", "status", "color",
                 "folder_id", "category_id", "parent_id", "relation_type", "target_id"):
        if hasattr(obj, attr):
            value = getattr(obj, attr)
            data[attr] = str(value) if value is not None and not isinstance(value, (str, int, float, bool)) else value
    if hasattr(obj, "tags"):
        data["tags"] = [t.name for t in obj.tags]
    return data


class NotesTool(Tool):
    module = "notes"

    def __init__(self, service: Any) -> None:
        self.service = service

    async def call(self, method: str, *args, **kwargs):
        return await asyncio.to_thread(getattr(self.service, method), *args, **kwargs)


class CreateNoteTool(NotesTool):
    name = "create_note"
    description = "Create a new note with optional folder, category, parent note, importance and tags."
    permission = "notes.create"
    input_schema = CreateNoteInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        note = await self.call("create", validated, ctx.user_id)
        return _serialize(note)


class GetNoteTool(NotesTool):
    name = "get_note"
    description = "Get a single note and its content by id."
    permission = "notes.read"
    input_schema = GetNoteInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        note = await self.call("get", validated["note_id"])
        data = _serialize(note)
        children = await self.call("list", None, validated["note_id"])
        data["children"] = [_serialize(c).get("id") for c in children]
        return data


class UpdateNoteTool(NotesTool):
    name = "update_note"
    description = "Update an existing note (title, content, folder, category, parent, importance, tags)."
    permission = "notes.update"
    input_schema = UpdateNoteInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        note_id = validated.pop("note_id")
        note = await self.call("update", note_id, validated)
        return _serialize(note)


class DeleteNoteTool(NotesTool):
    name = "delete_note"
    description = "Permanently delete a note. Children are re-parented. Requires confirmation."
    permission = "notes.delete"
    default_mode = PermissionMode.CONFIRM
    input_schema = DeleteNoteInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        await self.call("delete", validated["note_id"], ctx.user_id)
        return {"deleted": True, "note_id": validated["note_id"]}


class SearchNotesTool(NotesTool):
    name = "search_notes"
    description = "Search notes by title, content, category or tag."
    permission = "notes.read"
    input_schema = SearchNotesInput

async def run(self, validated: dict, ctx: ToolContext) -> Any:
        query = validated.get("query", "")
        notes = await self.call("search", query, validated.get("category_id"), validated.get("tag"), validated.get("limit", 20))
        return [_serialize(n) | {"snippet": _snippet(n.get("content", ""), query)} for n in notes]


def _snippet(content: str, query: str, radius: int = 120) -> str:
    if not query or not content:
        return content[:200]
    idx = content.lower().find(query.lower())
    if idx < 0:
        return content[:200]
    start = max(0, idx - radius)
    end = min(len(content), idx + len(query) + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


class ListNotesTool(NotesTool):
    name = "list_notes"
    description = "List notes by folder or by parent note (hierarchy children)."
    permission = "notes.read"
    input_schema = ListNotesInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        notes = await self.call("list", validated.get("folder_id"), validated.get("parent_id"))
        return [_serialize(n) for n in notes]


class CreateFolderTool(NotesTool):
    name = "create_folder"
    description = "Create a folder (group of notes), optionally nested under another folder."
    permission = "notes.create"
    input_schema = CreateFolderInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        return _to_dict(await self.call("create_folder", validated))


class UpdateFolderTool(NotesTool):
    name = "update_folder"
    description = "Rename or move a folder."
    permission = "notes.update"
    input_schema = UpdateFolderInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        folder_id = validated.pop("folder_id")
        return _to_dict(await self.call("update_folder", folder_id, validated))


class DeleteFolderTool(NotesTool):
    name = "delete_folder"
    description = "Delete a folder. Notes move to the parent folder. Requires confirmation."
    permission = "notes.delete"
    default_mode = PermissionMode.CONFIRM
    input_schema = DeleteFolderInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        await self.call("delete_folder", validated["folder_id"])
        return {"deleted": True, "folder_id": validated["folder_id"]}


class CreateCategoryTool(NotesTool):
    name = "create_category"
    description = "Create a category (e.g. Personal, Business, Work, Friends, Finance)."
    permission = "notes.create"
    input_schema = CreateCategoryInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        return _to_dict(await self.call("create_category", validated["name"], validated.get("color", "#8b5cf6")))


class RenameCategoryTool(NotesTool):
    name = "rename_category"
    description = "Rename (or recolor) an existing category."
    permission = "notes.update"
    input_schema = RenameCategoryInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        return _to_dict(await self.call("rename_category", validated["category_id"], validated["name"], validated.get("color")))


class DeleteCategoryTool(NotesTool):
    name = "delete_category"
    description = "Delete a category. Notes are kept but lose the category. Requires confirmation."
    permission = "notes.delete"
    default_mode = PermissionMode.CONFIRM
    input_schema = DeleteCategoryInput

    async def run(self, validated: dict, ctx: ToolContext) -> Any:
        await self.call("delete_category", validated["category_id"])
        return {"deleted": True, "category_id": validated["category_id"]}


def build_tools(service) -> list[Tool]:
    return [
        CreateNoteTool(service),
        GetNoteTool(service),
        UpdateNoteTool(service),
        DeleteNoteTool(service),
        SearchNotesTool(service),
        ListNotesTool(service),
        CreateFolderTool(service),
        UpdateFolderTool(service),
        DeleteFolderTool(service),
        CreateCategoryTool(service),
        RenameCategoryTool(service),
        DeleteCategoryTool(service),
    ]
