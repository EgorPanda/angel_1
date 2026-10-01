from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\]]*?))?\]\]")
TASK_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.+)$")
DUE_RE = re.compile(r"(?:📅|@)\s*(\d{4}-\d{2}-\d{2})")
HEADING_RE = re.compile(r"^#\s+(.+)$")


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1]) or {}
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _fm_datetime(data: dict, keys: tuple[str, ...]) -> datetime | None:
    for key in keys:
        value = data.get(key)
        if not value:
            continue
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except Exception:  # noqa: BLE001
            continue
    return None


def _body(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip("\n")
    return text


def parse_wikilinks(text: str) -> list[dict]:
    links: list[dict] = []
    for match in WIKILINK_RE.finditer(text):
        target = match.group(1).strip()
        label = (match.group(2) or "").strip() or target
        if target:
            links.append({"target": target, "label": label})
    return links


def parse_tasks(text: str) -> list[dict]:
    tasks: list[dict] = []
    for match in TASK_RE.finditer(text):
        done = match.group(1).lower() in ("x", "X")
        raw = match.group(2).strip()
        due_match = DUE_RE.search(raw)
        due = None
        if due_match:
            try:
                due = datetime.fromisoformat(due_match.group(1))
            except ValueError:  # noqa: PERF203
                due = None
        text_clean = DUE_RE.sub("", raw).strip()
        tasks.append({"text": text_clean, "done": done, "due": due})
    fm = parse_frontmatter(text)
    fm_tasks = fm.get("tasks", [])
    if isinstance(fm_tasks, list):
        for item in fm_tasks:
            if isinstance(item, str):
                con = TASK_RE.match(item)
                if con:
                    tasks.append({"text": con.group(2).strip(), "done": con.group(1).lower() in ("x", "X"), "due": None})
                else:
                    tasks.append({"text": item.strip(), "done": False, "due": None})
            elif isinstance(item, dict):
                tasks.append(
                    {
                        "text": str(item.get("text", "")),
                        "done": bool(item.get("done", False)),
                        "due": item.get("due"),
                    }
                )
    return tasks


def parse_title(text: str, path: Path) -> str:
    fm = parse_frontmatter(text)
    if fm.get("title"):
        return str(fm["title"]).strip()
    for line in _body(text).splitlines():
        match = HEADING_RE.match(line)
        if match:
            return match.group(1).strip()
    return path.stem or "untitled"


def parse_note(text: str, path: Path) -> dict:
    fm = parse_frontmatter(text)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) if path.exists() else None
    created = _fm_datetime(fm, ("created_at", "created")) or mtime
    updated = _fm_datetime(fm, ("updated_at", "updated")) or mtime
    tags = [str(t).strip("#").strip() for t in (fm.get("tags") or []) if str(t).strip()]
    if "tag" in fm and str(fm.get("tag")).strip():
        tags.append(str(fm["tag"]).strip("#").strip())
    return {
        "title": parse_title(text, path),
        "note_type": str(fm.get("type") or "note").strip(),
        "business": str(fm.get("business") or "").strip(),
        "status": str(fm.get("status") or "active").strip(),
        "importance": str(fm.get("importance") or "medium").strip(),
        "summary": str(fm.get("summary") or "").strip(),
        "tags": [t for t in dict.fromkeys(tags) if t],
        "id": fm.get("id"),
        "created_at": created,
        "updated_at": updated,
    }


def render_frontmatter(meta: dict) -> str:
    data: dict = {}
    for key in ("id", "title", "type", "business", "status", "importance", "tags", "summary", "created_at", "updated_at"):
        value = meta.get(key)
        if value in (None, "", [], {}):
            continue
        data[key] = value
    fm = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).rstrip()
    return f"---\n{fm}\n---\n\n"