from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.ai.providers import build_provider
from app.api.system import build_router as build_system_router
from app.config import Settings, get_settings
from app.core.core import Core
from app.core.errors import AngelError
from app.core.logging import correlation_var, install_db_logging, request_var, setup_logging
from app.infrastructure.db import create_all, init_db

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


async def bootstrap_core(settings: Settings) -> Core:
    init_db(settings.database_url)
    create_all()

    from app.markdown.module import MarkdownModule
    from app.modules.ai.module import AIModule
    from app.modules.notes.module import NotesModule
    from app.modules.notifications.module import NotificationsModule
    from app.modules.reminders.module import RemindersModule
    from app.interfaces.telegram import TelegramModule
    from app.workers.module import WorkersModuleConnector

    core = Core(settings)
    install_db_logging(core.session_factory, settings.log_level)
    core.register_module(NotesModule())
    core.register_module(RemindersModule())
    core.register_module(NotificationsModule())
    core.register_module(AIModule())
    core.register_module(MarkdownModule())
    core.register_module(TelegramModule())

    connector = WorkersModuleConnector(core)
    connector.install()
    core.workers_connector = connector

    ai = core.get_module("ai")
    for key, value in ai.config_values().items():
        if value is not None and hasattr(settings, key):
            setattr(settings, key, value)

    provider = build_provider(settings)
    await core.start(llm=provider)
    core.setup_health_checks()
    await connector.start()
    core.default_user()
    await core.modules.start("telegram")

    return core


async def teardown_core(core: Core) -> None:
    if getattr(core, "telegram", None) is not None:
        await core.telegram.stop()
    if getattr(core, "workers_connector", None) is not None:
        await core.workers_connector.stop()
    await core.shutdown()


def mount_routes(app: FastAPI, core: Core) -> None:
    app.include_router(build_system_router(core))
    for router in core.module_routers:
        app.include_router(router)
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

        @app.get("/", include_in_schema=False)
        async def index():
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        @app.get("/app.js", include_in_schema=False)
        async def index_js():
            return FileResponse(str(FRONTEND_DIR / "app.js"))

        @app.get("/style.css", include_in_schema=False)
        async def index_css():
            return FileResponse(str(FRONTEND_DIR / "style.css"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        correlation = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        correlation_var.set(correlation)
        request_var.set(request_id)
        response = await call_next(request)
        response.headers["x-correlation-id"] = correlation
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(AngelError)
    async def angel_error_handler(request: Request, exc: AngelError):
        payload = {"error": exc.code, "message": exc.message}
        if exc.details:
            payload["details"] = exc.details
        return JSONResponse(status_code=exc.http_status, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": "internal_error", "message": "internal server error"})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.log_level)
        core = await bootstrap_core(settings)
        app.state.core = core
        mount_routes(app, core)
        yield
        await teardown_core(core)

    app.router.lifespan_context = lifespan
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()