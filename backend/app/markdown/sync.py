from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.logging import get_logger
from app.modules.notes.index_models import IndexLink, IndexNote, IndexTag, IndexTask, Moc, ArchiveMoc, SyncState
from app.modules.notes.markdown_parser import parse_frontmatter, parse_note, parse_tasks, parse_wikilinks

logger = get_logger("markdown.sync")

INDEX_FOLDERS = ("0_Входящие", "1_МоиПроекты", "2_Области", "3_Ресурсы", "5_Шаблоны")
ARCHIVE_FOLDER = "4_Архив"
ARCHIVE_MOC_NAME = "Архив_MOC.md"
MOC_SUFFIX = "_MOC.md"
SKIP_DIRS = {".obsidian", ".git", "Attachments", "__pycache__"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MarkdownSyncService:
    def __init__(self, session_factory, vault_path: str) -> None:
        self._sf = session_factory
        self.vault_path = Path(vault_path)

    def enabled(self) -> bool:
        return self.vault_path is not None and str(self.vault_path) != ""

    def _ensure_root(self) -> None:
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.vault_path).as_posix()

    def _abspath(self, rel: str) -> Path:
        target = (self.vault_path / rel).resolve()
        root = self.vault_path.resolve()
        if root not in target.parents and target != root:
            raise ValueError(f"path escapes vault: {rel}")
        return target

    def _in_archive(self, rel: str) -> bool:
        return rel.startswith(ARCHIVE_FOLDER + "/") or rel == ARCHIVE_FOLDER

    def _in_index_scope(self, rel: str) -> bool:
        return any(rel.startswith(f + "/") or rel == f for f in INDEX_FOLDERS)

    def _walk_md_files(self) -> list[Path]:
        if not self.vault_path.exists():
            return []
        files: list[Path] = []
        for root, dirs, names in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                if not name.endswith(".md"):
                    continue
                candidate = Path(root) / name
                rel = self._rel(candidate)
                if self._in_archive(rel) or self._in_index_scope(rel):
                    files.append(candidate)
        return files

    # ----- full sync (vault -> index) -----

    def full_sync(self) -> dict:
        if not self.enabled():
            return {"indexed": 0, "removed": 0, "disabled": True, "error": ""}
        self._ensure_root()
        session = self._sf()
        indexed = 0
        removed = 0
        error = ""
        try:
            scanned: set[str] = set()
            moc_paths: set[str] = set()
            for filepath in self._walk_md_files():
                rel = self._rel(filepath)
                scanned.add(rel)
                try:
                    if self._in_archive(rel):
                        if filepath.name == ARCHIVE_MOC_NAME:
                            self._index_archive(session, rel)
                            moc_paths.add(rel)
                        continue
                    if filepath.name.endswith(MOC_SUFFIX):
                        self._index_moc(session, rel)
                        moc_paths.add(rel)
                    self._index_note_file(session, rel)
                    indexed += 1
                except Exception:  # noqa: BLE001
                    logger.exception("failed to index %s", rel)
                    error = f"{rel}: {error}"[:2000] if error else rel
            removed = self._cleanup(session, scanned)
            self._regenerate_mocs(session)
            self._update_state(session, indexed, error)
            logger.info("markdown index finished: %s notes", indexed)
            return {"indexed": indexed, "removed": removed, "disabled": False, "error": error}
        finally:
            session.close()

    def _index_note_file(self, session, rel: str) -> None:
        filepath = self._abspath(rel)
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        data = parse_note(text, filepath)
        row = session.execute(select(IndexNote).where(IndexNote.path == rel)).scalars().first()
        if row is None:
            row = IndexNote(path=rel)
            session.add(row)
        row.title = data["title"]
        row.note_type = data["note_type"]
        row.business = data["business"]
        row.status = "archived" if self._in_archive(rel) else (data["status"] or "active")
        row.importance = data["importance"]
        row.summary = data["summary"]
        if data["created_at"]:
            row.created_at = data["created_at"]
        if data["updated_at"]:
            row.updated_at = data["updated_at"]
            row.file_updated_at = data["updated_at"]
        if data["id"]:
            try:
                row.id = uuid.UUID(str(data["id"]))
            except (ValueError, TypeError):  # noqa: PERF203
                pass
        session.flush()
        self._replace_tags(session, row, data["tags"])
        self._replace_links(session, row, parse_wikilinks(text), rel)
        self._replace_tasks(session, row, parse_tasks(text))

    def _replace_tags(self, session, row: IndexNote, names: list[str]) -> None:
        session.execute(IndexTag.__table__.delete().where(IndexTag.index_note_id == row.id))
        for name in names:
            session.add(IndexTag(index_note_id=row.id, name=name))

    def _replace_links(self, session, row: IndexNote, links: list[dict], rel: str) -> None:
        session.execute(IndexLink.__table__.delete().where(IndexLink.source_id == row.id))
        seen: set[str] = set()
        for link in links:
            target = link["target"]
            if target in seen:
                continue
            seen.add(target)
            session.add(
                IndexLink(
                    source_id=row.id,
                    source_path=rel,
                    target_path=target,
                    target_id=None,
                    relation_type="link",
                    label=link.get("label", ""),
                )
            )

    def _replace_tasks(self, session, row: IndexNote, tasks: list[dict]) -> None:
        session.execute(IndexTask.__table__.delete().where(IndexTask.index_note_id == row.id))
        for task in tasks:
            session.add(
                IndexTask(
                    index_note_id=row.id,
                    text=task.get("text", ""),
                    done=bool(task.get("done")),
                    due=task.get("due"),
                    priority="medium",
                )
            )

    def _index_moc(self, session, rel: str) -> None:
        filepath = self._abspath(rel)
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        folder = filepath.parent.name
        structure = parse_wikilinks(text)
        row = session.execute(select(Moc).where(Moc.note_path == rel)).scalars().first()
        if row is None:
            row = Moc(folder=folder, note_path=rel)
            session.add(row)
        row.folder = folder
        row.structure = {"links": structure}
        row.updated_at = _now()

    def _index_archive(self, session, rel: str) -> None:
        filepath = self._abspath(rel)
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        for link in parse_wikilinks(text):
            name = (link.get("label") or link.get("target") or "").strip()
            if not name or name.endswith(MOC_SUFFIX) or name.endswith("_MOC"):
                continue
            existing = session.execute(select(ArchiveMoc).where(ArchiveMoc.project_name == name)).scalars().first()
            if existing is None:
                session.add(
                    ArchiveMoc(
                        project_name=name,
                        description="",
                        original_folder=ARCHIVE_FOLDER,
                        restored=False,
                    )
                )

    def _regenerate_mocs(self, session) -> None:
        for folder in INDEX_FOLDERS:
            folder_path = self.vault_path / folder
            if not folder_path.is_dir():
                continue
            note_paths: list[str] = []
            for filepath in sorted(folder_path.rglob("*.md")):
                rel = self._rel(filepath)
                if filepath.name.endswith(MOC_SUFFIX) or ".obsidian" in rel:
                    continue
                note_paths.append(rel)
            title = f"# {folder}\n\n"
            body = "".join(f"- [[{_title_of(session, rel)}]]\n" for rel in note_paths)
            moc_rel = f"{folder}/{folder}_MOC.md"
            text = title + body
            current = ""
            existing = self._abspath(moc_rel)
            if existing.exists():
                current = existing.read_text(encoding="utf-8", errors="ignore")
            if current == text:
                continue
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text(text, encoding="utf-8")
            self._index_moc(session, moc_rel)

    def _cleanup(self, session, scanned: set[str]) -> int:
        removed = 0
        rows = session.execute(select(IndexNote)).scalars().all()
        for row in rows:
            if row.path in scanned or row.status == "archived":
                continue
            session.delete(row)
            removed += 1
        for moc in session.execute(select(Moc)).scalars().all():
            if moc.note_path not in scanned:
                session.delete(moc)
        return removed

    def _update_state(self, session, indexed: int, error: str) -> None:
        state = session.execute(select(SyncState).where(SyncState.id == 1)).scalars().first()
        if state is None:
            state = SyncState(id=1)
            session.add(state)
        state.last_sync_at = _now()
        state.indexed_count = indexed
        state.last_error = error
        session.commit()

    def status(self) -> dict:
        session = self._sf()
        try:
            state = session.execute(select(SyncState).where(SyncState.id == 1)).scalars().first()
            return {
                "vault_path": str(self.vault_path),
                "last_sync_at": state.last_sync_at.isoformat() if state and state.last_sync_at else None,
                "indexed": state.indexed_count if state else 0,
                "last_error": state.last_error if state else "",
            }
        finally:
            session.close()

    # ----- single note ops -----

    def sync_note(self, note_id: str) -> dict:
        rel = self._resolve_rel(note_id)
        if rel is None:
            return {"indexed": 0, "removed": 0, "disabled": False}
        session = self._sf()
        try:
            self._index_note_file(session, rel)
            session.commit()
            return {"indexed": 1, "removed": 0, "disabled": False}
        finally:
            session.close()

    def delete_note(self, note_id: str) -> dict:
        rel = self._resolve_rel(note_id)
        if rel is None:
            return {"indexed": 0, "removed": 0, "disabled": False}
        self.archive_note(rel)
        return {"indexed": 0, "removed": 1, "disabled": False}

    def sync_folder(self, folder: str) -> dict:
        session = self._sf()
        try:
            for row in session.execute(select(IndexNote)).scalars().all():
                if row.path.startswith(folder.strip("/") + "/"):
                    session.delete(row)
            session.commit()
        finally:
            session.close()
        return self.full_sync()

    def _resolve_rel(self, note_id: str) -> str | None:
        if note_id.endswith(".md"):
            return note_id if self._in_archive(note_id) or self._in_index_scope(note_id) else None
        try:
            target = uuid.UUID(str(note_id))
        except (ValueError, TypeError):  # noqa: PERF203
            return None
        session = self._sf()
        try:
            row = session.execute(select(IndexNote).where(IndexNote.id == target)).scalars().first()
            if row is not None:
                return row.path
            for filepath in self._walk_md_files():
                rel = self._rel(filepath)
                if self._in_archive(rel):
                    continue
                data = parse_frontmatter(filepath.read_text(encoding="utf-8", errors="ignore"))
                if str(data.get("id")) == str(note_id):
                    return rel
        finally:
            session.close()
        return None

    # ----- write / move helpers (used by notes service) -----

    def read_note(self, rel: str) -> str:
        if rel.endswith(".md"):
            try:
                filepath = self._abspath(rel)
            except ValueError:
                return ""
        else:
            resolved = self._resolve_rel(rel)
            if resolved is None:
                return ""
            filepath = self._abspath(resolved)
        if not filepath.exists():
            return ""
        return filepath.read_text(encoding="utf-8", errors="ignore")

    def save_note(self, note: "NotePayload") -> str:
        rel = self._normalize_write_path(note["path"])
        text = note["text"].rstrip() + "\n"
        filepath = self._abspath(rel)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(text, encoding="utf-8")
        return rel

    def move_note(self, rel: str, new_rel: str) -> str:
        src = self._abspath(self._normalize_write_path(rel))
        dst = self._abspath(self._normalize_write_path(new_rel))
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            src.rename(dst)
        return self._rel(dst)

    def archive_note(self, rel: str) -> str:
        src = self._abspath(rel)
        if not src.exists():
            return rel
        archive_dir = self.vault_path / ARCHIVE_FOLDER / "Архивированные"
        archive_dir.mkdir(parents=True, exist_ok=True)
        dst = archive_dir / f"{src.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        counter = 1
        while dst.exists():
            dst = archive_dir / f"{src.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{counter}.md"
            counter += 1
        src.rename(dst)
        new_rel = self._rel(dst)
        session = self._sf()
        try:
            row = session.execute(select(IndexNote).where(IndexNote.path == rel)).scalars().first()
            if row is not None:
                session.delete(row)
            session.commit()
        finally:
            session.close()
        return new_rel

    def list_folders(self) -> list[dict]:
        folders: list[dict] = []
        for root, dirs, _ in os.walk(self.vault_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != ARCHIVE_FOLDER]
            root_path = Path(root)
            for name in dirs:
                full = root_path / name
                rel = self._rel(full)
                if rel.split("/", 1)[0] in SKIP_DIRS:
                    continue
                folders.append(
                    {
                        "id": rel,
                        "name": name,
                        "parent_id": self._rel(root_path) if root_path != self.vault_path else None,
                    }
                )
        return folders

    def path_for_new_note(self, folder_rel: str, title: str) -> str:
        safe_folder = self._normalize_write_path(folder_rel)
        base = self.vault_path / safe_folder / _slug(title)
        candidate = base.with_suffix(".md")
        counter = 1
        while candidate.exists():
            candidate = base.with_name(f"{base.name}-{counter}").with_suffix(".md")
            counter += 1
        return self._rel(candidate)

    def _normalize_write_path(self, rel: str) -> str:
        clean = rel.replace("\\", "/").strip("/")
        parts = [p for p in clean.split("/") if p and p != ".."]
        if not parts or parts[0] in (".obsidian", ".git", "Attachments"):
            raise ValueError(f"path not allowed: {rel}")
        return "/".join(parts)


class NotePayload(dict):
    pass


def _title_of(session, rel: str) -> str:
    row = session.execute(select(IndexNote).where(IndexNote.path == rel)).scalars().first()
    if row is not None:
        return row.title or Path(rel).stem
    return Path(rel).stem


def _slug(name: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "untitled"


def iso(dt) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()