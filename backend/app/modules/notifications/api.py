from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException


def _serialize(notification) -> dict:
    return {
        "id": str(notification.id),
        "channel": notification.channel,
        "title": notification.title,
        "text": notification.text,
        "status": notification.status,
        "read": notification.read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
    }


def build_router(service) -> APIRouter:
    router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

    @router.get("")
    def list_notifications(limit: int = 50, unread: bool = False):
        return [_serialize(n) for n in service.list(user_id=None, limit=limit, unread=unread)]

    @router.get("/channels")
    def channels():
        return {"channels": service.available_channels()}

    @router.post("/{notification_id}/read")
    def mark_read(notification_id: str):
        try:
            return _serialize(service.mark_read(notification_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.post("/read-all")
    def mark_all_read():
        return {"marked": service.mark_all_read()}

    return router