from __future__ import annotations

from datetime import datetime, timezone


def _dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:  # noqa: BLE001
        return None


def serialize_note(note) -> dict:
    if note is None:
        return {}
    data = note if isinstance(note, dict) else note.to_dict()
    return {
        "id": data.get("id"),
        "title": data.get("title") or "",
        "content": data.get("content") or "",
        "folder_id": data.get("folder_id"),
        "category_id": data.get("category_id") or data.get("note_type"),
        "parent_id": data.get("parent_id"),
        "importance": data.get("importance") or "medium",
        "status": data.get("status") or "active",
        "sort_order": int(data.get("sort_order") or 0),
        "user_id": data.get("user_id"),
        "created_at": _dt(data.get("created_at")) or datetime.now(timezone.utc),
        "updated_at": _dt(data.get("updated_at")) or datetime.now(timezone.utc),
        "tags": list(data.get("tags") or []),
    }


def serialize_folder(folder) -> dict:
    data = folder if isinstance(folder, dict) else folder.to_dict()
    now = datetime.now(timezone.utc)
    return {
        "id": data.get("id"),
        "name": data.get("name") or "",
        "description": data.get("description") or "",
        "parent_id": data.get("parent_id"),
        "category_id": data.get("category_id"),
        "user_id": data.get("user_id"),
        "created_at": _dt(data.get("created_at")) or now,
        "updated_at": _dt(data.get("updated_at")) or now,
    }


def serialize_category(category) -> dict:
    data = category if isinstance(category, dict) else category.to_dict()
    return {
        "id": data.get("id"),
        "name": data.get("name") or "",
        "color": data.get("color") or "#8b5cf6",
        "created_at": _dt(data.get("created_at")) or datetime.now(timezone.utc),
    }


def serialize_tag(tag) -> dict:
    data = tag if isinstance(tag, dict) else tag.to_dict()
    return {
        "id": data.get("id"),
        "name": data.get("name") or "",
    }


def serialize_relationship(rel) -> dict:
    data = rel if isinstance(rel, dict) else rel.to_dict()
    return {
        "id": data.get("id"),
        "source_id": data.get("source_id"),
        "target_id": data.get("target_id"),
        "relation_type": data.get("relation_type") or "link",
        "created_at": _dt(data.get("created_at")) or datetime.now(timezone.utc),
    }