import os
import sys
import tempfile

import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings
from app.core.core import Core
from app.infrastructure.db import create_all, init_db


def make_settings(vault_dir: str | None = None) -> Settings:
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="angel-test-")
    os.close(fd)
    return Settings(
        app_env="test",
        database_url=f"sqlite:///{db_path.replace(os.sep, '/')}",
        markdown_vault_path=vault_dir or tempfile.mkdtemp(prefix="angel-vault-"),
        scheduler_interval=60.0,
        worker_concurrency=1,
        telegram_bot_token="",
    )


async def build_core(settings: Settings, with_workers: bool = True, provider=None) -> Core:
    init_db(settings.database_url)
    create_all()
    from app.modules.ai.module import AIModule
    from app.markdown.module import MarkdownModule
    from app.modules.notes.module import NotesModule
    from app.modules.notifications.module import NotificationsModule
    from app.modules.reminders.module import RemindersModule

    core = Core(settings)
    core.register_module(NotesModule())
    core.register_module(RemindersModule())
    core.register_module(NotificationsModule())
    core.register_module(AIModule())
    core.register_module(MarkdownModule())
    if with_workers:
        from app.workers.module import WorkersModuleConnector

        connector = WorkersModuleConnector(core)
        connector.install()
        core.workers_connector = connector
    import asyncio

    await core.start(llm=provider)
    core.setup_health_checks()
    if with_workers:
        await core.workers_connector.start()
    core.default_user()
    return core


class FakeProvider:
    name = "fake"
    supports_tool_calling = True

    def __init__(self, script: list | None = None) -> None:
        self.script = list(script or [])
        self.calls = []

    def available(self) -> bool:
        return True

    def health_check(self) -> tuple[bool, str]:
        return True, "ok"

    async def complete(self, messages, tools=None, temperature=0.3, max_tokens=1024, timeout=60.0):
        from app.ai.providers.base import Completion, Message, ToolCall

        self.calls.append([m.role for m in messages])
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, str):
                return Completion(text=item)
            if isinstance(item, dict) and "text" in item:
                return Completion(text=item["text"], usage=item.get("usage", {}))
            if isinstance(item, dict) and "tool" in item:
                return Completion(text="")
        return Completion(text='{"text": "done"}')


@pytest_asyncio.fixture
async def core():
    settings = make_settings()
    core = await build_core(settings)
    yield core
    from app.core.lifecycle import SystemState

    if core.lifecycle.state != SystemState.STOPPED:
        import asyncio

        if getattr(core, "workers_connector", None) is not None:
            await core.workers_connector.stop()
        await core.shutdown()


@pytest_asyncio.fixture
async def no_llm_core():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    yield core
    import asyncio

    await core.shutdown()