# 07. Инструменты, разрешения, подтверждения

## Инструмент (Tool)

`app/core/tools.py`:

- `Tool` — базовый класс: `name`, `description`, `permission` (строка вида
  `module.action`), `default_mode` (`PermissionMode`), `input_schema` (pydantic,
  опционально), `module` (имя модуля-владельца), `internal` (bool, по умолчанию
  `False`).
- **`internal=True`** — инструмент недоступен модели: не попадает в
  `tool_catalog` (каталог в системном промпте и нативные `tools` для LLM).
  Используется для служебных инструментов планировщика
  (`send_reminder_notification`).
- `validate(params)` — pydantic-валидация аргументов.
- `async execute(params, ctx)` — типичный конвейер:
  1. валидация;
  2. `core.permissions.request(permission, tool_name, params, default,
     user_id, correlation_id, message)`;
  3. если `needs_confirmation` → вернуть `ToolResult(needs_confirmation=True,
     confirmation_id=...)` (инструмент НЕ выполняется);
  4. если `forbid` → `PermissionDenied`;
  5. выполнить `run(validated, ctx)`; записать `activity` (ok/error +
     duration_ms); вернуть `ToolResult`.
- `ToolContext`: `user_id`, `correlation_id`, `task_id`, `core`, `extra`.
- `ToolRegistry`: `register/unregister/get/require/list`.

### Инструменты и их permissions

| Группа | Инструменты | Permissions |
|--------|-------------|-------------|
| Заметки | create_note, create_folder, create_category | `notes.create` |
| | get_note, search_notes, list_notes | `notes.read` |
| | update_note, update_folder, rename_category | `notes.update` |
| | delete_note, delete_folder, delete_category | `notes.delete` |
| Напоминания | create_reminder | `reminders.create` |
| | update_reminder, cancel_reminder | `reminders.update` |
| | delete_reminder | `reminders.delete` |
| | list_reminders | `reminders.read` |
| Уведомления | send_notification | `notifications.send` |
| | send_reminder_notification (internal) | `notifications.reminder` |

По умолчанию все режимы — `ALLOW` (кроме того, что пользователь настроит).

## Режимы разрешений

`app/core/permissions.py`, enum `PermissionMode`:

- `ALLOW` — инструмент выполняется автоматически.
- `CONFIRM` — создаётся `ConfirmationRecord` (статус `pending`), агент ждёт
  одобрения человека; без подтверждения инструмент не выполняется.
- `FORBID` — отказ (`PermissionDenied`).

Порядок приоритета: rule для конкретного `user_id` > rule «для всех»
(null user) > `default_mode` инструмента.

`PermissionService`:
- `set_rule(permission, mode, user_id=None)` / `reset_rule(permission,
  user_id=None)` (таблица `permission_rules`).
- `request(...)` — принимает решение и, при `CONFIRM`, создаёт подтверждение.
- `pending(user_id)` — список ожидающих подтверждений.
- `resolve(confirmation_id, approve=True/False)` — одобрить/отклонить
  (меняет статус, при одобрении инструмент можно выполнить).

## Подтверждения (confirmations)

- Таблица `confirmations` (см. `04-database.md`).
- TTL подтверждения — `confirmation_ttl_seconds` (default 300), `expires_at`.
- API:
  - `GET /api/v1/system/confirmations` — ожидающие;
  - `POST /api/v1/system/confirmations/{id}/approve` (или `/deny`);
  - `GET /api/v1/system/permissions` — список инструментов и их режимов;
  - `POST /api/v1/system/permissions/{permission}` `{mode}` — задать режим;
  - `DELETE /api/v1/system/permissions/{permission}` — сброс к дефолту.

## Пользователи и роли (взаимодействие с разрешениями)

- Каждый инструмент выполняется от имени `ctx.user_id` (по умолчанию —
  основной пользователь).
- Telegram-команды (см. `09`) исполняются от имени Telegram-пользователя;
  бот проверяет роли (`owner/admin`).

## Журнал действий

Каждый вызов инструмента логируется в `activity`:
`action=tool:<name>`, `module=<module>`, `status=ok|error`, `duration_ms`,
`correlation_id`, при ошибке — `metadata={error: ...}`.