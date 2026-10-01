from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.core.errors import AngelError, LLMError
from app.core.lifecycle import ModuleStatus


def build_router(core) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["system"])

    @router.get("/system/status")
    def system_status():
        return {
            "state": core.lifecycle.state.value,
            "app": core.settings.app_name,
            "env": core.settings.app_env,
            "modules": core.modules.statuses(),
            "capabilities": core.modules.capabilities(),
            "users": 1,
        }

    @router.get("/system/modules")
    def modules():
        return core.modules.info()

    @router.post("/system/modules/{name}/start")
    async def module_start(name: str):
        if core.modules.get(name) is None:
            raise HTTPException(404, f"module {name} not found")
        await core.modules.start(name)
        return {"name": name, "status": core.modules.status(name)}

    @router.post("/system/modules/{name}/stop")
    async def module_stop(name: str):
        if core.modules.get(name) is None:
            raise HTTPException(404, f"module {name} not found")
        await core.modules.stop(name)
        return {"name": name, "status": core.modules.status(name)}

    @router.post("/system/modules/{name}/restart")
    async def module_restart(name: str):
        if core.modules.get(name) is None:
            raise HTTPException(404, f"module {name} not found")
        await core.modules.restart(name)
        return {"name": name, "status": core.modules.status(name)}

    @router.put("/system/modules/{name}/config")
    async def module_config_update(name: str, payload: dict):
        module = core.modules.get(name)
        if module is None:
            raise HTTPException(404, f"module {name} not found")
        saved = module.save_config(payload)
        return {
            "name": name,
            "saved": saved,
            "values": module.config_values(),
        }

    @router.get("/system/modules/{name}/config")
    def module_config_get(name: str):
        module = core.modules.get(name)
        if module is None:
            raise HTTPException(404, f"module {name} not found")
        return {
            "name": name,
            "fields": [f.to_dict() for f in module.config_fields],
            "values": module.config_values(),
        }

    @router.get("/system/health")
    def health():
        snap = core.health.snapshot()
        return {"healthy": all(v["ok"] for k, v in snap.items() if not k.startswith("_")), **snap}

    @router.get("/system/users")
    def users():
        from app.core.models import User
        from sqlalchemy import select

        session = core.session_factory()
        try:
            rows = session.execute(select(User).order_by(User.created_at)).scalars().all()
            return [
                {
                    "id": str(u.id),
                    "username": u.username,
                    "full_name": u.full_name,
                    "role": u.role,
                    "telegram_user_id": u.telegram_user_id,
                    "telegram_username": u.telegram_username,
                    "telegram_chat_id": u.telegram_chat_id,
                    "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
                    "authorized": u.role in ("owner", "admin"),
                }
                for u in rows
            ]
        finally:
            session.close()

    @router.post("/system/users/{user_id}/role")
    def user_role(user_id: str, payload: dict):
        role = payload.get("role")
        if role not in ("owner", "admin", "member"):
            raise HTTPException(422, "role must be owner|admin|member")
        from app.core.models import User
        import uuid

        session = core.session_factory()
        try:
            user = session.get(User, uuid.UUID(user_id))
            if user is None:
                raise HTTPException(404, "user not found")
            if user.username == core.settings.default_user_username and role != "owner":
                raise HTTPException(403, "нельзя понизить владельца системы")
            if role == "owner" and user.username != core.settings.default_user_username:
                raise HTTPException(403, "роль владельца закреплена за основным пользователем")
            user.role = role
            session.commit()
            return {"id": str(user.id), "role": user.role}
        except ValueError:
            raise HTTPException(404, "user not found")
        finally:
            session.close()

    @router.get("/workers/status")
    def worker_status():
        return core.worker_pool.status()

    @router.get("/scheduler/status")
    def scheduler_status():
        workers_module = core.modules.get("workers")
        scheduler = getattr(core, "workers_connector", None)
        if scheduler is None or scheduler.scheduler is None:
            return {"status": "stopped"}
        sched = scheduler.scheduler
        return {
            "status": sched.status,
            "interval": sched.interval,
            "last_tick": sched.last_tick,
            "last_scan_at": sched.last_scan_at.isoformat() if sched.last_scan_at else None,
            "scanned": sched.scanned,
            "triggered": sched.triggered,
            "last_error": sched.last_error,
        }

    @router.get("/system/confirmations")
    def pending_confirmations():
        return [
            {
                "id": str(c.id),
                "permission": c.permission,
                "tool": c.tool_name,
                "params": c.params_json,
                "message": c.message,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            }
            for c in core.permissions.pending(None)
        ]

    @router.post("/system/confirmations/{confirmation_id}/approve")
    def approve_confirmation(confirmation_id: str):
        try:
            record = core.permissions.resolve(confirmation_id, approve=True)
            return {"status": "approved", "tool": record.tool_name}
        except (KeyError, ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc))

    @router.post("/system/confirmations/{confirmation_id}/deny")
    def deny_confirmation(confirmation_id: str):
        try:
            record = core.permissions.resolve(confirmation_id, approve=False)
            return {"status": "denied", "tool": record.tool_name}
        except (KeyError, ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc))

    @router.get("/system/permissions")
    def permissions():
        tools = [
            {
                "name": t.name,
                "permission": t.permission,
                "description": t.description,
                "default": t.default_mode.value,
                "current": core.permissions.mode_for(t.permission, t.default_mode, None).value,
            }
            for t in core.tools.list()
        ]
        return {"tools": tools}

    @router.post("/system/permissions/{permission}")
    def set_permission(permission: str, payload: dict):
        mode = payload.get("mode")
        if mode not in ("allow", "confirm", "forbid"):
            raise HTTPException(422, "mode must be allow|confirm|forbid")
        tokens = {p: t.default_mode.value for p in (p.permission for t in core.tools.list())}
        if permission not in tokens:
            raise HTTPException(404, f"permission {permission} not found")
        core.permissions.set_rule(permission, mode)
        return {"permission": permission, "mode": mode}

    @router.delete("/system/permissions/{permission}")
    def reset_permission(permission: str):
        core.permissions.reset_rule(permission)
        return {"permission": permission, "reset": True}

    @router.get("/activity")
    def activity(limit: int = 100):
        return [
            {
                "id": str(a.id),
                "user_id": str(a.user_id) if a.user_id else None,
                "actor": a.actor,
                "action": a.action,
                "module": a.module,
                "tool": a.tool,
                "status": a.status,
                "task_id": a.task_id,
                "correlation_id": a.correlation_id,
                "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in core.activity.list_recent(limit=limit)
        ]

    @router.get("/dashboard")
    def dashboard():
        from sqlalchemy import func, select

        session = core.session_factory()
        try:
            from app.modules.notes.index_models import IndexNote
            from app.modules.reminders.models import Reminder
            from app.modules.notifications.models import Notification
            from app.core.models import ActivityRecord

            notes_count = session.execute(select(func.count(IndexNote.id)).where(IndexNote.status != "archived")).scalar_one()
            reminders = session.execute(select(Reminder).where(Reminder.status == "scheduled")).scalars().all()
            unread = session.execute(select(func.count(Notification.id)).where(Notification.read.is_(False))).scalar_one()
            today_activities = session.execute(
                select(func.count(ActivityRecord.id))
            ).scalar_one()
            session.close()
        finally:
            session.close()
        return {
            "notes": int(notes_count),
            "upcoming_reminders": [_reminder_summary(r) for r in sorted(reminders, key=lambda r: r.trigger_at)[:5]],
            "unread_notifications": int(unread),
            "activity_count": int(today_activities),
            "system_state": core.lifecycle.state.value,
            "llm_provider": getattr(core.llm, "name", "none") if core.llm else "none",
            "telegram": core.telegram.configured if core.telegram else False,
        }

    @router.post("/markdown/sync")
    def markdown_sync():
        module = core.modules.get("markdown")
        if module is None or module.sync is None:
            raise HTTPException(404, "markdown module disabled")
        report = module.sync.full_sync()
        return {"status": "scheduled", **report}

    @router.post("/ai/chat")
    async def ai_chat(payload: dict):
        text = (payload.get("text") or "").strip()
        if not text:
            raise HTTPException(422, "text is required")
        try:
            outcome = await core.ai_runtime.chat(text, user_id=core.user_id(), kind="chat")
            return {
                "status": outcome.status,
                "text": outcome.text,
                "tool_calls": outcome.tool_calls,
                "confirmation_id": outcome.confirmation_id,
                "error": outcome.error,
                "steps": outcome.steps,
            }
        except LLMError as exc:
            raise HTTPException(502, str(exc))
        except AngelError as exc:
            raise HTTPException(exc.http_status, exc.message)

    @router.get("/ai/providers")
    def ai_providers():
        settings = core.settings
        return {
            "primary": settings.llm_provider,
            "model": settings.llm_model,
            "api_url": settings.llm_api_url,
            "fallback": settings.llm_fallback_provider or None,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
        }

    @router.get("/ai/ollama/models")
    async def ollama_models(base_url: str | None = None):
        import httpx

        settings = core.settings
        base = (base_url or settings.llm_api_url).strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "http://" + base
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base}/api/tags")
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, f"Не удалось получить модели Ollama по «{base}»: {exc}")
        models = sorted({m.get("name", "") for m in data.get("models", []) if m.get("name")})
        return {"models": models, "base_url": base}

    @router.post("/ai/test")
    async def ai_test(payload: dict):
        import asyncio

        from app.ai.providers import build_provider

        settings = core.settings
        overrides = {k: payload[k] for k in (
            "llm_provider", "llm_model", "llm_api_url", "llm_api_key", "llm_timeout",
        ) if payload.get(k) is not None}
        edited = settings.model_copy(update=overrides)
        provider = build_provider(edited)
        try:
            ok = await asyncio.to_thread(provider.available)
        except Exception as exc:  # noqa: BLE001
            ok = False
            message = str(exc)
        else:
            message = "доступен" if ok else "недоступен (нет ответа от API)"
        return {
            "ok": ok,
            "provider": provider.name,
            "model": edited.llm_model,
            "api_url": edited.llm_api_url,
            "message": message,
        }

    def _parse_dt(value: str | None, end_of_day: bool = False):
        if not value:
            return None
        from datetime import datetime

        text = value.strip()
        for fmt, eod in (("%Y-%m-%dT%H:%M:%S", end_of_day), ("%Y-%m-%d %H:%M:%S", end_of_day),
                         ("%Y-%m-%d", end_of_day), ("%Y-%m-%d %H:%M", end_of_day)):
            try:
                dt = datetime.strptime(text, fmt)
            except ValueError:
                continue
            if not eod:
                return dt
            return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        raise HTTPException(422, f"неверный формат даты: {value}, ожидается YYYY-MM-DD[THH:MM[:SS]]")

    def _log_conditions(level: str | None, query: str | None, module: str | None,
                    errors_only: bool, from_date: str | None, to_date: str | None):
        from sqlalchemy import or_

        from app.core.models import LogRecord

        conds = []
        if errors_only:
            conds.append(LogRecord.level.in_(["ERROR", "CRITICAL"]))
        if level:
            names = [l.strip().upper() for l in level.split(",") if l.strip()]
            if names:
                conds.append(LogRecord.level.in_(names))
        if module:
            conds.append(LogRecord.logger.ilike(f"%{module}%"))
        if query:
            q = query.strip()
            if q:
                conds.append(or_(LogRecord.message.ilike(f"%{q}%"), LogRecord.exc_text.ilike(f"%{q}%")))
        start = _parse_dt(from_date, end_of_day=False)
        end = _parse_dt(to_date, end_of_day=True)
        if start is not None:
            conds.append(LogRecord.ts >= start)
        if end is not None:
            conds.append(LogRecord.ts <= end)
        return conds, LogRecord

    def _log_row(r) -> dict:
        return {
            "id": str(r.id),
            "ts": r.ts.isoformat() if r.ts else None,
            "level": r.level,
            "logger": r.logger,
            "message": r.message,
            "extra": r.extra or {},
            "exc_text": r.exc_text,
            "correlation_id": r.correlation_id,
            "request_id": r.request_id,
            "task_id": r.task_id,
            "user_id": r.user_id,
        }

    @router.get("/logs")
    def logs(level: str | None = None, query: str | None = None, module: str | None = None,
             errors_only: bool = False, from_date: str | None = None, to_date: str | None = None,
             limit: int = 200, offset: int = 0, order: str = "desc"):
        from sqlalchemy import func, select

        limit = min(max(limit, 1), 1000)
        offset = max(offset, 0)
        conds, LogRecord = _log_conditions(level, query, module, errors_only, from_date, to_date)
        session = core.session_factory()
        try:
            total = session.execute(select(func.count("*")).select_from(select(LogRecord).where(*conds).subquery())).scalar_one()
            direction = LogRecord.ts.desc() if order == "desc" else LogRecord.ts.asc()
            rows = session.execute(select(LogRecord).where(*conds).order_by(direction).limit(limit).offset(offset)).scalars().all()
            items = [_log_row(r) for r in rows]
        finally:
            session.close()
        return {"items": items, "total": int(total), "limit": limit, "offset": offset}

    @router.get("/logs/summary")
    def logs_summary():
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import func, select

        from app.core.models import LogRecord

        session = core.session_factory()
        try:
            total = session.execute(select(func.count(LogRecord.id))).scalar_one()
            by_level = dict(
                session.execute(select(LogRecord.level, func.count(LogRecord.id)).group_by(LogRecord.level)).all()
            )
            day_start = datetime.now(timezone.utc) - timedelta(days=1)
            today_total = session.execute(
                select(func.count(LogRecord.id)).where(LogRecord.ts >= day_start)
            ).scalar_one()
            today_errors = session.execute(
                select(func.count(LogRecord.id)).where(
                    LogRecord.ts >= day_start, LogRecord.level.in_(["ERROR", "CRITICAL"])
                )
            ).scalar_one()
            last_error = session.execute(
                select(LogRecord).where(LogRecord.level.in_(["ERROR", "CRITICAL"])).order_by(LogRecord.ts.desc()).limit(1)
            ).scalar_one_or_none()
            top_loggers = [
                {"logger": name, "count": int(count)}
                for name, count in session.execute(
                    select(LogRecord.logger, func.count(LogRecord.id))
                    .group_by(LogRecord.logger).order_by(func.count(LogRecord.id).desc()).limit(10)
                ).all()
            ]
        finally:
            session.close()
        return {
            "total": int(total),
            "levels": {k: int(v) for k, v in by_level.items()},
            "today_total": int(today_total),
            "today_errors": int(today_errors),
            "last_error": _log_row(last_error) if last_error else None,
            "top_loggers": top_loggers,
        }

    @router.delete("/logs")
    def logs_delete(level: str | None = None, query: str | None = None, module: str | None = None,
                    errors_only: bool = False, from_date: str | None = None, to_date: str | None = None):
        from sqlalchemy import delete, func, select

        conds, LogRecord = _log_conditions(level, query, module, errors_only, from_date, to_date)
        session = core.session_factory()
        try:
            count = session.execute(select(func.count("*")).select_from(select(LogRecord).where(*conds).subquery())).scalar_one()
            session.execute(delete(LogRecord).where(*conds))
            session.commit()
        finally:
            session.close()
        return {"deleted": int(count)}

    @router.get("/settings")
    def settings_view():
        settings = core.settings
        return {
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "llm_api_url": settings.llm_api_url,
            "llm_fallback_provider": settings.llm_fallback_provider,
            "markdown_vault_path": settings.vault_path,
            "markdown_enabled": settings.markdown_enabled,
            "scheduler_interval": settings.scheduler_interval,
            "worker_concurrency": settings.worker_concurrency,
            "telegram_configured": bool(core.telegram and core.telegram.configured),
        }

    @router.get("/ai/llm-logs")
    def ai_llm_logs(
        model: str | None = None,
        provider: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        from sqlalchemy import select, desc
        from app.core.models import LLMCall

        stmt = select(LLMCall).order_by(desc(LLMCall.ts)).offset(offset).limit(limit)
        if model:
            stmt = stmt.where(LLMCall.model == model)
        if provider:
            stmt = stmt.where(LLMCall.provider == provider)
        if kind:
            stmt = stmt.where(LLMCall.kind == kind)
        session = core.session_factory()
        try:
            rows = session.execute(stmt).scalars().all()
            return {
                "items": [
                    {
                        "id": r.id, "ts": r.ts.isoformat() if r.ts else None,
                        "model": r.model, "provider": r.provider,
                        "temperature": r.temperature, "max_tokens": r.max_tokens,
                        "request_messages": r.request_messages,
                        "response_text": r.response_text,
                        "response_tool_calls": r.response_tool_calls,
                        "response_usage": r.response_usage,
                        "steps": r.steps, "error": r.error,
                        "user_id": r.user_id, "kind": r.kind,
                    }
                    for r in rows
                ],
                "count": len(rows),
                "limit": limit, "offset": offset,
            }
        finally:
            session.close()

    return router


def _reminder_summary(r) -> dict:
    return {"id": str(r.id), "text": r.text, "trigger_at": r.trigger_at.isoformat(), "timezone": r.timezone}