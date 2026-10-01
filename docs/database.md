# Angel AI — База данных

SQLAlchemy 2.0 (sync) + миграции (папка `backend/migrations`, alembic). Локально по умолчанию
`sqlite:///./angel.db`; для продакшена — `ANGEL_DATABASE_URL=postgresql+psycopg://...`.

**PostgreSQL — source of truth.** Все записи, кроме файлов vault, живут в БД.

## Соединение
- `app/infrastructure/db.py`: `engine`, `sessionmaker` (`autoflush=False`, `expire_on_commit=False`).
- SQLite: `check_same_thread=False`; `:memory:` + `StaticPool` для тестов.
- `init_db(url)` пересоздаёт глобальные engine/session; `create_all`/`drop_all` для dev/тестов.

## Утилиты
- `utcnow()` — часовой пояс UTC везде.
- `to_uuid(value)` — нормализация строк/UUID в `uuid.UUID | None` (используется при связывании
  с `Uuid`-колонками, напр. `user_id` из `ToolContext`).

## Модели (`app/models.py` — агрегатор)

### Core (`app/core/models.py`)
| Таблица | Назначение | Ключевое |
|---|---|---|
| `users` | пользователь | username unique, telegram_chat_id, settings JSON |
| `events` | персистентная шина | event_type, aggregate_*, payload JSON, user_id |
| `activity` | аудит | actor/action/module/tool/status/duration_ms, correlation_id |
| `permission_rules` | права | (user_id, permission) unique, mode |
| `confirmations` | подтверждения | params_hash, status, expires_at |

### Notes
`notes` (folder_id/category_id/parent_id FK, importance, sort_order), `folders` (parent_id,
description), `categories` (name unique, color), `tags` (name unique), `note_tags` (M2M),
`note_relationships` (source/target/relation_type, UNIQUE тройка).

### Reminders
`reminders` (trigger_at, timezone, repeat_rule JSON, status), `reminder_runs`
(UNIQUE (reminder_id, occurrence_key), статус, result JSON, attempts).

### Notifications
`notifications` (channel, title, text, status, read, sent_at/read_at).

## Соглашения
- PK — `uuid.UUID` с `default=uuid.uuid4`; FK-строки нормализуются `to_uuid`.
- Timestamps: `DateTime(timezone=True)` + `utcnow()`; SQLite возвращает naive — код умеет
  приравнивать к aware UTC (`expires_at` сравнение в permissions).
- JSON-поля: `payload`, `repeat_rule`, `settings`, `metadata`.
- Индексы на часто используемых фильтрах (title, parent, folder, category, updated, user_id/status).