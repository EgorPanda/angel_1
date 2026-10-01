from __future__ import annotations

import enum
import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.models import ConfirmationRecord, PermissionRule
from app.config import get_settings
from app.infrastructure.db import to_uuid

_uid = to_uuid


class PermissionMode(str, enum.Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    FORBID = "forbid"


class Decision:
    def __init__(self, mode: PermissionMode, confirmation_id: str | None = None) -> None:
        self.mode = mode
        self.confirmation_id = confirmation_id

    @property
    def allowed(self) -> bool:
        return self.mode == PermissionMode.ALLOW

    @property
    def needs_confirmation(self) -> bool:
        return self.mode == PermissionMode.CONFIRM


def hash_params(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PermissionService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def rules(self, user_id: str | None) -> dict[str, PermissionMode]:
        session = self._session()
        try:
            stmt = select(PermissionRule)
            if user_id is not None:
                stmt = stmt.where(PermissionRule.user_id == _uid(user_id))
            rows = session.execute(stmt).scalars().all()
            return {r.permission: PermissionMode(r.mode) for r in rows}
        finally:
            session.close()

    def set_rule(self, permission: str, mode, user_id: str | None = None) -> None:
        mode = mode if isinstance(mode, PermissionMode) else PermissionMode(str(mode))
        session = self._session()
        try:
            existing = session.execute(
                select(PermissionRule).where(
                    PermissionRule.user_id == _uid(user_id), PermissionRule.permission == permission
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(PermissionRule(user_id=_uid(user_id), permission=permission, mode=mode.value))
            else:
                existing.mode = mode.value
            session.commit()
        finally:
            session.close()

    def reset_rule(self, permission: str, user_id: str | None = None) -> None:
        session = self._session()
        try:
            session.execute(
                delete(PermissionRule).where(
                    PermissionRule.user_id == _uid(user_id), PermissionRule.permission == permission
                )
            )
            session.commit()
        finally:
            session.close()

    def mode_for(self, permission: str, default: PermissionMode, user_id: str | None = None) -> PermissionMode:
        session = self._session()
        try:
            row = session.execute(
                select(PermissionRule).where(
                    PermissionRule.user_id == _uid(user_id), PermissionRule.permission == permission
                )
            ).scalar_one_or_none()
            return PermissionMode(row.mode) if row else default
        finally:
            session.close()

    def request(self, permission: str, tool_name: str, params: dict, default: PermissionMode,
                user_id: str | None = None, message: str = "", correlation_id: str | None = None) -> Decision:
        mode = self.mode_for(permission, default, user_id)
        if mode != PermissionMode.CONFIRM:
            return Decision(mode)
        approved = self._consume_approved(permission, params, user_id)
        if approved:
            return Decision(PermissionMode.ALLOW)
        return Decision(PermissionMode.CONFIRM, self._create_pending(permission, tool_name, params, user_id, message, correlation_id))

    def _create_pending(self, permission: str, tool_name: str, params: dict, user_id: str | None,
                        message: str, correlation_id: str | None) -> str:
        settings = get_settings()
        session = self._session()
        try:
            record = ConfirmationRecord(
                user_id=_uid(user_id),
                permission=permission,
                tool_name=tool_name,
                params_json=params,
                params_hash=hash_params(params),
                status="pending",
                message=message,
                correlation_id=correlation_id,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.confirmation_ttl_seconds),
            )
            session.add(record)
            session.commit()
            return str(record.id)
        finally:
            session.close()

    def _consume_approved(self, permission: str, params: dict, user_id: str | None) -> bool:
        params_hash = hash_params(params)
        session = self._session()
        try:
            stmt = select(ConfirmationRecord).where(
                ConfirmationRecord.user_id == _uid(user_id),
                ConfirmationRecord.permission == permission,
                ConfirmationRecord.status == "approved",
            )
            candidates = session.execute(stmt).scalars().all()
            for candidate in candidates:
                if candidate.params_hash == params_hash and not _expired(candidate):
                    session.execute(
                        update(ConfirmationRecord)
                        .where(ConfirmationRecord.id == candidate.id)
                        .values(status="used", resolved_at=datetime.now(timezone.utc))
                    )
                    session.commit()
                    return True
                if _expired(candidate):
                    candidate.status = "expired"
            session.commit()
            return False
        finally:
            session.close()

    def pending(self, user_id: str | None) -> list[ConfirmationRecord]:
        session = self._session()
        try:
            stmt = select(ConfirmationRecord).where(ConfirmationRecord.status == "pending")
            if user_id is not None:
                stmt = stmt.where(ConfirmationRecord.user_id == _uid(user_id))
            rows = session.execute(stmt.order_by(ConfirmationRecord.created_at)).scalars().all()
            return list(rows)
        finally:
            session.close()

    def resolve(self, confirmation_id: str, approve: bool, user_id: str | None = None) -> ConfirmationRecord:
        session = self._session()
        try:
            record = session.get(ConfirmationRecord, _uid(confirmation_id))
            if record is None:
                raise KeyError("confirmation not found")
            if record.status != "pending":
                raise ValueError("confirmation is not pending")
            if user_id is not None and str(record.user_id) != str(user_id):
                raise PermissionError("confirmation belongs to another user")
            if _expired(record):
                record.status = "expired"
                session.commit()
                raise ValueError("confirmation expired")
            record.status = "approved" if approve else "denied"
            record.resolved_at = datetime.now(timezone.utc)
            session.commit()
            return record
        finally:
            session.close()


def _expired(record: ConfirmationRecord) -> bool:
    if record.expires_at is None:
        return False
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expires_at
