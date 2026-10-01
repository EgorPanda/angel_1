from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NoteBase(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    content: str = Field(default="", max_length=1_000_000)
    folder_id: str | None = None
    category_id: str | None = None
    parent_id: str | None = None
    importance: Literal["low", "medium", "high"] = "medium"
    tags: list[str] = Field(default_factory=list)


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    content: str | None = Field(default=None, max_length=1_000_000)
    folder_id: str | None = None
    category_id: str | None = None
    parent_id: str | None = None
    importance: Literal["low", "medium", "high"] | None = None
    tags: list[str] | None = None


class NoteOut(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    sort_order: int = 0
    user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class NoteDetail(NoteOut):
    children_ids: list[str] = Field(default_factory=list)
    relationships: list[dict] = Field(default_factory=list)


class NoteSearchResult(BaseModel):
    id: str
    title: str
    folder_id: str | None = None
    category_id: str | None = None
    importance: str = "medium"
    updated_at: datetime
    snippet: str = ""


class FolderBase(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="")
    parent_id: str | None = None
    category_id: str | None = None


class FolderCreate(FolderBase):
    pass


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    parent_id: str | None = None
    category_id: str | None = None


class FolderOut(FolderBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str = Field(default="#8b5cf6", max_length=32)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)


class CategoryOut(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class RelationshipCreate(BaseModel):
    target_id: str
    relation_type: str = "related"


class RelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    target_id: str
    relation_type: str
    created_at: datetime


class NoteTreeItem(BaseModel):
    id: str
    title: str
    folder_id: str | None = None
    importance: str = "medium"
    children: list["NoteTreeItem"] = Field(default_factory=list)


NoteTreeItem.model_rebuild()