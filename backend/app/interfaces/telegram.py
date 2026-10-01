from __future__ import annotations

import asyncio
import re
import time
import uuid
from datetime import datetime, timedelta

import httpx

from app.core.errors import ConfirmationRequired
from app.core.logging import get_logger, log_extra
from app.core.module import Module
from app.core.module_config import ConfigField
from app.modules.notifications.service import NotificationChannel

logger = get_logger("telegram")

TELEGRAM_API = "https://api.telegram.org"


class TelegramError(Exception):
    pass


class TelegramBot:
    def __init__(self, core, token: str = "", poll_interval: float = 2.0) -> None:
        self.core = core
        self.token = token or core.settings.telegram_bot_token
        self.poll_interval = poll_interval or core.settings.telegram_poll_interval
        self._offset = 0
        self._task: asyncio.Task | None = None
        self._running = False
        self.last_poll: float = 0.0
        self.last_error: str = ""
        self.processed = 0

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _url(self, method: str) -> str:
        return f"{TELEGRAM_API}/bot{self.token}/{method}"

    def send_message(self, chat_id: str | int, text: str) -> bool:
        if not self.configured:
            return False
        try:
            response = httpx.post(self._url("sendMessage"), json={"chat_id": chat_id, "text": text}, timeout=15)
            response.raise_for_status()
            return bool(response.json().get("ok"))
        except Exception as exc:  # noqa: BLE001
            logger.error("telegram send failed: %s", exc)
            return False

    def chat_id_for(self, user_id: str | None = None) -> str | None:
        session = self.core.session_factory()
        try:
            from sqlalchemy import select

            from app.core.models import User

            user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none() if user_id else self.core.default_user()
            return user.telegram_chat_id if user else None
        finally:
            session.close()

    async def start(self) -> None:
        if not self.configured or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("telegram bot started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.error("telegram poll failed: %s", exc)
            self.last_poll = time.time()
            await asyncio.sleep(self.poll_interval)

    async def _poll_once(self) -> None:
        if not self.configured:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                self._url("getUpdates"),
                params={"offset": self._offset, "timeout": 10},
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise TelegramError(data.get("description", "telegram error"))
            updates = data.get("result", [])
        for update in updates:
            self._offset = max(self._offset, update.get("update_id", 0) + 1)
            await self._handle_update(update)

    async def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        if not chat_id or not text:
            return
        sender = message.get("from", {})
        self._remember_chat(chat_id, sender)
        self.processed += 1
        logger.info("telegram message received", extra=log_extra({"chat_id": chat_id, "text_prefix": text[:80]}))
        user, authorized = self._resolve_sender(chat_id, sender)
        if not authorized:
            self.send_message(chat_id, self._access_denied_text(sender))
            return
        command = self._command(text)
        if command is not None:
            await self._run_command(chat_id, user, command)
            return
        await self._chat(chat_id, user, text)

    # ----- пользователи -----

    def _find_user_by_telegram(self, tg_user_id: str, tg_username: str | None):
        from sqlalchemy import or_, select

        from app.core.models import User

        session = self.core.session_factory()
        try:
            stmt = select(User)
            if tg_user_id:
                stmt = stmt.where(User.telegram_user_id == str(tg_user_id))
            elif tg_username:
                stmt = stmt.where(User.telegram_username == tg_username)
            else:
                return None
            return session.execute(stmt.limit(1)).scalars().first()
        finally:
            session.close()

    def _remember_chat(self, chat_id, sender) -> None:
        try:
            tg_user_id = sender.get("id")
            tg_username = sender.get("username")
            session = self.core.session_factory()
            from sqlalchemy import select

            from app.core.models import User

            user = None
            if tg_user_id:
                user = session.execute(
                    select(User).where(User.telegram_user_id == str(tg_user_id))
                ).scalars().first()
            if user is None and tg_username:
                user = session.execute(
                    select(User).where(User.telegram_username == tg_username)
                ).scalars().first()
            if user is None:
                user = User(
                    username=f"tg_{tg_user_id or tg_username or 'unknown'}",
                    full_name=sender.get("first_name"),
                    role="member",
                )
                session.add(user)
            user.telegram_user_id = str(tg_user_id) if tg_user_id else user.telegram_user_id
            if tg_username:
                user.telegram_username = f"@{tg_username}"
            user.telegram_chat_id = str(chat_id)
            user.last_seen_at = datetime.utcnow()
            session.commit()
            session.close()
        except Exception:  # noqa: BLE001
            logger.exception("failed to remember telegram chat")

    def _resolve_sender(self, chat_id, sender):
        user = self._find_user_by_telegram(str(sender.get("id") or ""), sender.get("username"))
        if user is None:
            self._remember_chat(chat_id, sender)
            user = self._find_user_by_telegram(str(sender.get("id") or ""), sender.get("username"))
        if user is None:
            return None, False
        return user, user.role in ("owner", "admin")

    def _access_denied_text(self, sender) -> str:
        username = sender.get("username")
        name = f"@{username}" if username else str(sender.get("first_name") or sender.get("id") or "?")
        return (
            "У вас пока нет доступа к Angel AI. "
            f"Ваш Telegram: {name} (id: {sender.get('id')}).\n\n"
            "Владелец системы должен выдать вам права администратора "
            "в web-интерфейсе: Система → Модули → Telegram → Пользователи."
        )

    # ----- команды -----

    def _command(self, text: str) -> tuple[str, str | None] | None:
        parts = text.split()
        if parts and parts[0].startswith("/"):
            name = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else None
            return name, arg
        return None

    async def _run_command(self, chat_id, user, command) -> None:
        name, arg = command
        if name in ("/start", "/help"):
            self.send_message(chat_id, self._help_text(user))
        elif name == "/status":
            self.send_message(chat_id, self._status_text())
        elif name == "/me":
            self.send_message(
                chat_id,
                f"Вы: <b>{user.full_name or user.username}</b>\nРоль: {self._role_ru(user.role)}\n"
                f"Telegram: {user.telegram_username or '-'}",
                parse_mode="HTML",
            )
        elif name == "/note":
            self._cmd_note(chat_id, user, arg)
        elif name == "/notes":
            self._cmd_notes(chat_id, user)
        elif name == "/remind":
            self._cmd_remind(chat_id, user, arg)
        elif name == "/confirm":
            self._resolve_confirmation(chat_id, user, arg, approve=True)
        elif name == "/deny":
            self._resolve_confirmation(chat_id, user, arg, approve=False)
        else:
            self.send_message(chat_id, f"Неизвестная команда: {name}.\n\n{self._help_text(user)}")

    def _help_text(self, user) -> str:
        return (
            "Angel AI — бот.\n\n"
            "Команды:\n"
            "/note Заголовок — описание. — быстро создать заметку\n"
            "/notes — последние заметки\n"
            "/remind <текст> <дата> — напоминание, например:\n"
            "   /remind купить ножницы 18:00\n"
            "   /remind оплатить счёт 20.09 12:00\n"
            "/confirm <id> — подтвердить действие\n"
            "/deny <id> — отклонить действие\n"
            "/status — состояние системы\n"
            "/help — помощь\n\n"
            "Или просто напишите запрос в свободной форме — например: "
            "«создай заметку о запуске Angel AI»."
        )

    def _cmd_note(self, chat_id, user, arg) -> None:
        if not arg:
            self.send_message(chat_id, "Формат: /note Заголовок\nОписание (по желанию).")
            return
        lines = arg.splitlines()
        title = lines[0].strip()
        content = "\n".join(lines[1:]).strip()
        if not title:
            self.send_message(chat_id, "Укажите заголовок заметки.")
            return
        notes = self.core.modules.get("notes")
        if notes is None or notes.service is None:
            self.send_message(chat_id, "Модуль заметок недоступен.")
            return
        try:
            note = notes.service.create({"title": title, "content": content}, user_id=str(user.id))
            self.send_message(chat_id, f"Заметка создана: «{title}»")
        except Exception as exc:  # noqa: BLE001
            self.send_message(chat_id, f"Не удалось создать заметку: {exc}")

    def _cmd_notes(self, chat_id, user) -> None:
        notes = self.core.modules.get("notes")
        if notes is None or notes.service is None:
            self.send_message(chat_id, "Модуль заметок недоступен.")
            return
        try:
            items = notes.service.list()[:10]
        except Exception:  # noqa: BLE001
            items = []
        if not items:
            self.send_message(chat_id, "Заметок пока нет. Создайте: /note Заголовок")
            return
        lines = [f"Последние заметки ({len(items)}):"]
        for n in items:
            lines.append(f"• {n['title']}")
        self.send_message(chat_id, "\n".join(lines))

    def _cmd_remind(self, chat_id, user, arg) -> None:
        if not arg:
            self.send_message(chat_id, "Формат: /remind <текст> <дата и время>. Примеры:\n/remind купить хлеб 18:00\n/remind оплатить 20.09 12:00\n/remind доктор 2026-09-15 09:30.\nПовтор: добавьте слово ежедневно/еженедельно/ежемесячно.")
            return
        reminder, parsed, error = self._parse_reminder(arg)
        if error:
            self.send_message(chat_id, error)
            return
        reminders = self.core.modules.get("reminders")
        if reminders is None or reminders.service is None:
            self.send_message(chat_id, "Модуль напоминаний недоступен.")
            return
        try:
            record = reminders.service.create(
                {
                    "text": reminder,
                    "trigger_at": parsed.isoformat(),
                    "timezone": "UTC",
                    "repeat_rule": parsed.repeat_rule or {},
                },
                user_id=str(user.id),
            )
            self.send_message(chat_id, f"Напоминание создано: «{reminder}» — {parsed.isoformat()}")
        except Exception as exc:  # noqa: BLE001
            self.send_message(chat_id, f"Не удалось создать напоминание: {exc}")

    def _parse_reminder(self, arg):
        class Parsed:
            def __init__(self, when, repeat_rule):
                self.when = when
                self.repeat_rule = repeat_rule

        text = arg.strip()
        repeat_rule = {}
        for word, freq in (("ежедневно", "daily"), ("ежедневная", "daily"), ("еженедельно", "weekly"),
                           ("еженедельная", "weekly"), ("ежемесячно", "monthly"), ("ежемесячная", "monthly")):
            if word in text.lower():
                repeat_rule = {"freq": freq}
                text = re.sub(re.escape(word), "", text, flags=re.IGNORECASE)
                break

        # ищем дату-время в конце текста
        candidate = text.rsplit(None, 1)[-1].strip(".,;")
        when = self._parse_datetime_token(candidate)
        reminder = text.rsplit(None, 1)[0].strip().strip(".,; ") if when is not None else text
        if when is None:
            m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", text)
            if m:
                when = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
                reminder = (text[:m.start()] + text[m.end():]).strip().strip(".,;")
        if when is None:
            m = re.search(r"(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\s+(\d{2}:\d{2})", text)
            if m:
                when = self._parse_dmy(m.group(1), m.group(2))
                reminder = (text[:m.start()] + text[m.end():]).strip().strip(".,;")
        if when is None:
            return reminder, None, (
                "Не удалось распознать дату. Примеры:\n/remind купить хлеб 18:00\n/remind оплатить 20.09 12:00"
            )
        return reminder, Parsed(when, repeat_rule), None

    def _parse_datetime_token(self, token: str):
        if not token:
            return None
        m = re.fullmatch(r"(\d{2}):(\d{2})", token)
        if m:
            now = datetime.utcnow()
            when = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            if when <= now:
                when += timedelta(days=1)
            return when
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?", token)
        if m:
            return datetime(*[int(g) for g in m.groups() if g is not None])
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", token)
        if m:
            return datetime(*[int(g) for g in m.groups()])
        return None

    def _parse_dmy(self, day_part: str, time_part: str) -> datetime | None:
        parts = re.split(r"[./-]", day_part)
        try:
            hour, minute = (int(x) for x in time_part.split(":"))
        except Exception:  # noqa: BLE001
            return None
        now = datetime.utcnow()
        if len(parts) == 2:
            day, month = int(parts[0]), int(parts[1])
            year = now.year
        elif len(parts) == 3:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 100:
                year += 2000
        else:
            return None
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            return None

    def _resolve_confirmation(self, chat_id, user, confirmation_id, approve: bool) -> None:
        if not confirmation_id:
            self.send_message(chat_id, "Укажите id подтверждения: /confirm <id>")
            return
        try:
            record = self.core.permissions.resolve(confirmation_id, approve)
            action = "подтверждено" if approve else "отклонено"
            self.send_message(chat_id, f"Действие {action} ({record.tool_name}).")
        except (KeyError, ValueError, PermissionError) as exc:
            self.send_message(chat_id, f"Ошибка: {exc}")

    async def _chat(self, chat_id, user, text: str) -> None:
        outcome = await self.core.ai_runtime.chat(text, user_id=str(user.id), tool_names=None, kind="chat")
        if outcome.status == "awaiting_confirmation":
            self.send_message(
                chat_id,
                f"Для этого действия требуется подтверждение.\n/confirm {outcome.confirmation_id} — подтвердить\n/deny {outcome.confirmation_id} — отменить",
            )
        elif outcome.status == "completed":
            self.send_message(chat_id, outcome.text or "Готово.")
        else:
            self.send_message(chat_id, f"Ошибка: {outcome.error or 'неизвестная ошибка'}")

    def _role_ru(self, role: str) -> str:
        return {"owner": "владелец", "admin": "администратор", "member": "ожидает доступа"}.get(role, role)

    def _status_text(self) -> str:
        snap = self.core.health.snapshot()
        lines = ["Angel AI — состояние:"]
        names = {
            "core": "Ядро", "database": "База данных", "llm": "LLM", "scheduler": "Планировщик",
            "workers": "Воркеры", "telegram": "Telegram",
        }
        for name, entry in snap.items():
            if name.startswith("_"):
                continue
            marker = "OK" if entry["ok"] else "FAIL"
            label = names.get(name, name)
            detail = entry["detail"]
            lines.append(f"• {label}: {marker}" + (f" — {detail}" if not entry["ok"] and isinstance(detail, str) else ""))
        lines.append(f"• модули: {', '.join(self.core.modules.statuses().keys())}")
        return "\n".join(lines)

    def health_check(self) -> tuple[bool, str]:
        if not self.configured:
            return False, "telegram token not configured"
        return True, f"ok (polled {max(0, int((time.time() - self.last_poll)))}s ago, {self.processed} processed)"


class TelegramChannel(NotificationChannel):
    name = "telegram"

    def __init__(self, bot: TelegramBot) -> None:
        self.bot = bot

    def send(self, user_id: str | None, title: str, text: str) -> bool:
        if not self.bot.configured:
            return False
        chat_id = self.bot.chat_id_for(user_id)
        if not chat_id:
            return False
        message = f"{title}\n{text}" if title else text
        return self.bot.send_message(chat_id, message)


class TelegramModule(Module):
    name = "telegram"
    version = "0.2.0"
    description = "Telegram bot: quick notes/reminders, user access and notifications."
    description_ru = "Telegram-бот: быстрые заметки/напоминания, доступ пользователей и уведомления."
    capabilities = ["telegram.bot", "telegram.commands", "telegram.users", "telegram.notifications"]

    config_fields = [
        ConfigField("token", "Токен бота", field_type="password", default="",
                    hint="Получите у @BotFather", value_type="str"),
        ConfigField("poll_interval", "Интервал опроса (сек)", field_type="number", default=2.0,
                    value_type="float"),
        ConfigField("enabled", "Бот включён", field_type="bool", default=True, value_type="bool"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.bot: TelegramBot | None = None

    async def reconfigure(self) -> None:
        cfg = self.config_values()
        self.core.settings.telegram_bot_token = str(cfg.get("token") or "")
        try:
            self.core.settings.telegram_poll_interval = float(cfg.get("poll_interval", 2.0))
        except (TypeError, ValueError):
            pass

    async def start(self) -> None:
        cfg = self.config_values()
        await super().start()
        if not cfg.get("enabled", True):
            self.core.telegram = None
            return
        bot = TelegramBot(self.core, token=str(cfg.get("token") or ""),
                          poll_interval=float(cfg.get("poll_interval") or 2.0))
        self.bot = bot
        self.core.telegram = bot
        notifications = self.core.modules.get("notifications")
        if notifications is not None and notifications.service is not None:
            notifications.service.register_channel(TelegramChannel(bot))
        self.core.health.register("telegram", bot.health_check)
        await bot.start()

    async def stop(self) -> None:
        if self.bot is not None:
            await self.bot.stop()
        self.bot = None
        self.core.telegram = None
        self.core.health.unregister("telegram")
        await super().stop()

    def health_check(self) -> tuple[bool, str]:
        if self.bot is None:
            return False, "telegram not started"
        return self.bot.health_check()


def install_telegram(core):
    """Лёгкий паттерн установки: возвращает бота, если модуль уже запущен и настроен."""
    module = core.modules.get("telegram")
    if module is None:
        return None
    return getattr(module, "bot", None)