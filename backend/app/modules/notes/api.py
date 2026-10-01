from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.errors import AngelError, NotFound
from app.modules.notes.schemas import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    FolderCreate,
    FolderOut,
    FolderUpdate,
    NoteCreate,
    NoteDetail,
    NoteOut,
    NoteSearchResult,
    NoteUpdate,
    RelationshipCreate,
    RelationshipOut,
    TagOut,
    NoteTreeItem,
)
from app.modules.notes.serializer import (
    serialize_category,
    serialize_folder,
    serialize_note,
    serialize_relationship,
    serialize_tag,
)


def build_router(service: Any) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["notes"])

    def _err(exc: AngelError) -> HTTPException:
        return HTTPException(status_code=exc.http_status, detail=exc.message)

    @router.get("/notes", response_model=list[NoteOut])
    def list_notes(folder_id: str | None = None, parent_id: str | None = None):
        try:
            return [serialize_note(n) for n in service.list(folder_id=folder_id, parent_id=parent_id)]
        except AngelError as exc:
            raise _err(exc)

    @router.post("/notes", response_model=NoteOut, status_code=201)
    def create_note(payload: NoteCreate):
        try:
            return serialize_note(service.create(payload.model_dump()))
        except AngelError as exc:
            raise _err(exc)

    @router.get("/notes/search", response_model=list[NoteSearchResult])
    def search_notes(
        q: str = "",
        category_id: str | None = None,
        tag: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
    ):
        try:
            notes = service.search(q, category_id=category_id, tag=tag, limit=limit)
            results = []
            for note in notes:
                text = note.get("content") or ""
                idx = text.lower().find(q.lower()) if q else -1
                snippet = text[max(0, idx - 120): idx + len(q) + 120] if idx >= 0 else text[:240]
                results.append({
                    "id": note["id"],
                    "title": note["title"],
                    "folder_id": note.get("folder_id"),
                    "category_id": note.get("category_id"),
                    "importance": note.get("importance", "medium"),
                    "updated_at": note["updated_at"],
                    "snippet": snippet,
                })
            return results
        except AngelError as exc:
            raise _err(exc)

    @router.get("/notes/tree", response_model=list[NoteTreeItem])
    def note_tree():
        return service.tree()

    @router.get("/notes/{note_id}", response_model=NoteDetail)
    def get_note(note_id: str):
        try:
            note = service.get(note_id)
            data = serialize_note(note)
            data["children_ids"] = [c.get("id") for c in service.list(parent_id=note_id)]
            rels = service.relationships(note_id)
            data["relationships"] = [
                {
                    "id": r.get("id"),
                    "source_id": r.get("source_id"),
                    "target_id": r.get("target_id"),
                    "relation_type": r.get("relation_type", "link"),
                }
                for r in rels
            ]
            return data
        except AngelError as exc:
            raise _err(exc)

    @router.patch("/notes/{note_id}", response_model=NoteOut)
    def update_note(note_id: str, payload: NoteUpdate):
        try:
            return serialize_note(service.update(note_id, payload.model_dump(exclude_unset=True)))
        except AngelError as exc:
            raise _err(exc)

    @router.delete("/notes/{note_id}", status_code=204)
    def delete_note(note_id: str):
        try:
            service.delete(note_id)
        except AngelError as exc:
            raise _err(exc)

    @router.post("/notes/{note_id}/relations", response_model=RelationshipOut, status_code=201)
    def add_relation(note_id: str, payload: RelationshipCreate):
        try:
            rel = service.add_relation(note_id, payload.target_id, payload.relation_type)
            return serialize_relationship(rel)
        except AngelError as exc:
            raise _err(exc)

    @router.get("/notes/{note_id}/relations", response_model=list[RelationshipOut])
    def note_relations(note_id: str):
        try:
            return [serialize_relationship(r) for r in service.relationships(note_id)]
        except AngelError as exc:
            raise _err(exc)

    @router.delete("/notes/relations/{relation_id}", status_code=204)
    def remove_relation(relation_id: str):
        try:
            service.remove_relation(relation_id)
        except AngelError as exc:
            raise _err(exc)

    @router.get("/folders", response_model=list[FolderOut])
    def folders():
        return [serialize_folder(f) for f in service.folders()]

    @router.post("/folders", response_model=FolderOut, status_code=201)
    def create_folder(payload: FolderCreate):
        try:
            return serialize_folder(service.create_folder(payload.model_dump()))
        except AngelError as exc:
            raise _err(exc)

    @router.patch("/folders/{folder_id}", response_model=FolderOut)
    def update_folder(folder_id: str, payload: FolderUpdate):
        try:
            return serialize_folder(service.update_folder(folder_id, payload.model_dump(exclude_unset=True)))
        except AngelError as exc:
            raise _err(exc)

    @router.delete("/folders/{folder_id}", status_code=204)
    def delete_folder(folder_id: str):
        try:
            service.delete_folder(folder_id)
        except AngelError as exc:
            raise _err(exc)

    @router.get("/categories", response_model=list[CategoryOut])
    def categories():
        return [serialize_category(c) for c in service.categories()]

    @router.post("/categories", response_model=CategoryOut, status_code=201)
    def create_category(payload: CategoryCreate):
        try:
            return serialize_category(service.create_category(payload.name, payload.color))
        except AngelError as exc:
            raise _err(exc)

    @router.patch("/categories/{category_id}", response_model=CategoryOut)
    def rename_category(category_id: str, payload: CategoryUpdate):
        try:
            return serialize_category(service.rename_category(category_id, payload.name, payload.color))
        except AngelError as exc:
            raise _err(exc)

    @router.delete("/categories/{category_id}", status_code=204)
    def delete_category(category_id: str):
        try:
            service.delete_category(category_id)
        except AngelError as exc:
            raise _err(exc)

    @router.get("/tags", response_model=list[TagOut])
    def tags():
        try:
            return [serialize_tag(t) for t in service.tags()]
        except AngelError as exc:
            raise _err(exc)

    return router