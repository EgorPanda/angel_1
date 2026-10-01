import json
import logging
import sys
import time
from contextvars import ContextVar
from typing import Any

correlation_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
request_var: ContextVar[str | None] = ContextVar("request_id", default=None)
task_var: ContextVar[str | None] = ContextVar("task_id", default=None)
user_var: ContextVar[str | None] = ContextVar("user_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for var, name in (
            (correlation_var, "correlation_id"),
            (request_var, "request_id"),
            (task_var, "task_id"),
            (user_var, "user_id"),
        ):
            value = var.get()
            if value:
                payload[name] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class DatabaseLogHandler(logging.Handler):
    """Пишет записи лога в таблицу log_records (для экрана «Статистика»).

    Хранит структурированные строки: ts, level, logger, message, extra,
    текст исключения и идентификаторы (correlation/request/task/user).
    Периодически удаляет старые записи (retention_days).
    """

    def __init__(self, session_factory, level: int = logging.INFO,
                 retention_days: int = 14, flush_every: int = 256) -> None:
        super().__init__(level=level)
        self._sf = session_factory
        self._retention_days = retention_days
        self._flush_every = flush_every
        self._writes = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._write(self._row(record))
        except Exception as exc:  # noqa: BLE001
            try:
                sys.stderr.write(f"[loghandler] write failed: {exc}\n")
            except Exception:  # noqa: BLE001
                pass

    def _row(self, record: logging.LogRecord) -> dict[str, Any]:
        import traceback

        extra = dict(getattr(record, "extra_fields", None) or {})
        ts = time.time()
        exc_text = None
        if record.exc_info:
            try:
                exc_text = "".join(traceback.format_exception(*record.exc_info))
            except Exception:  # noqa: BLE001
                exc_text = None
        return {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name or "root",
            "message": record.getMessage(),
            "extra": extra,
            "exc_text": exc_text,
            "correlation_id": getattr(record, "correlation_id", None) or correlation_var.get(),
            "request_id": getattr(record, "request_id", None) or request_var.get(),
            "task_id": getattr(record, "task_id", None) or task_var.get(),
            "user_id": getattr(record, "user_id", None) or user_var.get(),
        }

    def _write(self, row: dict[str, Any]) -> None:
        from datetime import datetime, timedelta, timezone

        from app.core.models import LogRecord

        session = self._sf()
        try:
            record = LogRecord(
                ts=datetime.fromtimestamp(row["ts"], tz=timezone.utc),
                level=row["level"],
                logger=row["logger"],
                message=row["message"],
                extra=row["extra"],
                exc_text=row["exc_text"],
                correlation_id=row["correlation_id"],
                request_id=row["request_id"],
                task_id=row["task_id"],
                user_id=row["user_id"],
            )
            session.add(record)
            self._writes += 1
            if self._writes >= self._flush_every:
                cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
                session.execute(
                    LogRecord.__table__.delete().where(LogRecord.ts < cutoff)
                )
                self._writes = 0
            session.commit()
        finally:
            session.close()


def install_db_logging(session_factory, level: str = "INFO") -> DatabaseLogHandler:
    """Добавляет в корневой логгер режим записи логов в БД."""
    handler = DatabaseLogHandler(session_factory, level=level.upper() or logging.INFO)
    logging.getLogger().addHandler(handler)
    return handler


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(columns: dict[str, Any]) -> dict[str, Any]:
    return {"extra_fields": columns}