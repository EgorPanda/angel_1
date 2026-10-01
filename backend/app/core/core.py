from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from sqlalchemy import select

from app.config import Settings, get_settings
from app.core.activity import ActivityService
from app.core.errors import DatabaseError
from app.core.events import Event, EventBus, InProcessCommandBus, Command
from app.core.health import HealthChecker
from app.core.lifecycle import Lifecycle, SystemState
from app.core.logging import log_extra, get_logger
from app.core.models import EventRecord, User
from app.core.module_config import ModuleConfigService
from app.core.permissions import PermissionService
from app.core.registry import ModuleRegistry
from app.core.tools import ToolRegistry
from app.infrastructure.db import get_engine, get_session_factory, init_db, to_uuid
from app.workers.runner import WorkerPool

logger = get_logger("core")


class Core:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.lifecycle = Lifecycle()
        self.session_factory = get_session_factory()
        self.tools = ToolRegistry()
        self.modules = ModuleRegistry()
        self.permissions = PermissionService(self.session_factory)
        self.activity = ActivityService(self.session_factory)
        self.module_config = ModuleConfigService(self.session_factory)
        self.health = HealthChecker()
        self.command_bus = InProcessCommandBus()
        self.confirmations = self.permissions
        self.llm: Any = None
        self.ai_runtime: Any = None
        self.telegram: Any = None
        self.worker_pool = WorkerPool(
            concurrency=settings.worker_concurrency,
            retry_policy=settings.worker_retry_attempts,
        )
        self._module_routers: list[Any] = []
        self._event_tasks: list[asyncio.Task] = []

        def sink(event: Event) -> None:  # noqa: E731
            self._persist_event(event)

        self.events = EventBus(sink=sink)

    def _persist_event(self, event: Event) -> None:
        try:
            session = self.session_factory()
            try:
                record = EventRecord(
                    event_type=event.type,
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    payload=event.payload,
                    user_id=to_uuid(event.user_id),
                    correlation_id=event.correlation_id,
                )
                session.add(record)
                session.commit()
            finally:
                session.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("failed to persist event %s: %s", event.type, exc, exc_info=True)

    def include_module_router(self, module: Any) -> None:
        for router in module.routers:
            self._module_routers.append(router)

    @property
    def module_routers(self) -> list[Any]:
        return list(self._module_routers)

    def register_module(self, module: Any) -> None:
        logger.info("registering module %s v%s", module.name, module.version)
        module.on_register(self)
        self.modules.register(module)

    def get_module(self, name: str):
        return self.modules.require(name)

    def default_user(self) -> User:
        session = self.session_factory()
        try:
            row = session.execute(
                select(User).where(User.username == self.settings.default_user_username)
            ).scalar_one_or_none()
            if row is None:
                row = User(username=self.settings.default_user_username, settings={}, role="owner", full_name="Angel")
                session.add(row)
                session.commit()
                session.refresh(row)
            elif row.role != "owner":
                row.role = "owner"
                session.commit()
            return row
        except Exception as exc:  # noqa: BLE001
            logger.error("default user lookup failed: %s", exc, exc_info=True)
            raise DatabaseError(str(exc)) from exc
        finally:
            session.close()

    def user_id(self) -> str:
        return str(self.default_user().id)

    def reload_llm(self) -> None:
        """Пересобирает LLM-провайдер из текущих настроек (используется модулем ai при перезапуске)."""
        from app.ai.providers.factory import build_provider

        self.llm = build_provider(self.settings)
        if getattr(self, "ai_runtime", None) is not None:
            self.ai_runtime.agent = None

    def timestamp(self) -> str:
        return str(int(time.time()))

    def new_correlation_id(self) -> str:
        return str(uuid.uuid4())

    def event(self, event_type: str, aggregate_type: str = "", aggregate_id: str | None = None,
              payload: dict | None = None, user_id: str | None = None, correlation_id: str | None = None) -> Event:
        return Event(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload or {},
            user_id=user_id,
            correlation_id=correlation_id,
        )

    def command(self, command_type: str, payload: dict | None = None, **ctx) -> Command:
        return Command(type=command_type, payload=payload or {}, **ctx)

    async def start(self, llm: Any = None) -> None:
        self.lifecycle.transition(SystemState.STARTING)
        logger.info("core starting", extra=log_extra({"env": self.settings.app_env}))
        await self.modules.start_all()
        self.llm = llm
        from app.ai.runtime import AIRuntime

        self.ai_runtime = AIRuntime(self)
        self.lifecycle.transition(SystemState.RUNNING)
        logger.info("core running", extra=log_extra({"modules": list(self.modules.statuses().keys())}))

    async def shutdown(self) -> None:
        self.lifecycle.transition(SystemState.STOPPING)
        for task in self._event_tasks:
            task.cancel()
        await self.modules.stop_all()
        self.lifecycle.transition(SystemState.STOPPED)
        logger.info("core stopped")

    def setup_health_checks(self) -> None:
        self.health.register("core", lambda: (True, "ok"))
        self.health.register("database", self._check_database)
        for module in self.modules.list():
            self.health.register(f"module:{module.name}", module.health_check)
        self.health.register("llm", self._check_llm)

    def _check_llm(self) -> tuple[bool, str]:
        if self.llm is None:
            return False, "llm not configured"
        return self.llm.health_check()

    def _check_database(self) -> tuple[bool, str]:
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(select(1))
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, f"database unreachable: {exc}"

    def new_context(self, user_id: str | None = None, correlation_id: str | None = None,
                    task_id: str | None = None) -> Any:
        from app.core.tools import ToolContext

        return ToolContext(
            user_id=user_id if user_id else self.user_id(),
            correlation_id=correlation_id or self.new_correlation_id(),
            task_id=task_id,
            core=self,
        )

    def publish(self, event: Event | None = None, **kwargs) -> None:
        if event is None:
            if "event_type" not in kwargs:
                return
            event = self.event(
                kwargs.pop("event_type", ""),
                aggregate_type=kwargs.pop("aggregate_type", ""),
                aggregate_id=kwargs.pop("aggregate_id", None),
                payload=kwargs.pop("payload", None),
                user_id=kwargs.pop("user_id", None),
                correlation_id=kwargs.pop("correlation_id", None),
            )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.events.publish(event))
            return
        task = loop.create_task(self.events.publish(event))
        self._event_tasks.append(task)