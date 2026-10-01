# 03. Бэкенд: структура и важные файлы

## Дерево каталогов

```
backend/
├── app/
│   ├── main.py                     # FastAPI app, bootstrap, роуты, статика
│   ├── config.py                   # Settings (env ANGEL_*) + get_settings()
│   ├── models.py                   # единая точка импорта всех моделей ORM
│   ├── ai/
│   │   ├── agent.py                # Agent: цикл «LLM ↔ инструменты»
│   │   ├── runtime.py              # AIRuntime: chat(), health_check()
│   │   ├── schemas.py              # AgentRequest / AgentOutcome
│   │   └── providers/
│   │       ├── factory.py          # build_provider(), get_provider()
│   │       ├── base.py             # LLMProvider, Message, Completion, ToolCall
│   │       ├── http.py             # OpenAI-совместимый HTTP
│   │       ├── local.py            # локальный (Ollama /v1) — наследник http
│   │       └── fallback.py         # FallbackProvider (primary+fallback)
│   ├── api/
│   │   └── system.py               # системный роутер /api/v1
│   ├── core/
│   │   ├── core.py                 # класс Core
│   │   ├── module.py               # базовый класс Module
│   │   ├── registry.py             # ModuleRegistry
│   │   ├── module_config.py        # ConfigField + ModuleConfigService
│   │   ├── tools.py                # Tool, ToolRegistry, ToolContext, ToolResult
│   │   ├── permissions.py          # PermissionService, PermissionMode
│   │   ├── events.py               # Event, Command, EventBus, CommandBus
│   │   ├── activity.py             # ActivityService
│   │   ├── health.py               # HealthChecker
│   │   ├── lifecycle.py            # SystemState, ModuleStatus, Lifecycle
│   │   ├── logging.py              # JSON-формат, DatabaseLogHandler
│   │   ├── models.py               # User, EventRecord, ActivityRecord,
│   │   │                           # PermissionRule, ConfirmationRecord,
│   │   │                           # ModuleSetting, LogRecord
│   │   └── errors.py               # AngelError и наследники
│   ├── infrastructure/
│   │   └── db.py                   # Base, engine, session, create_all, utcnow
│   ├── interfaces/
│   │   └── telegram/               # TelegramModule, бот, команды, роутер
│   ├── markdown/
│   │   └── module.py               # MarkdownModule: vault + синхронизация
│   ├── modules/
│   │   ├── notes/                  # модель, сервис, api, tools (модуль notes)
│   │   ├── reminders/              # reminders
│   │   ├── notifications/          # notifications
│   │   └── ai/
│   │       ├── module.py           # AIModule (конфигурация + health)
│   │       └── models.py           # AITask
│   └── workers/
│       ├── module.py               # WorkersModuleConnector
│       ├── runner.py               # WorkerPool
│       ├── scheduler.py            # Scheduler
│       └── handlers/               # process_reminder, sync_markdown, ...
├── migrations/                     # Alembic (env.py, versions/*.py)
├── tests/                          # pytest (conftest.py + test_*.py)
├── angel.db                        # dev-БД (SQLite), создаётся автоматически
└── .env                            # (создаётся по желанию) ANGEL_* переменные
```

## Как стартует приложение (`app/main.py`)

- `app = create_app()` на этапе импорта (`app.main:app` для uvicorn).
- `lifespan`: `setup_logging(level)` → `bootstrap_core` → `mount_routes` →
  yield → `teardown_core`.
- `mount_routes`: все роутеры модулей, затем статика `/static`, `/`, `/app.js`,
  `/style.css`.
- `run()` — uvicorn 127.0.0.1:8000 (используется start.bat).

## Ключевые «как это работает»

### SQLAlchemy sync
- Сессии создаются через `core.session_factory()`; соглашение: открыть → сделать →
  `close()` в `finally`. Коммиты — на уровне сервисов/роутеров.
- `app/core/models.py` + `app/models.py` — все таблицы; `create_all()` создаёт
  недостающие при старте.
- UTC: `utcnow()` — время создания всех записей (timestamptz).

### Ошибки
- Базовый `AngelError` имеет `code`, `message`, `http_status`, `details`.
- `LLMError`, `DatabaseError`, `PermissionDenied`, `ToolExecutionError`,
  `ValidationError (Angel)` — наследники.

### Логирование
- `setup_logging()`: корневой StreamHandler в stdout в JSON-формате.
- Шумные логгеры (`uvicorn.access`, `httpx`) снижены до WARNING.
- `DatabaseLogHandler` (см. `14-logging.md`) пишет копию в `log_records`.
- Контекстные переменные: correlation/request/task/user id.

## Что важно не ломать

- `core.session_factory()` — единственная точка создания сессий.
- Регистрация модулей до `core.start()` (иначе роутеры/инструменты не прицепятся).
- Применение конфигурации ai к settings до `build_provider` (см. 02).
- Перед изменением схемы БД: новая Alembic-миграция + `pytest`.

## Тесты

- `tests/conftest.py` — `make_settings()` (временный SQLite/vault),
  `build_core()` (без HTTP), `FakeProvider` (имитация LLM).
- Покрытие: заметки, напоминания, permissions, tools, агент, события,
  markdown, scheduler, API (dashboard, confirmations, ai/chat, markdown/sync,
  logs, ollama/models, ai/test).
- Запуск: `& "E:\angel\backend\.venv\Scripts\python.exe" -m pytest -q`.