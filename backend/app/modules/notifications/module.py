from __future__ import annotations

from app.core.module import Module
from app.modules.notifications.api import build_router
from app.modules.notifications.service import NotificationService


class NotificationsModule(Module):
    name = "notifications"
    version = "0.1.0"
    description = "Notification delivery through multiple channels (web, telegram and future channels)."
    description_ru = "Доставка уведомлений по каналам (web, telegram и др.)."
    capabilities = ["notifications.send", "notifications.channels"]

    def __init__(self) -> None:
        super().__init__()
        self.service: NotificationService | None = None

    def on_register(self, core) -> None:
        self.service = NotificationService(core.session_factory, core.publish)
        from app.modules.notifications import tools as notification_tools

        self.tools = notification_tools.build_tools(self.service)
        self.routers = [build_router(self.service)]
        super().on_register(core)

    def health_check(self) -> tuple[bool, str]:
        if self.service is None:
            return False, "service not initialized"
        return True, "ok"

    def info(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "dependencies": list(self.dependencies),
        }