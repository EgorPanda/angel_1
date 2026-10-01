from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy import select

from app.modules.notifications import events as notification_events
from app.modules.notifications.models import Notification


class NotificationChannel(ABC):
    name: str = ""

    @abstractmethod
    def send(self, user_id: str | None, title: str, text: str) -> bool:
        ...


class NotificationService:
    def __init__(self, session_factory, event_publish) -> None:
        self._sf = session_factory
        self._publish = event_publish
        self.channels: dict[str, NotificationChannel] = {"web": WebChannel(session_factory)}

    def register_channel(self, channel: NotificationChannel) -> None:
        self.channels[channel.name] = channel

    def available_channels(self) -> list[str]:
        return list(self.channels.keys())

    def send(self, text: str, channel: str = "web", user_id: str | None = None, title: str = "") -> Notification:
        channel_name = channel or "web"
        adapter = self.channels.get(channel_name)
        if adapter is None:
            adapter = self.channels["web"]
        notification = Notification(user_id=_u(user_id), channel=adapter.name, title=title, text=text, status="pending")
        session = self._sf()
        try:
            session.add(notification)
            session.commit()
            session.refresh(notification)
        finally:
            session.close()
        self._publish_event(
            notification_events.NOTIFICATION_REQUESTED,
            str(notification.id),
            {"notification_id": str(notification.id), "channel": adapter.name, "text": text, "user_id": user_id},
        )
        ok = adapter.send(user_id, title, text)
        session = self._sf()
        try:
            notification = session.get(Notification, notification.id)
            if notification is not None:
                notification.status = "sent" if ok else "failed"
                notification.sent_at = datetime.now(timezone.utc)
                session.commit()
                session.refresh(notification)
        finally:
            session.close()
        self._publish_event(
            notification_events.NOTIFICATION_SENT,
            str(notification.id),
            {"notification_id": str(notification.id), "channel": adapter.name, "status": notification.status},
        )
        return notification

    def list(self, user_id: str | None = None, limit: int = 50, unread: bool = False) -> list[Notification]:
        session = self._sf()
        try:
            stmt = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
            if user_id is not None:
                stmt = stmt.where(Notification.user_id == _u(user_id))
            if unread:
                stmt = stmt.where(Notification.read.is_(False))
            return list(session.execute(stmt).scalars().all())
        finally:
            session.close()

    def mark_read(self, notification_id: str) -> Notification:
        session = self._sf()
        try:
            notification = session.get(Notification, uuid.UUID(notification_id))
            if notification is None:
                raise KeyError("notification not found")
            notification.read = True
            notification.read_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(notification)
            return notification
        finally:
            session.close()

    def mark_all_read(self, user_id: str | None = None) -> int:
        session = self._sf()
        try:
            rows = list(session.execute(
                select(Notification).where(Notification.read.is_(False))
            ).scalars().all())
            for row in rows:
                row.read = True
                row.read_at = datetime.now(timezone.utc)
            session.commit()
            return len(rows)
        finally:
            session.close()

    def _publish_event(self, event_type: str, aggregate_id: str, payload: dict) -> None:
        try:
            self._publish(event_type=event_type, aggregate_type="notification", aggregate_id=aggregate_id, payload=payload)
        except Exception:  # noqa: BLE001
            pass


class WebChannel(NotificationChannel):
    name = "web"

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def send(self, user_id: str | None, title: str, text: str) -> bool:
        return True


def _u(value: str | None):
    if value in (None, ""):
        return None
    return uuid.UUID(str(value))