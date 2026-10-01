from __future__ import annotations

import uuid

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from app.modules.notes.models import Category, Folder, Note, NoteRelationship, Tag, note_tags


class NotesRepository:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def session(self) -> Session:
        return self._sf()

    def get(self, session: Session, note_id: str) -> Note | None:
        return session.get(Note, uuid.UUID(note_id))

    def get_mapped(self, session: Session, note_id: str) -> Note | None:
        return self.get(session, note_id)

    def list_ids(self, session: Session, ids: list[str]) -> list[Note]:
        uuids = [uuid.UUID(i) for i in ids]
        return list(session.execute(select(Note).where(Note.id.in_(uuids))).scalars().all())

    def by_folder(self, session: Session, folder_id: str | None) -> list[Note]:
        if folder_id is None:
            return list(session.execute(select(Note).where(Note.folder_id.is_(None)).order_by(Note.sort_order, Note.title)).scalars().all())
        return list(session.execute(select(Note).where(Note.folder_id == uuid.UUID(folder_id)).order_by(Note.sort_order, Note.title)).scalars().all())

    def all(self, session: Session) -> list[Note]:
        return list(session.execute(select(Note).order_by(Note.sort_order, Note.title)).scalars().all())

    def children(self, session: Session, note_id: str) -> list[Note]:
        return list(session.execute(
            select(Note).where(Note.parent_id == uuid.UUID(note_id)).order_by(Note.sort_order, Note.title)
        ).scalars().all())

    def descendants(self, session: Session, note_id: str) -> list[uuid.UUID]:
        result: list[uuid.UUID] = []
        frontier = {uuid.UUID(note_id)}
        while frontier:
            ids = list(frontier)
            rows = session.execute(select(Note.id).where(Note.parent_id.in_(ids))).scalars().all()
            result.extend(rows)
            frontier = set(rows)
        return result

    def ancestors(self, session: Session, note_id: str) -> list[uuid.UUID]:
        ancestors: list[uuid.UUID] = []
        current = session.get(Note, uuid.UUID(note_id))
        seen: set[uuid.UUID] = set()
        while current is not None and current.parent_id is not None:
            if current.parent_id in seen:
                break
            seen.add(current.parent_id)
            ancestors.append(current.parent_id)
            current = session.get(Note, current.parent_id)
        return ancestors

    def search(self, session: Session, query: str, category_id: str | None = None,
               tag: str | None = None, limit: int = 50) -> list[Note]:
        stmt = select(Note).where(Note.status == "active")
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
        if category_id:
            stmt = stmt.where(Note.category_id == uuid.UUID(category_id))
        if tag:
            stmt = stmt.join(note_tags).join(Tag).where(Tag.name == tag)
        return list(session.execute(stmt.order_by(Note.updated_at.desc()).limit(limit)).scalars().all())

    def tag_ids(self, session: Session, names: list[str]) -> dict[str, Tag]:
        if not names:
            return {}
        found = {t.name: t for t in session.execute(select(Tag).where(Tag.name.in_(names))).scalars().all()}
        return found

    def save_tags(self, session: Session, note: Note, names: list[str]) -> None:
        found = self.tag_ids(session, names)
        note.tags = []
        for name in names:
            tag = found.get(name)
            if tag is None:
                tag = Tag(name=name)
                session.add(tag)
            note.tags.append(tag)

    def relationships(self, session: Session, note_id: str) -> list[NoteRelationship]:
        nid = uuid.UUID(note_id)
        return list(session.execute(
            select(NoteRelationship).where(or_(NoteRelationship.source_id == nid, NoteRelationship.target_id == nid))
        ).scalars().all())

    def relation_exists(self, session: Session, source_id: str, target_id: str, relation_type: str) -> bool:
        stmt = select(NoteRelationship.id).where(
            NoteRelationship.source_id == uuid.UUID(source_id),
            NoteRelationship.target_id == uuid.UUID(target_id),
            NoteRelationship.relation_type == relation_type,
        )
        return session.execute(stmt).scalar_one_or_none() is not None

    def add_relation(self, session: Session, source_id: str, target_id: str, relation_type: str) -> NoteRelationship:
        rel = NoteRelationship(source_id=uuid.UUID(source_id), target_id=uuid.UUID(target_id), relation_type=relation_type)
        session.add(rel)
        return rel

    def delete_relation(self, session: Session, relation_id: str) -> None:
        session.execute(delete(NoteRelationship).where(NoteRelationship.id == uuid.UUID(relation_id)))

    def categories(self, session: Session) -> list[Category]:
        return list(session.execute(select(Category).order_by(Category.name)).scalars().all())

    def get_category(self, session: Session, category_id: str) -> Category | None:
        return session.get(Category, uuid.UUID(category_id))

    def category_by_name(self, session: Session, name: str) -> Category | None:
        return session.execute(select(Category).where(Category.name == name)).scalar_one_or_none()

    def tags(self, session: Session) -> list[Tag]:
        return list(session.execute(select(Tag).order_by(Tag.name)).scalars().all())

    def get_tag(self, session: Session, tag_id: str) -> Tag | None:
        return session.get(Tag, uuid.UUID(tag_id))

    def tag_by_name(self, session: Session, name: str) -> Tag | None:
        return session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()

    def folders(self, session: Session) -> list[Folder]:
        return list(session.execute(select(Folder).order_by(Folder.name)).scalars().all())

    def get_folder(self, session: Session, folder_id: str) -> Folder | None:
        return session.get(Folder, uuid.UUID(folder_id))

    def folder_by_name(self, session: Session, name: str, parent_id: str | None) -> Folder | None:
        stmt = select(Folder).where(Folder.name == name)
        if parent_id is None:
            stmt = stmt.where(Folder.parent_id.is_(None))
        else:
            stmt = stmt.where(Folder.parent_id == uuid.UUID(parent_id))
        return session.execute(stmt).scalar_one_or_none()

    def folder_descendants(self, session: Session, folder_id: str) -> list[uuid.UUID]:
        result: list[uuid.UUID] = []
        frontier = {uuid.UUID(folder_id)}
        while frontier:
            ids = list(frontier)
            rows = session.execute(select(Folder.id).where(Folder.parent_id.in_(ids))).scalars().all()
            result.extend(rows)
            frontier = set(rows)
        return result