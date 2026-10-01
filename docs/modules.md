# Angel AI — Модули

Каждый модуль — самодостаточный блок: модели, сервис, инструменты (`tools`), REST-роутер,
события и внутренние обработчики. Регистрация: `core.register_module(Module())`.

| Модуль | Название | Возможности | Зависимости |
|---|---|---|---|
| Notes | `notes` | crud, иерархия, папки, категории, теги, связи, поиск | — |
| Reminders | `reminders` | crud, повторения, запуски (runs) | — |
| Notifications | `notifications` | доставка в каналы (web/telegram) | — |
| AI | `ai` | задачи AI, health LLM | — |
| Markdown | `markdown` | проекция в Obsidian Vault | notes |

## Notes
- Модели: `Note`, `Folder`, `Category`, `Tag`, `note_tags`, `NoteRelationship`.
- Иерархия заметок без циклов; удаление родителя переставляет детей к дедушке (FK `SET NULL`, без каскада delete-orphan).
- Папки: вложенность с защитой от циклов, удаление возвращает заметки и подпапки на уровень выше.
- События: `notes.note_created/updated/deleted`, `folder_*`, `category_*`.

## Reminders
- Модели: `Reminder` (статусы `scheduled/triggered/completed/cancelled`), `ReminderRun`.
- Повторения: `repeat_rule: {freq: daily|weekly|monthly, interval, until}`, учёт timezone.
- `occurrence_key = YYYYMMDDThhmmss` + UNIQUE → идемпотентный запуск.
- События: `reminders.reminder_created/updated/deleted/cancelled/triggered/run_created`.

## Notifications
- Модель `Notification`; каналы: `web` (всегда), `telegram` (после `install_telegram`).
- Неизвестный канал → fallback на `web`.
- События: `notifications.notification_requested/sent`.

## Markdown
- Не модуль домена, а проекция: читает БД, пишет `.md`.
- `full_sync()` удаляет файлы из манифеста и пересоздаёт всё; `sync_note/delete_note/sync_folder` — точечные операции.
- При старте модуля выполняется первичный `full_sync`.