from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select

from app.core.errors import Conflict, NotFound, ValidationError
from app.modules.notes import events as note_events
from app.modules.notes.index_models import IndexLink, IndexNote, IndexTag
from app.modules.notes.markdown_parser import _body, parse_frontmatter, render_frontmatter

NOTES_TYPES = ["project", "area", "resource", "plan", "daily", "template", "note", "inbox"]
CATEGORY_COLORS = {
    "project": "#8b5cf6",
    "area": "#22c55e",
    "resource": "#06b6d4",
    "plan": "#f59e0b",
    "daily": "#ec4899",
    "template": "#94a3b8",
    "note": "#64748b",
    "inbox": "#eab308",
}


ARCHIVE_DEST = "4_Архив/Архивированные"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _infer_type(folder: str, title: str) -> str:
    folder = (folder or "").lower()
    if folder.startswith("1_моипроекты") or folder.startswith("проект"):
        return "project"
    if folder.startswith("2_области"):
        return "area"
    if folder.startswith("3_ресурсы"):
        return "resource"
    if folder.startswith("5_шаблоны"):
        return "template"
    if folder.startswith("0_входящие") or folder == "":
        return "inbox"
    if "дневник" in folder or len(title) == 10 and title[2] == "-" and title[5] == "-":
        return "daily"
    if "план" in title.lower() or "план" in folder:
        return "plan"
    return "note"


