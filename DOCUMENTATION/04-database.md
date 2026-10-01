# 04. База данных

ORM: SQLAlchemy 2.x (Declarative), sync-сессии. База по умолчанию — SQLite
(`sqlite:///./angel.db`, файл `backend/angel.db`), продакшен — PostgreSQL через
`ANGEL_DATABASE_URL`. Все даты — `utcnow()` (timestamptz).

## Таблицы и назначение

### `users`
Основной пользователь и Telegram-пользователи.
- `id` UUID pk, `username` unique, `full_name`, `role`
  (`owner|admin|member`, server_default `member`), `settings` (JSON).
- Telegram-поля: `telegram_chat_id`, `telegram_user_id` (index),
  `telegram_username`, `last_seen_at`.
- Основной пользователь (username=`angel`) автоматически становится `owner`
  и его роль защищена от понижения.

### `index_notes`, `index_tags`, `index_links`, `index_tasks`

**Индексные таблицы Markdown-vault** (модуль `notes` теперь файловый: vault —
источник правды, БД — быстрый индекс, полный текст не хранится).

- `index_notes`: `path` (rel-путь в vault, unique), `title`, `note_type`,
  `business`, `status` (`active|archived`), `importance` (`low|medium|high`),
  `summary`, `user_id` (nullable, FK users, CASCADE), `created_at/updated_at`,
  `file_updated_at`. Индексы: `(path)`, `(note_type)`, `(status)`, `(title)`.
- `index_tags`: `index_note_id` (FK index_notes, CASCADE), `name`; unique
  `(index_note_id, name)` (uq_index_tag), индекс по `name`.
- `index_links`: `source_id` (FK index_notes, CASCADE), `source_path`,
  `target_path`, `target_id` (FK index_notes, SET NULL), `relation_type`,
  `label`, `created_at`; unique `(source_id, target_path)` (uq_index_link),
  индексы — `source_id`, `target_path`.
- `index_tasks`: `index_note_id` (FK index_notes, CASCADE), `text`, `done`,
  `due`, `priority`, `status`, `created_at/updated_at`; индексы `(done)`,
  `(due)`, `(index_note_id)`.
- `sync_state`: одна строка `id=1` — `last_sync_at`, `last_error`,
  `indexed_count`.

### `mocs`, `archive_mocs`

Авто-генерируемые MOC-файлы (карты заметок) прогрессируют при `full_sync`.
- `mocs`: `folder` (unique), `note_path` (unique, например
  `0_Входящие/0_Входящие_MOC.md`), `structure` (JSON: `{links:[...]}`),
  `updated_at`.
- `archive_mocs`: архивные проекты; `project_name` (unique), `description`,
  `original_folder`, `restored` (bool, true = возвращён из архива),
  `created_at/updated_at`.

### `reminders`, `reminder_runs`
Модуль напоминаний.
- `reminders`: `text`, `trigger_at`, `timezone`, `repeat` (`once|daily|weekly|
  monthly|yearly`), `status` (`scheduled|completed|cancelled|...`), `metadata`.
- `reminder_runs`: история срабатываний.

### `notifications`
Модуль уведомлений.
- `title`, `body`, `channel` (`web|telegram|...`), `read` (bool), `user_id`,
  `created_at`, `delivered_at`.

### `ai_tasks`
Очередь задач AI на фоне: `kind`, `payload`, `status/attempts/result/error`,
привязка к `task_id` пула, `created_at/updated_at`. Индекс `(status, created_at)`.

### `events`
Хроника событий (sink EventBus).
- `event_type`, `aggregate_type/id`, `payload` (JSON), `user_id`,
  `correlation_id`, `occurred_at`, `processed_at`.
- Индекс `(event_type, occurred_at)`.

### `activity`
Журнал действий (инструменты агента и др.).
- `user_id`, `actor` (`ai`, `system`, ...), `action` (напр. `tool:create_note`),
  `module`, `tool`, `status` (`ok|error`), `task_id`, `correlation_id`,
  `duration_ms`, `metadata` (JSON), `created_at`.
- Индекс `(user_id, created_at)`.

### `permission_rules`
Пользовательские переопределения режимов разрешений.
- `user_id` (null = для всех), `permission`, `mode`
  (`allow|confirm|forbid`), `updated_at`.
- Уникальный индекс `(user_id, permission)`.

### `confirmations`
Ожидающие подтверждения опасных действий агента.
- `user_id`, `permission`, `tool_name`, `params` (JSON) + `params_hash`,
  `status` (`pending|approved|denied|expired`), `message`,
  `correlation_id`, `created_at`, `expires_at`, `resolved_at`.
- Индекс `(user_id, status)`.

### `module_settings`
Конфигурация модулей поверх дефолтов/.env.
- `module`, `key`, `value` (JSON: строки/числа/булево), `updated_at`.
- Уникальный ключ `(module, key)` (uq_module_setting), индекс по `module`.
- Поле `value` хранит **сериализованный JSON** (например строка пишется как
  `"строка"`). Никогда не редактируйте ячейку «в лоб» мелким текстом — только
  через ORM/UI, иначе JSON-десериализация сломается.

### `log_records`
Логи приложения для экрана «Статистика» (пишет `DatabaseLogHandler`).
- `ts` (timestamptz), `level` (DEBUG/INFO/...), `logger`, `message` (Text),
  `extra` (JSON), `exc_text` (Text, трейс исключения), `correlation_id`,
  `request_id`, `task_id`, `user_id`.
- Индексы: `(level, ts)`, `(logger, ts)`, `ts`.
- Строка удаляется автоматически по retention (14 дней), write-cadence 256.

## Схема связей (кратко)

```
users 1─* notifications      users 1─* activity (user_id, nullable)
users 1─* events (nullable)  users 1─* confirmations (nullable)
notes *─1 folders            notes *─1 categories
notes *─* tags (note_tags)   notes.*─* notes (note_relationships)
notes *─0..1 notes (parent_id — подзаметка)
reminders *─1 users (nullable)   reminders 1─* reminder_runs
ai_tasks *─1 users (nullable)
```

## Миграции (Alembic)

- `backend/migrations/env.py` импортирует `app.models` → target_metadata.
- Список версий (ревизии до актуальных):
  - `... → ee9322807de8` «module settings and telegram users» (users.role,
    telegram-поля, module_settings).
  - `ee9322807de8 → 365e95b1cf71` «add log_records» (создание таблицы логов
    с guard-проверкой: если таблица уже есть — пропуск).
- Команды (в `backend/`):
  - `alembic upgrade head`
  - `alembic revision --autogenerate -m "name"`
  - `alembic downgrade -1`
- Лаунчер `start.bat` выполняет `alembic upgrade head` перед запуском.
- `create_all()` при старте сам создаёт недостающие таблицы (для dev-комфорта);
  миграции предназначены для согласованного обновления существующих БД.

## Соглашения

- Время — UTC. Вывод в UI — локальное время.
- UUID — pk для всех таблиц (`default=uuid.uuid4`).
- JSON-колонки для динамических данных (payload, metadata, settings, value).
- Для каждого нового индексируемого запроса — продуманный составной индекс.