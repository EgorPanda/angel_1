# Angel AI — Permissions (Разрешения)

Реализация: `app/core/permissions.py`, модель `PermissionRule`, `ConfirmationRecord`.

## Режимы
- `allow` — выполнять без вопросов;
- `confirm` — требовать подтверждение (одноразовое, по хэшу параметров);
- `forbid` — запретить всегда.

`default_mode` задаётся инструментом; `PermissionRule` (per-user) переопределяет режим для
конкретного `permission`. Правило со значением `allow` снижает, `forbid` блокирует,
отсутствие правила = default.

## Модель подтверждения
`confirmation -> confirmations`:
- `params_hash = sha256(canonical JSON аргументов)` — подтверждение верно только для тех же аргументов;
- lifecycle: `pending → approved → used` (или `denied`, `expired`);
- `expires_at = created + confirmation_ttl_seconds` (настройка, по умолчанию 300 с);
- одно подтверждение расходуется на ОДИН запуск инструмента.

## Поток
1. `Tool.execute` → `permissions.request(permission, tool, params, default_mode, user_id)`.
2. `mode_for(...)` находит результирующий режим (default ∪ rule).
3. Если `confirm`: `_consume_approved` ищет `approved`-подтверждение с тем же `params_hash`
   и не истёкшее → используется (`used`) → `allow`. Иначе создаётся `pending` подтверждение.
4. Оператор одобряет/отклоняет через UI («Подтверждения»), Telegram (`/confirm <id>`, `/deny <id>`)
   или API (`/api/v1/system/confirmations/{id}/approve|deny`).

## Правила
API: `GET /api/v1/system/permissions` (каталог + текущие режимы),
`POST /api/v1/system/permissions/{permission}` `{mode: allow|confirm|forbid}`,
`DELETE /api/v1/system/permissions/{permission}` — сброс к default.

## Удобный default по категориям
- `confirm`: `delete_note`, `delete_folder`, `delete_category`, `delete_reminder`, `send_notification`.
- `allow`: всё остальное (чтение, создание, правки, служебные уведомления напоминаний).

## Безопасность
- `hash_params` порядок-независим (sort_keys), `ensure_ascii=False`, `default=str`.
- Только pending-записи доступны для подтверждения; повторное использование одобрения невозможно.
- Сравнение `user_id` при подтверждении защищает от чужих подтверждений.