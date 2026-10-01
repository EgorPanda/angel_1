from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from app.core.models import ActivityRecord
from app.infrastructure.db import to_uuid


class ActivityService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def log(self, user_id: str | None, actor: str, action: str, module: str = "",
            tool: str | None = None, status: str = "ok", task_id: str | None = None,
            correlation_id: str | None = None, duration_ms: int | None = None,
            metadata: dict[str, Any] | None = None) -> str:
        session = self._session_factory()
        try:
            record = ActivityRecord(
                user_id=to_uuid(user_id),
                actor=actor,
                action=action,
                module=module,
                tool=tool,
                status=status,
                task_id=task_id,
                correlation_id=correlation_id,
                duration_ms=duration_ms,
                metadata_json=metadata or {},
            )
            session.add(record)
            session.commit()
            return str(record.id)
        finally:
            session.close()

    def record(self, **kwargs) -> str:
        return self.log(**kwargs)

    def list_recent(self, user_id: str | None = None, limit: int = 100) -> list[ActivityRecord]:
        session = self._session_factory()
        try:
            stmt = select(ActivityRecord).order_by(ActivityRecord.created_at.desc()).limit(limit)
            if user_id is not None:
                stmt = stmt.where(ActivityRecord.user_id == to_uuid(user_id))
            return list(session.execute(stmt).scalars().all())
        finally:
            session.close()


class Timing:
    def __init__(self, activity: ActivityService, user_id: str | None, actor: str, action: str, **ctx) -> None:
        self._activity = activity
        self._user_id = user_id
        self._actor = actor
        self._action = action
        self._ctx = ctx
        self._started = time.monotonic()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        duration = int((time.monotonic() - self._started) * 1000)
        status = "error" if exc_type is not None else "ok"
        self._activity.log(
            user_id=self._user_id, actor=self._actor, action=self._action,
            status=status, duration_ms=duration, **self._ctx,
        )

    def success(self, **extra) -> str:
        return self._activity.log(
            user_id=self._user_id, actor=self._actor, duration_ms=int((time.monotonic() - self._started) * 1000),
            action=self._action, **{**self._ctx, **extra},
        )