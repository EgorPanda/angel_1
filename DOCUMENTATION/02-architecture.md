# 02. Архитектура

## Слои

```
┌──────────────────────────────────────────────────────────────┐
│ Интерфейсы                                                  │
│  • Веб SPA (frontend/app.js) — /static, /app.js, /style.css  │
│  • Telegram-бот (app/interfaces/telegram/)                   │
│  • REST API  /api/v1/* (system.py + роутеры модулей)          │
├──────────────────────────────────────────────────────────────┤
│ Ядро  (app/core)                                             │
│  Core (core.py) — концентратор всех зависимостей             │
│  модули (registry), инструменты (tools), permissions,        │
│  события (events), активность (activity), модульная          │
│  конфигурация (module_config), здоровье (health),            │
│  lifecycle (lifecycle), логирование (logging), ошибки,       │
│  пул задач (workers/runner.py)                               │
├──────────────────────────────────────────────────────────────┤
│ Модули (app/modules, app/markdown, app/interfaces)           │
│  notes, reminders, notifications, ai, markdown, telegram     │
├──────────────────────────────────────────────────────────────┤
│ Инфраструктура  (app/infrastructure)                         │
│  db.py (Base, engine, session), SQLAlchemy sync               │
├──────────────────────────────────────────────────────────────┤
│ Внешние системы                                              │
│  SQLite / PostgreSQL, Ollama / LLM API (httpx),               │
│  Telegram API, папка Markdown-vault                          │
└──────────────────────────────────────────────────────────────┘
```

## Ядро Core

`app/core/core.py`, класс `Core`. Создаётся в `bootstrap_core` (`main.py`),
хранит:

| Поле | Назначение |
|------|-----------|
| `settings` | `Settings` (pydantic, env `ANGEL_*`) |
| `lifecycle` | конечный автомат системы |
| `session_factory` | фабрика синхронных SQLAlchemy-сессий |
| `tools` | `ToolRegistry` (все инструменты агента) |
| `modules` | `ModuleRegistry` (все модули) |
| `permissions` | `PermissionService` (режимы allow/confirm/forbid + подтверждения) |
| `activity` | запись журнала действий |
| `module_config` | `ModuleConfigService` (таблица `module_settings`) |
| `health` | `HealthChecker` (health-эндпоинт) |
| `command_bus` | `InProcessCommandBus` |
| `events` | `EventBus` с sink → таблица `events` |
| `llm` | текущий LLM-провайдер |
| `ai_runtime` | `AIRuntime` (агент) |
| `telegram` | бот (ставится модулем telegram) |
| `worker_pool` | `WorkerPool` (очередь + воркеры) |
| `workers_connector` | мост планировщика/воркеров в модули |

Методы: `user_id()` (uuid основного пользователя), `default_user()`
(создаёт owner при первом старте), `reload_llm()` (пересборка провайдера),
`publish()` (асинхронная или фоновая публикация события), `new_context()`
(контекст инструмента), `register_module()`, `include_module_router()`,
`start()/shutdown()`, `setup_health_checks()`.

## Инициализация (bootstrap)

`app/main.py::bootstrap_core(settings)`:

1. `init_db(settings.database_url)` + `create_all()` (создаст недостающие таблицы).
2. Устанавливается **DB-логирование** (`install_db_logging`) — логгер пишет в
   `log_records`.
3. Регистрируются модули: **notes, reminders, notifications, ai, markdown,
   telegram** (в этом порядке).
4. Устанавливается `WorkersModuleConnector` (планировщик + воркеры,
   handlers `process_reminder`, `sync_markdown`).
5. **Конфигурация модуля ai поверх настроек**: `config_values()` модуля ai
   применяется к `settings` (провайдер/модель/URL из БД имеют приоритет) —
   это важно: иначе LLM соберётся из env-дефолтов.
6. Строится LLM-провайдер `build_provider(settings)`, `core.start(llm=...)`.
7. `core.setup_health_checks()`, старт коннектора воркеров, `default_user()`,
   старт модуля telegram.

Ошибки старта и все последующие записи логируются и (при доступной БД)
сохраняются в `log_records`.

## Жизненный цикл системы

- Состояния: `starting → running → stopping → stopped` (`app/core/lifecycle.py`).
- Модули имеют собственный статус (stopped/running/…).

## HTTP-слой

- `app/api/system.py` — системный роутер: статус, модули, конфигурация,
  health, пользователи/роли, permissions, подтверждения, workers, scheduler,
  activity, dashboard, logs (+ summary + delete), ai (chat, providers,
  ollama/models, test), markdown/sync, settings.
- Роутеры модулей: `/api/v1/*` (notes), `/api/v1/reminders/*`,
  `/api/v1/notifications/*`.
- Middleware: CORS + `trace_middleware` (x-correlation-id, x-request-id →
  контекстные переменные логирования).
- Обработчики исключений: `AngelError` → JSON c кодом/сообщением,
  `Exception` → 500 «internal error».

## Ключевые потоки

### Поток запроса к API
```
Request → trace_middleware → роутер → (module service / system callbacks)
  → session_factory() → операция SQL → ответ JSON
```

### Поток чата с агентом
```
POST /api/v1/ai/chat {text} → core.ai_runtime.chat()
  → Agent.run(): цикл до max_steps
      LLM.complete(messages, tools=схемы инструментов)
      если tool_calls → для каждого:
          permissions.request(permission, mode, ...)
            allow  → инструмент.execute(...) → activity.log
            confirm→ создаётся ConfirmationRecord, агент ждёт
            forbid → отказ
      если text → агент завершает
  → ответ {status, text, tool_calls, confirmation_id, steps, error}
```

### Поток напоминания
```
планировщик (tick) → находит reminders status=scheduled
  → worker handler process_reminder → создаёт Notification
  → событие reminder:due → уведомление (web/telegram)
```

### Поток Markdown-синхронизации
```
POST /api/v1/markdown/sync → worker handler sync_markdown
  → полная двусторонняя синхронизация vault ↔ заметки
```

### Поток события
```
core.publish(event) → EventBus.publish → sink → таблица events
  + подписчики модулей (event_subscriptions)
```

## Принцип «документация = правда»

Любая доработка кода обязана сопровождаться обновлением `DOCUMENTATION/*` и
правкой фактов в этом пакете (см. AGENTS.md).