class NotesService:
    def __init__(self, session_factory, event_publish, vault_path: str | None = None) -> None:
        self._sf = session_factory
        self._publish = event_publish
        self.vault_path = vault_path

    def _sync(self):
        from app.markdown.sync import MarkdownSyncService

        if getattr(self, "_sync_service", None) is None:
            if not self.vault_path:
                from app.config import get_settings

                self.vault_path = get_settings().vault_path
            self._sync_service = MarkdownSyncService(self._sf, self.vault_path)
        return self._sync_service

    # ----- resolution / hydration -----

    def _resolve_row(self, note_id: str) -> IndexNote:
        session = self._sf()
        try:
            row = None
            if isinstance(note_id, str) and note_id.endswith(".md"):
                row = session.execute(select(IndexNote).where(IndexNote.path == note_id)).scalars().first()
            if row is None:
                try:
                    row = session.execute(select(IndexNote).where(IndexNote.id == uuid.UUID(str(note_id)))).scalars().first()
                except (ValueError, TypeError):  # noqa: PERF203
                    row = None
            if row is None:
                raise NotFound(f"note {note_id} not found")
            return row
        finally:
            session.close()

    def _note_dict(self, row: IndexNote, content: str | None = None) -> dict:
        folder = Path(row.path).parent.as_posix()
        return {
            "id": str(row.id),
            "title": row.title,
            "content": content if content is not None else "",
            "folder_id": folder if folder and folder != "." else None,
            "path": row.path,
            "note_type": row.note_type,
            "category_id": row.note_type,
            "parent_id": None,
            "importance": row.importance,
            "status": row.status,
            "sort_order": 0,
            "user_id": str(row.user_id) if row.user_id else None,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "tags": [t.name for t in row.tags],
        }

    # ----- notes -----

    def create(self, data: dict, user_id: str | None = None) -> dict:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValidationError("title is required")
        folder = (data.get("folder_id") or "0_Входящие").strip("/")
        note_type = data.get("category_id") or _infer_type(folder, title)
        tags = [str(t).strip("#").strip() for t in (data.get("tags") or []) if str(t).strip()]
        content = str(data.get("content") or "").strip()
        now = _now().isoformat()
        note_id = str(uuid.uuid4())
        meta = {
            "id": note_id,
            "title": title,
            "type": note_type,
            "tags": tags,
            "importance": data.get("importance") or "medium",
            "created_at": now,
            "updated_at": now,
        }
        if data.get("status"):
            meta["status"] = str(data["status"])
        text = render_frontmatter(meta) + (content + "\n" if content else "")
        sync = self._sync()
        rel = sync.path_for_new_note(folder, title)
        sync.save_note({"path": rel, "text": text})
        sync.sync_note(rel)
        self._emit(note_events.NOTE_CREATED, note_id, {"note_id": rel, "path": rel, "title": title}, user_id)
        return {
            "id": note_id,
            "title": title,
            "content": content,
            "folder_id": folder if folder != "." else None,
            "path": rel,
            "note_type": note_type,
            "category_id": note_type,
            "parent_id": None,
            "importance": data.get("importance") or "medium",
            "status": data.get("status") or "active",
            "sort_order": 0,
            "user_id": user_id,
            "created_at": _now(),
            "updated_at": _now(),
            "tags": tags,
        }

    def get(self, note_id: str) -> dict:
        row = self._resolve_row(note_id)
        sync = self._sync()
        text = sync.read_note(row.path)
        return self._note_dict(row, content=_body(text))

    def list(self, folder_id: str | None = None, parent_id: str | None = None) -> list[dict]:
        if parent_id:
            return []
        session = self._sf()
        try:
            stmt = select(IndexNote)
            if folder_id and str(folder_id).strip("/"):
                prefix = str(folder_id).strip("/") + "/"
                stmt = stmt.where(or_(IndexNote.path.startswith(prefix), IndexNote.path == str(folder_id).strip("/")))
            stmt = stmt.order_by(IndexNote.updated_at.desc()).limit(1000)
            rows = session.execute(stmt).scalars().all()
            return [self._note_dict(r) for r in rows]
        finally:
            session.close()

    def search(self, query: str = "", category_id: str | None = None, tag: str | None = None, limit: int = 50) -> list[dict]:
        session = self._sf()
        try:
            stmt = select(IndexNote).where(IndexNote.status != "archived")
            if category_id:
                stmt = stmt.where(IndexNote.note_type == category_id)
            if tag:
                stmt = stmt.join(IndexTag, IndexTag.index_note_id == IndexNote.id).where(IndexTag.name == tag)
            if not query:
                stmt = stmt.order_by(IndexNote.updated_at.desc()).limit(max(limit, 50))
                rows = session.execute(stmt).scalars().all()
                return [self._note_dict(r) for r in rows]
            stmt = stmt.order_by(IndexNote.updated_at.desc()).limit(400)
            rows = session.execute(stmt).scalars().all()
        finally:
            session.close()
        q = query.lower()
        sync = self._sync()
        candidates: list[tuple[IndexNote, str, int]] = []
        for row in rows:
            content = sync.read_note(row.path)
            low = content.lower()
            score = 0
            if q in low:
                score = 2
            elif q in row.title.lower() or q in row.path.lower() or q in row.note_type.lower():
                score = 1
            if score:
                candidates.append((row, content, score))
        candidates.sort(key=lambda item: item[2], reverse=True)
        results = []
        for row, content, _score in candidates[:limit]:
            item = self._note_dict(row, content=content)
            item["score"] = _score
            results.append(item)
        return results

    def update(self, note_id: str, data: dict) -> dict:
        row = self._resolve_row(note_id)
        sync = self._sync()
        old_rel = row.path
        filepath = sync._abspath(old_rel)
        text = filepath.read_text(encoding="utf-8", errors="ignore") if filepath.exists() else ""
        fm = parse_frontmatter(text)
        body = _body(text)

        if data.get("status") == "archived":
            new_rel = sync.archive_note(old_rel)
            self._emit(note_events.NOTE_UPDATED, str(row.id), {"note_id": new_rel, "path": new_rel, "title": row.title}, data.get("_user_id"))
            return {
                "id": str(row.id),
                "title": row.title,
                "content": "",
                "folder_id": str(Path(new_rel).parent.as_posix()),
                "path": new_rel,
                "note_type": row.note_type,
                "category_id": row.note_type,
                "parent_id": None,
                "importance": row.importance,
                "status": "archived",
                "sort_order": 0,
                "user_id": str(row.user_id) if row.user_id else None,
                "created_at": row.created_at,
                "updated_at": _now(),
                "tags": [t.name for t in row.tags],
            }

        title = str(data.get("title") or fm.get("title") or row.title).strip()
        note_type = data.get("category_id") or fm.get("type") or row.note_type
        if data.get("tags") is not None:
            tags = [str(t).strip("#").strip() for t in data["tags"] if str(t).strip()]
        else:
            tags = [str(t) for t in (fm.get("tags") or [])]
        for key in ("business", "summary", "importance", "status"):
            if data.get(key) is not None and data.get(key) != "":
                fm[key] = data[key]
        fm.update(
            {
                "id": str(fm.get("id") or row.id),
                "title": title,
                "type": note_type,
                "tags": tags,
                "updated_at": _now().isoformat(),
            }
        )
        if data.get("content") is not None:
            body = str(data["content"]).strip()

        new_rel = old_rel
        if data.get("folder_id") is not None:
            folder = str(data["folder_id"]).strip("/")
            new_rel = sync.path_for_new_note(folder, title)
        elif title != row.title:
            folder = str(Path(old_rel).parent.as_posix())
            new_rel = sync.path_for_new_note(folder, title)

        text_out = render_frontmatter(fm) + (body + "\n" if body else "")
        sync.save_note({"path": new_rel, "text": text_out})
        if new_rel != old_rel:
            sync._abspath(old_rel).unlink(missing_ok=True)
            session = self._sf()
            try:
                session.execute(IndexNote.__table__.delete().where(IndexNote.path == old_rel))
                session.commit()
            finally:
                session.close()
        sync.sync_note(new_rel)
        self._emit(note_events.NOTE_UPDATED, str(uuid.uuid4()), {"note_id": new_rel, "path": new_rel, "title": title}, data.get("_user_id"))
        return self._hydrated(rel=new_rel)

    def delete(self, note_id: str, user_id: str | None = None) -> dict:
        sync = self._sync()
        rel = str(note_id).replace("\\", "/")
        if rel.startswith(ARCHIVE_DEST):
            sync._abspath(rel).unlink(missing_ok=True)
            self._emit(note_events.NOTE_DELETED, str(uuid.uuid4()), {"note_id": rel, "path": rel, "title": ""}, user_id)
            return {"deleted": True, "note_id": note_id}
        row = self._resolve_row(rel)
        if row.path.startswith("4_Архив") or row.status == "archived":
            filepath = sync._abspath(row.path)
            filepath.unlink(missing_ok=True)
            session = self._sf()
            try:
                session.delete(row)
                session.commit()
            finally:
                session.close()
        else:
            sync.archive_note(row.path)
        self._emit(note_events.NOTE_DELETED, str(uuid.uuid4()), {"note_id": row.path, "path": row.path, "title": row.title}, user_id)
        return {"deleted": True, "note_id": note_id}

    def tree(self) -> list[dict]:
        session = self._sf()
        try:
            rows = session.execute(select(IndexNote).order_by(IndexNote.path)).scalars().all()
        finally:
            session.close()
        nodes: list[dict] = []
        for row in rows:
            data = self._note_dict(row)
            nodes.append(
                {
                    "id": data["id"],
                    "title": data["title"],
                    "folder_id": data["folder_id"],
                    "importance": data["importance"],
                    "children": [],
                }
            )
        return nodes

    # ----- relations -----

    def add_relation(self, source_id: str, target_id: str, relation_type: str = "link") -> dict:
        source = self._resolve_row(source_id)
        target = self._resolve_row(target_id)
        if source.id == target.id:
            raise ValidationError("note cannot relate to itself")
        session = self._sf()
        try:
            existing = session.execute(
                select(IndexLink).where(IndexLink.source_id == source.id, IndexLink.target_path == target.path)
            ).scalars().first()
            if existing is not None:
                raise Conflict("relationship already exists")
            link = IndexLink(
                source_id=source.id,
                source_path=source.path,
                target_path=target.path,
                target_id=target.id,
                relation_type=relation_type or "link",
                label=target.title,
            )
            session.add(link)
            session.commit()
            session.refresh(link)
            return {
                "id": str(link.id),
                "source_id": str(link.source_id),
                "target_id": str(link.target_id) if link.target_id else link.target_path,
                "relation_type": link.relation_type,
                "created_at": link.created_at,
            }
        finally:
            session.close()

    def remove_relation(self, relation_id: str) -> None:
        session = self._sf()
        try:
            row = session.get(IndexLink, uuid.UUID(str(relation_id)))
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()

    def relationships(self, note_id: str) -> list[dict]:
        row = self._resolve_row(note_id)
        session = self._sf()
        try:
            links = session.execute(
                select(IndexLink).where(or_(IndexLink.source_id == row.id, IndexLink.target_id == row.id))
            ).scalars().all()
            return [
                {
                    "id": str(link.id),
                    "source_id": str(link.source_id),
                    "target_id": str(link.target_id) if link.target_id else link.target_path,
                    "relation_type": link.relation_type,
                    "created_at": link.created_at,
                }
                for link in links
            ]
        finally:
            session.close()

    # ----- folders -----

    def folders(self) -> list[dict]:
        now = _now()
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "description": "",
                "parent_id": f["parent_id"],
                "category_id": None,
                "user_id": None,
                "created_at": now,
                "updated_at": now,
            }
            for f in self._sync().list_folders()
        ]

    def create_folder(self, data: dict) -> dict:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValidationError("name is required")
        parent = str(data.get("parent_id") or "").strip("/")
        rel = f"{parent}/{name}".strip("/") if parent else name
        target = self._sync()._abspath(rel)
        target.mkdir(parents=True, exist_ok=True)
        now = _now()
        return {
            "id": rel,
            "name": name,
            "description": data.get("description") or "",
            "parent_id": parent if parent else None,
            "category_id": data.get("category_id"),
            "user_id": None,
            "created_at": now,
            "updated_at": now,
        }

    def update_folder(self, folder_id: str, data: dict) -> dict:
        sync = self._sync()
        old_rel = str(folder_id).strip("/")
        parent = str(Path(old_rel).parent.as_posix())
        name = data.get("name") or Path(old_rel).name
        new_rel = f"{parent}/{name}".strip("/") if parent != "." else name
        if new_rel != old_rel:
            src = sync._abspath(old_rel)
            dst = sync._abspath(new_rel)
            if src != sync.vault_path.resolve() and not dst.parent.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                src.rename(dst)
        now = _now()
        return {
            "id": new_rel,
            "name": name,
            "description": data.get("description") or "",
            "parent_id": parent if parent != "." else None,
            "category_id": data.get("category_id"),
            "user_id": None,
            "created_at": now,
            "updated_at": now,
        }

    def delete_folder(self, folder_id: str) -> dict:
        sync = self._sync()
        rel = str(folder_id).strip("/")
        session = self._sf()
        try:
            rows = session.execute(select(IndexNote).where(IndexNote.path.startswith(rel + "/"))).scalars().all()
            paths = [r.path for r in rows]
        finally:
            session.close()
        for path in paths:
            sync.archive_note(path)
        target = sync._abspath(rel)
        if target.exists() and target.is_dir():
            try:
                target.rmdir()
            except OSError:
                pass
        return {"deleted": True, "folder_id": folder_id}

    # ----- categories -----

    def categories(self) -> list[dict]:
        return [
            {"id": t, "name": t, "color": CATEGORY_COLORS.get(t, "#8b5cf6"), "created_at": _now()}
            for t in NOTES_TYPES
        ]

    def create_category(self, name: str, color: str = "#8b5cf6") -> dict:
        name = str(name).strip()
        if not name:
            raise ValidationError("name is required")
        now = _now()
        return {"id": name, "name": name, "color": color, "created_at": now}

    def rename_category(self, category_id: str, name: str, color: str | None = None) -> dict:
        return {"id": str(name), "name": str(name), "color": color or "#8b5cf6", "created_at": _now()}

    def delete_category(self, category_id: str) -> None:
        return None

    # ----- tags -----

    def tags(self) -> list[dict]:
        session = self._sf()
        try:
            rows = session.execute(select(IndexTag.name).distinct().order_by(IndexTag.name)).scalars().all()
            return [{"id": name, "name": name} for name in rows]
        finally:
            session.close()

    # ----- helpers -----

    def _hydrated(self, rel: str) -> dict:
        row = self._resolve_row(rel)
        return self._note_dict(row, content=_body(self._sync().read_note(row.path)))

    def _emit(self, event_type: str, aggregate_id, payload: dict, user_id: str | None) -> None:
        try:
            self._publish(
                event_type=event_type,
                aggregate_type="note",
                aggregate_id=str(aggregate_id),
                payload=payload,
                user_id=user_id,
            )
        except Exception:  # noqa: BLE001
            pass