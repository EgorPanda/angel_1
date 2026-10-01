import asyncio
import logging
import os

import httpx

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.infrastructure.db import create_all, init_db
from tests.conftest import build_core, FakeProvider, make_settings
from tests.test_markdown import find_file_in_vault


class _TestApp:
    def __init__(self, core):
        self.core = core

    def create(self):
        from app.main import mount_routes

        app = FastAPI(title="Angel AI (test)")
        mount_routes(app, self.core)
        return app


async def test_api_dashboard_and_notes():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        core.get_module("notes").service.create({"title": "Через API"})

        app = _TestApp(core).create()
        with TestClient(app) as client:
            res = client.get("/api/v1/dashboard")
            assert res.status_code == 200
            body = res.json()
            assert body["notes"] >= 1

            res = client.post("/api/v1/notes", json={"title": "Новая через HTTP"})
            assert res.status_code == 201
            note = res.json()
            assert note["title"] == "Новая через HTTP"

            res = client.get(f"/api/v1/notes/{note['id']}")
            assert res.status_code == 200

            res = client.get("/api/v1/system/health")
            assert res.status_code == 200
            checks = res.json()
            assert checks["database"]["ok"] is True
            assert checks["healthy"] is True
            # note with relationships + children ids must not raise AttributeError
            src = client.post("/api/v1/notes", json={"title": "Source"}).json()
            tgt = client.post("/api/v1/notes", json={"title": "Target"}).json()
            client.post(f"/api/v1/notes/{src['id']}/relations", json={"target_id": tgt["id"], "relation_type": "depends_on"})
            res = client.get(f"/api/v1/notes/{src['id']}")
            assert res.status_code == 200
            detail = res.json()
            assert any(r["relation_type"] == "depends_on" for r in detail["relationships"])
            rel = client.get(f"/api/v1/notes/{src['id']}/relations").json()
            assert rel[0]["target_id"] == tgt["id"]
        finally:
        await core.shutdown()


async def test_api_confirmation_flow():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        service = core.get_module("notes").service
        note = service.create({"title": "Удаляемая"})

        from app.core.permissions import PermissionMode

        core.permissions.set_rule("notes.delete", PermissionMode.CONFIRM, core.user_id())
        # create a pending confirmation for a future delete

        app = _TestApp(core).create()
        with TestClient(app) as client:
            res = client.get("/api/v1/system/confirmations")
            assert res.status_code == 200

            res = client.get("/api/v1/system/permissions")
            assert res.status_code == 200
            rules = res.json()
            assert any(t["permission"] == "notes.delete" and t["current"] == "confirm" for t in rules["tools"])
    finally:
        await core.shutdown()


async def test_api_ai_chat_with_fake_provider():
    settings = make_settings()
    provider = FakeProvider([
        '{"tool":"create_note","arguments":{"title":"AI через HTTP"}}',
        {"text": "Создал"},
    ])
    core = await build_core(settings, with_workers=False, provider=provider)
    try:
        app = _TestApp(core).create()
        with TestClient(app) as client:
            res = client.post("/api/v1/ai/chat", json={
                "text": "Создай заметку",
                "user_id": core.user_id(),
            })
            assert res.status_code == 200
            outcome = res.json()
            assert outcome["status"] == "completed"
            assert "Создал" in outcome["text"]
    finally:
        await core.shutdown()


async def test_api_logs_endpoint():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        from app.core.logging import install_db_logging

        install_db_logging(core.session_factory, "DEBUG")
        logger = logging.getLogger("testmod")
        logger.setLevel(logging.DEBUG)
        logger.info("запуск теста")
        logger.warning("внимание: что-то подозрительно")
        try:
            1 / 0
        except ZeroDivisionError:
            logger.error("упало деление", exc_info=True)

        app = _TestApp(core).create()
        with TestClient(app) as client:
            res = client.get("/api/v1/logs")
            assert res.status_code == 200
            body = res.json()
            assert body["total"] >= 3

            res = client.get("/api/v1/logs", params={"errors_only": "true"})
            errors = res.json()
            assert errors["total"] >= 1
            assert all(i["level"] in ("ERROR", "CRITICAL") for i in errors["items"])
            assert any("упало деление" in i["message"] for i in errors["items"])
            assert errors["items"][0]["exc_text"]

            res = client.get("/api/v1/logs", params={"module": "testmod"})
            assert res.json()["total"] >= 3

            res = client.get("/api/v1/logs", params={"level": "WARNING"})
            assert res.json()["total"] >= 1

            res = client.get("/api/v1/logs/summary")
            summary = res.json()
            assert summary["total"] >= 1
            assert summary["levels"].get("ERROR", 0) >= 1
            assert summary["last_error"] is not None

            res = client.delete("/api/v1/logs", params={"level": "INFO"})
            deleted = res.json()
            assert deleted["deleted"] >= 1
    finally:
        await core.shutdown()


class FakeAsyncClient:
    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        class Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"models": [{"name": "qwen2.5:7b"}, {"name": "llama3.2:3b"}]}

        return Response()


async def test_api_ollama_models(monkeypatch):
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
        app = _TestApp(core).create()
        with TestClient(app) as client:
            res = client.get("/api/v1/ai/ollama/models", params={"base_url": "http://localhost:11434"})
            assert res.status_code == 200
            assert res.json()["models"] == ["llama3.2:3b", "qwen2.5:7b"]
    finally:
        await core.shutdown()


async def test_api_ai_test(monkeypatch):
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        import app.ai.providers as providers_mod

        def fake_build(settings=None):
            return FakeProvider(["ok"])

        monkeypatch.setattr(providers_mod, "build_provider", fake_build)
        app = _TestApp(core).create()
        with TestClient(app) as client:
            res = client.post("/api/v1/ai/test", json={"llm_model": "qwen2.5:7b"})
            assert res.status_code == 200
            body = res.json()
            assert body["ok"] is True
            assert body["provider"] == "fake"
    finally:
        await core.shutdown()


async def test_api_markdown_sync_endpoint():
    settings = make_settings()
    core = await build_core(settings, with_workers=False, provider=None)
    try:
        core.get_module("notes").service.create({"title": "Синхронизация"})
        app = _TestApp(core).create()
        with TestClient(app) as client:
            res = client.post("/api/v1/markdown/sync")
            assert res.status_code == 200
            report = res.json()
            assert report["status"] == "scheduled"
            assert report["indexed"] >= 1
            inbox = os.path.join(settings.markdown_vault_path, "0_Входящие")
            assert os.path.isdir(inbox) and any(name.endswith(".md") and not name.endswith("_MOC.md") for name in os.listdir(inbox))
    finally:
        await core.shutdown()