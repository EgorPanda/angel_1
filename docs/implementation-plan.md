# Angel AI — Plan Implementation

Фазы реализации. Текущее состояние: **фазы 1–7 выполнены** (см. чек-листы). Оставшиеся пункты — валидация на реальном PostgreSQL и внешние сервисы.

## Фаза 1. Анализ и проектирование
- Разобрана спецификация v1, составлена архитектура (см. `docs/architecture.md`).
- Определены: модульная монолитность, событийная шина, инструменты + разрешения, PostgreSQL SSOT + Markdown-проекция.
- **Статус: выполнено.**

## Фаза 2. Инфраструктура ядра
- [x] `Settings` (pydantic-settings, префикс `ANGEL_`, `.env`).
- [x] SQLAlchemy engine/session (`app/infrastructure/db.py`), `Base`, утилита `utcnow`.
- [x] Общие модели (`users`, `events`, `activity`, `permission_rules`, `confirmations`).
- [x] Ошибки, JSON-логирование (correlation/task/user контекст), lifecycle (states).
- [x] EventBus + CommandBus + персист событий.
- [x] PermissionService (allow/confirm/forbid, подтверждения, TTL, хэш параметров).
- [x] ActivityService (аудит действий + длительность).
- [x] HealthChecker, ModuleRegistry, ToolRegistry.
- [x] Core-facade: сборка модулей, worker pool, ai runtime, publish от событий и публикация событий.

## Фаза 3. Модули
- [x] Notes: модели (иерархия, папки, категории, теги, связи), repository, service, 12 инструментов, API, события.
- [x] Reminders: модели, повторения (daily/weekly/monthly), `occurrence_key`, runs, 5 инструментов, события.
- [x] Notifications: каналы (web/telegram), доставка, 2 инструмента.
- [x] AI: модуль (AITask, health), провайдеры (local/http/fallback), prompts/context builders.

## Фаза 4. Markdown-проекция
- [x] `MarkdownSyncService`: full_sync/sync_note/delete_note/sync_folder, frontmatter, `_Index.md`, манифест.
- [x] Подписка на события notes → enqueue `sync_markdown`.

## Фаза 5. Workers
- [x] `WorkerPool` (asyncio, concurrency, retries с задержкой, статус).
- [x] `Scheduler` (цикл, `_scan` due-reminders, диспетчеризация, защита от дублей).
- [x] `WorkersModuleConnector`: задачи `process_reminder`, `sync_markdown`; health scheduler/workers.

## Фаза 6. Интерфейсы
- [x] Telegram: TelegramBot (long polling), команды, `TelegramChannel`.
- [x] REST API `/api/v1` + SPA (Dashboard, Notes, Reminders, AI Chat, Activity, Settings, System).
- [x] CORS, middleware корреляции, обработчики ошибок, статика фронтенда.

## Фаза 7. Настройка и развёртывание
- [x] `pytest`-покрытие: 58 тестов (notes, reminders, permissions, tools, agent, scheduler, markdown, api, events).
- [x] `.env.example`, `docker-compose.yml` (postgres + backend), `.gitignore`, `README.md`.
- [x] Alembic-миграции (`backend/alembic.ini`, `migrations/`, initial revision, проверен `upgrade head`).
- [x] Полировка импортов: пустые `__init__.py` пакетов (`app/interfaces/__init__.py` и др.).

## Оставшиеся фазы (v1+)
- Верификация на реальном PostgreSQL.
- Реальный LLM и Telegram-токен (сейчас health по этим пунктам ожидаемо `false`).
- Расширенный ретрай-план воркеров (backoff), полноценный UI подтверждений на клиенте.