from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db import Base, utcnow


class IndexNote(Base):
    __tablename__ = "index_notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    note_type: Mapped[str] = mapped_column(String(32), nullable=False, default="note")
    business: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(String, nullable=False, default="")
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    file_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tags = relationship("IndexTag", back_populates="note", cascade="all, delete-orphan", lazy="selectin")
    tasks = relationship("IndexTask", back_populates="note", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_index_notes_folder", "path"),
        Index("ix_index_notes_type", "note_type"),
        Index("ix_index_notes_status", "status"),
        Index("ix_index_notes_title", "title"),
    )


class IndexTag(Base):
    __tablename__ = "index_tags"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    index_note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("index_notes.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    note = relationship("IndexNote", back_populates="tags")

    __table_args__ = (
        UniqueConstraint("index_note_id", "name", name="uq_index_tag"),
        Index("ix_index_tags_name", "name"),
    )


class IndexLink(Base):
    __tablename__ = "index_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("index_notes.id", ondelete="CASCADE"), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    target_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("index_notes.id", ondelete="SET NULL"), nullable=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, default="link")
    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "target_path", name="uq_index_link"),
        Index("ix_index_links_source", "source_id"),
        Index("ix_index_links_target_path", "target_path"),
    )


class IndexTask(Base):
    __tablename__ = "index_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    index_note_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("index_notes.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    note = relationship("IndexNote", back_populates="tasks")

    __table_args__ = (
        Index("ix_index_tasks_note", "index_note_id"),
        Index("ix_index_tasks_done", "done"),
        Index("ix_index_tasks_due", "due"),
    )


class Moc(Base):
    __tablename__ = "mocs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    folder: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    note_path: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    structure: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ArchiveMoc(Base):
    __tablename__ = "archive_mocs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    original_folder: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    restored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String, nullable=False, default="")
    indexed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


__all__ = [
    "IndexNote",
    "IndexTag",
    "IndexLink",
    "IndexTask",
    "Moc",
    "ArchiveMoc",
    "SyncState",
]