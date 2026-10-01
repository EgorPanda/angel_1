from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.ai.context import ContextBuilder
from app.ai.prompts import PromptBuilder
from app.ai.providers.base import Message
from app.ai.schemas import AgentOutcome, AgentRequest
from app.core.errors import LLMError, PermissionDenied, ToolExecutionError, ValidationError as AngelValidationError
from app.core.logging import get_logger, log_extra
from app.infrastructure.db import get_session_factory
from app.modules.ai.models import AITask

logger = get_logger("ai.agent")


class Agent:
    def __init__(self, core, provider=None) -> None:
        self.core = core
        self.provider = provider or core.llm
        self.prompts = PromptBuilder(core.tools.list())
        self.context = ContextBuilder(core)

    async def run(self, request: AgentRequest) -> AgentOutcome:
        if self.provider is None:
            return AgentOutcome(status="error", error="no LLM provider configured")
        correlation_id = request.correlation_id or str(uuid.uuid4())
        ai_task_id = self._create_task(request, correlation_id)
        ctx = self.core.new_context(user_id=request.user_id, correlation_id=correlation_id, task_id=ai_task_id)
        logger.info("agent run started", extra=log_extra({"correlation_id": correlation_id, "user_id": request.user_id, "kind": request.kind}))
        strict_format = self._is_strict_format(request.text)
        if strict_format:
            messages = self._strict_messages(request)
            logger.info("strict format mode", extra=log_extra({"correlation_id": correlation_id}))
        else:
            messages = self._initial_messages(request, correlation_id)
        steps = 0
        self._seen: dict[str, int] = {}
        executed: list[str] = []
        last_raw_text = ""
        try:
            settings = self.core.settings
            model = settings.llm_model
            provider_name = self.provider.name
            if strict_format:
                call_id = await self._log_llm_call(request, messages, model, provider_name,
                    settings.llm_temperature, settings.llm_max_tokens)
                completion = await self.provider.complete(
                    messages,
                    tools=None,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    timeout=settings.llm_timeout,
                )
                await self._update_llm_call(call_id, text=completion.text,
                    tool_calls=[tc.__dict__ for tc in completion.tool_calls],
                    usage=completion.usage, steps=1)
                return AgentOutcome(status="completed", text=completion.text or "", steps=1, usage=completion.usage)
            while steps < (request.max_steps or settings.llm_max_steps):
                steps += 1
                call_id = await self._log_llm_call(request, messages, model, provider_name,
                    settings.llm_temperature, settings.llm_max_tokens)
                completion = await self.provider.complete(
                    messages,
                    tools=self.prompts.tool_catalog(request.tool_names) if (request.native_tools and not strict_format) else None,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    timeout=settings.llm_timeout,
                )
                await self._update_llm_call(call_id, text=completion.text,
                    tool_calls=[{"name": tc.name, "arguments": tc.arguments, "call_id": tc.call_id} for tc in completion.tool_calls],
                    usage=completion.usage, steps=steps)
                last_raw_text = (completion.text or "").strip()
                calls = list(completion.tool_calls)
                if not calls:
                    parsed = self._parse_envelope(completion.text)
                    if parsed is None:
                        return AgentOutcome(
                            status="completed", text=completion.text or "", steps=steps, usage=completion.usage
                        )
                    if "text" in parsed:
                        return AgentOutcome(
                            status="completed", text=parsed["text"], steps=steps, usage=completion.usage
                        )
                    calls = [self._call_from_parsed(parsed, completion.text)]
                assistant_block = self._assistant_block(calls, completion.text)
                messages.extend(assistant_block)
                all_repeated = bool(calls)
                for call in calls:
                    if request.tool_names and call.name not in request.tool_names:
                        messages.append(self._tool_result_message(call, {"error": f"tool not allowed: {call.name}"}))
                        all_repeated = False
                        continue
                    signature = _call_signature(call)
                    self._seen[signature] = self._seen.get(signature, 0) + 1
                    if self._seen[signature] >= 2:
                        messages.append(self._loop_guard_message(call))
                        continue
                    all_repeated = False
                    outcome = await self._execute_tool(call, ctx, messages, steps)
                    if outcome is not None:
                        return outcome
                    executed.append(call.name)
                if all_repeated:
                    summary = self._finalize_text(executed, last_raw_text)
                    return AgentOutcome(status="completed", text=summary, steps=steps)
            summary = self._finalize_text(executed, last_raw_text)
            return AgentOutcome(status="completed", text=summary, steps=steps)
        except LLMError as exc:
            self._fail_task(ai_task_id, exc)
            self.core.activity.log(
                user_id=request.user_id, actor="ai", action="chat", module="ai", tool=None,
                status="error", task_id=ai_task_id, correlation_id=correlation_id, metadata={"error": str(exc)},
            )
            raise
        except Exception as exc:  # noqa: BLE001
            self._fail_task(ai_task_id, exc)
            logger.error("agent run failed", exc_info=True)
            return AgentOutcome(status="error", error=str(exc), steps=steps)

    async def _log_llm_call(self, request: AgentRequest, messages: list[Message],
                             model: str, provider: str, temperature: float,
                             max_tokens: int, **kwargs) -> str:
        sf = get_session_factory()
        session = sf()
        try:
            from sqlalchemy import text
            call_id = uuid.uuid4().hex[:16]
            session.execute(text("""
                INSERT INTO llm_calls (id, ts, model, provider, temperature, max_tokens,
                    request_messages, response_text, response_tool_calls, response_usage,
                    steps, error, user_id, kind)
                VALUES (:id, :ts, :model, :provider, :temperature, :max_tokens,
                    :req, NULL, NULL, NULL, NULL, NULL, :uid, :kind)
            """), {
                "id": call_id, "ts": datetime.now(timezone.utc),
                "model": model, "provider": provider, "temperature": temperature,
                "max_tokens": max_tokens,
                "req": json.dumps([m.to_dict() for m in messages], ensure_ascii=False),
                "uid": request.user_id, "kind": request.kind,
            })
            session.commit()
            return call_id
        except Exception:  # noqa: BLE001
            session.rollback()
            return ""
        finally:
            session.close()

    async def _update_llm_call(self, call_id: str, text: str | None = None,
                                tool_calls: list[dict] | None = None,
                                usage: dict | None = None, steps: int | None = None,
                                error: str | None = None) -> None:
        if not call_id:
            return
        sf = get_session_factory()
        session = sf()
        try:
            from sqlalchemy import text
            set_parts = []
            params: dict = {}
            if text is not None:
                set_parts.append("response_text = :text"); params["text"] = text
            if tool_calls is not None:
                set_parts.append("response_tool_calls = :tc"); params["tc"] = json.dumps(tool_calls, ensure_ascii=False)
            if usage is not None:
                set_parts.append("response_usage = :u"); params["u"] = json.dumps(usage, ensure_ascii=False)
            if steps is not None:
                set_parts.append("steps = :s"); params["s"] = steps
            if error is not None:
                set_parts.append("error = :e"); params["e"] = error
            if not set_parts:
                return
            params["id"] = call_id
            session.execute(text(f"UPDATE llm_calls SET {', '.join(set_parts)} WHERE id = :id"), params)
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        finally:
            session.close()

    def _initial_messages(self, request: AgentRequest, correlation_id: str) -> list[Message]:
        system = self.prompts.system_prompt(request.tool_names)
        user_content = request.text
        data_context = self.context.build(request.user_id)
        rendered = self.context.render(data_context)
        user_block = f"{rendered}\n\nUSER REQUEST:\n{user_content}"
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user_block),
        ]
        return messages

    @staticmethod
    def _strict_messages(request: AgentRequest) -> list[Message]:
        system = (
            "You are a precise assistant.\n"
            "Rules:\n"
            "1. Follow the user's request literally and completely.\n"
            "2. If the user demands a specific output format (for example raw JSON), output exactly that and "
            "NOTHING else: no comments, no markdown fences, no surrounding text.\n"
            "3. Do not invent content. Do not describe what you would do.\n"
            "4. Respond in the same language the user wrote in."
        )
        return [
            Message(role="system", content=system),
            Message(role="user", content=request.text),
        ]

    @staticmethod
    def _is_strict_format(text: str) -> bool:
        lowered = text.lower()
        markers = (
            "строго в формате",
            "в формате json",
            "формате json",
            "чистый json",
            "только json",
            "pure json",
            "raw json",
            "exactly as json",
            "strictly as json",
            "без пояснений",
            "just output",
        )
        matched = any(m in lowered for m in markers)
        if not matched:
            return False
        action_hints = ("создай", "создать", "удали", "удалить", "обнови", "измени", "отправь", "напомни", "найди")
        return not any(h in lowered for h in action_hints)

    def _loop_guard_message(self, call) -> Message:
        content = (
            f"[SYSTEM] Инструмент \"{call.name}\" уже вызывался с теми же аргументами в этом диалоге. "
            "Повторный вызов недопустим. Если задача выполнена — немедленно ответь финальным "
            "{\"text\": \"...\"}. Не вызывай инструменты повторно."
        )
        return Message(role="user", content=content)

    @staticmethod
    def _finalize_text(executed: list[str], last_raw: str) -> str:
        if last_raw and not last_raw.startswith("TOOL CALL") and not last_raw.startswith("Based on"):
            return last_raw
        unique = list(dict.fromkeys(executed))
        if unique:
            return "Выполнено действие: " + ", ".join(unique) + "."
        return "Не удалось сформировать ответ. Попробуйте переформулировать запрос."

    async def _execute_tool(self, call, ctx, messages, step: int) -> AgentOutcome | None:
        tool = self.core.tools.get(call.name)
        if tool is None:
            messages.append(self._tool_result_message(call, {"error": f"unknown tool: {call.name}"}))
            return None
        try:
            result = await tool.execute(call.arguments, ctx)
        except PermissionDenied as exc:
            messages.append(self._tool_result_message(call, {"error": f"permission denied: {exc.message}"}))
            return None
        except AngelValidationError as exc:
            messages.append(self._tool_result_message(call, {"error": exc.message}))
            return None
        except ToolExecutionError as exc:
            messages.append(self._tool_result_message(call, {"error": exc.message}))
            return None
        if result.needs_confirmation:
            return AgentOutcome(
                status="awaiting_confirmation",
                confirmation_id=result.confirmation_id,
                text="Требуется подтверждение действия.",
                tool_calls=[{"name": call.name, "arguments": call.arguments}],
                steps=step,
            )
        # Если инструмент отправки уведомления выполнен успешно — завершаем агента
        if call.name == "send_reminder_notification" or call.name == "send_notification":
            result_data = result.data if result.data else {}
            notification_id = result_data.get("notification_id", "")
            channel = result_data.get("channel", "web")
            status = result_data.get("status", "unknown")
            text = f"Уведомление {'отправлено' if status == 'sent' else 'ошибка'} через {channel}"
            if notification_id:
                text += f" (ID: {notification_id})"
            return AgentOutcome(
                status="completed",
                text=text,
                steps=steps,
                usage=completion.usage if 'completion' in dir() else None,
            )
        messages.append(self._tool_result_message(call, result.data))
        return None

    def _assistant_block(self, calls, raw_text: str) -> list[Message]:
        content = self._format_assistant(calls) or raw_text or " "
        return [Message(role="assistant", content=content)]

    def _format_assistant(self, calls) -> str:
        parts = []
        for call in calls:
            parts.append(f"TOOL CALL: {call.name} with arguments {json.dumps(call.arguments, ensure_ascii=False)}")
        if not parts:
            return ""
        return "\n".join(parts)

    def _tool_result_message(self, call, data) -> Message:
        content = f"[TOOL RESULT for {call.name}]\n{json.dumps(data, ensure_ascii=False, default=str)}"
        return Message(role="user", content=content)

    def _parse_envelope(self, text: str) -> dict | None:
        candidate = text.strip()
        candidate = _strip_fences(candidate)
        data = _try_json(candidate)
        if data is None:
            data = _extract_json_object(candidate)
        if data is None or not isinstance(data, dict):
            return None
        if "tool" in data or "tool_name" in data or "text" in data or "response" in data or "answer" in data:
            return data
        return None

    def _call_from_parsed(self, parsed: dict, raw_text: str):
        name = parsed.get("tool") or parsed.get("tool_name") or ""
        arguments = parsed.get("arguments") or {}
        if not name:
            text = parsed.get("text") or parsed.get("response") or parsed.get("answer") or ""
            raise LLMError(f"model returned unparseable envelope: {text[:200]}")
        return ToolCallProxy(name=name, arguments=arguments if isinstance(arguments, dict) else {})

    def _create_task(self, request: AgentRequest, correlation_id: str) -> str | None:
        try:
            session = self.core.session_factory()
            task = AITask(
                user_id=request.user_id,
                kind=request.kind,
                payload={"text": request.text[:2000], "tool_names": request.tool_names or []},
                status="running",
                task_id=correlation_id,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            session.close()
            return str(task.id)
        except Exception:  # noqa: BLE001
            return None

    def _fail_task(self, task_id: str | None, exc: Exception) -> None:
        if task_id is None:
            return
        try:
            session = self.core.session_factory()
            task = session.get(AITask, task_id)
            if task is not None:
                task.status = "failed"
                task.error = str(exc)
                task.updated_at = datetime.now(timezone.utc)
                session.commit()
            session.close()
        except Exception:  # noqa: BLE001
            pass


class ToolCallProxy:
    def __init__(self, name: str, arguments: dict) -> None:
        self.name = name
        self.arguments = arguments
        self.call_id = ""


def _call_signature(call) -> str:
    return json.dumps([call.name, call.arguments], sort_keys=True, ensure_ascii=False, default=str)


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        return "\n".join(lines).strip()
    return stripped


def _try_json(text: str):
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None


def _extract_json_object(text: str):
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return _try_json(text[start:i + 1])
    return None