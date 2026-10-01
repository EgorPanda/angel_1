# 11. HTTP API

Базовый префикс всех эндпоинтов: `/api/v1`. Ответы — JSON. Ошибки: FastAPI
`{"detail": ...}` или `AngelError` → `{"error": code, "message": msg,
"details": ...}` с HTTP-статусом.

> Актуальный список всегда виден в Swagger:
> `http://127.0.0.1:8000/docs`.

## Система (`app/api/system.py`)

**Состояние и модули**
- `GET /system/status` — состояние системы, модули, capabilities.
- `GET /system/modules` — информация о модулях (включая `config_fields`).
- `POST /system/modules/{name}/start|stop|restart` — управление модулем.
- `GET|PUT /system/modules/{name}/config` — поля/значения конфигурации;
  PUT сохраняет (применить = перезапуск модуля).

**Здоровье**
- `GET /system/health` — ключи: `core`, `database`, `llm`, `telegram`,
  `scheduler`, `workers`, `module:*`; `healthy=true/false`.

**Пользователи и роли**
- `GET /system/users` — список, роли, telegram-поля, `authorized`.
- `POST /system/users/{id}/role` `{role: owner|admin|member}` — смена роли
  (owner защищён).

**Разрешения и подтверждения**
- `GET /system/permissions` — инструменты: `permission`, `default`, `current`.
- `POST /system/permissions/{permission}` `{mode: allow|confirm|forbid}`.
- `DELETE /system/permissions/{permission}` — сброс.
- `GET /system/confirmations` — ожидающие подтверждения.
- `POST /system/confirmations/{id}/approve|deny` — решение.

**Воркеры и планировщик**
- `GET /workers/status` — пул задач.
- `GET /scheduler/status` — планировщик (tick, scanned/triggered, ошибки).

**Журнал**
- `GET /activity?limit=` — действия.

**Логи (для раздела «Статистика»)**
- `GET /logs?level=&errors_only=&module=&query=&from_date=&to_date=&limit=&offset=&order=`
  — записи логов, ответ `{items, total, limit, offset}`. `level` — точные
  уровни через запятую (DEBUG,INFO,WARNING,ERROR,CRITICAL); `errors_only=true`
  — ERROR/CRITICAL; `module` — LIKE по логгеру; `query` — по сообщению и
  трейсу; даты `YYYY-MM-DD` или `YYYY-MM-DDTHH:MM:SS`; `order=asc|desc`.
- `GET /logs/summary` — итоги: `total`, `levels` (по уровням), `today_total`,
  `today_errors`, `last_error` (объект), `top_loggers`.
- `DELETE /logs?<те же фильтры>` — удаление записей по фильтру.

**Дашборд**
- `GET /dashboard` — счётчики (заметки, напоминания, уведомления, активность),
  состояние, LLM, telegram.

**AI**
- `POST /ai/chat` `{text, user_id?}` — разговор с агентом; ответ
  `{status, text, tool_calls, confirmation_id, error, steps}`. Агенту доступны
  нативные `tool_calls` (по умолчанию) плюс JSON-конверт; при явном требовании
  вывода в строгом формате («строго в формате…») ответ возвращается дословно
  без инструментов и контекста. `status`: `completed` / `awaiting_confirmation`
  / `error`.
- `GET /ai/providers` — текущие настройки провайдера.
- `GET /ai/ollama/models?base_url=` — список моделей Ollama (нативный `/api/tags`).
- `POST /ai/test` `{llm_provider, llm_model, llm_api_url, llm_api_key}` —
  проверка подключения `{ok, provider, model, api_url, message}`.

**Markdown**
- `POST /markdown/sync` — запустить полную синхронизацию vault.

**Настройки**
- `GET /settings` — ключевые настройки системы.

## Модуль Заметки (`/notes`, `/folders`, `/categories`, `/tags`)

- `GET|POST /notes` — список (без папки/родителя) и создание.
- `GET /notes/search?q=` — поиск.
- `GET /notes/tree` — дерево.
- `GET|PATCH|DELETE /notes/{id}` — деталь/обновление/удаление.
- `POST /notes/{id}/relations`, `GET /notes/{id}/relations`,
  `DELETE /notes/relations/{relation_id}` — связи заметок.
- `GET|POST /folders`, `PATCH|DELETE /folders/{id}`.
- `GET|POST /categories`, `PATCH|DELETE /categories/{id}`.
- `GET /tags`.

## Модуль Напоминания (`/reminders`)

- `GET|POST /reminders` — список/создание.
- `GET|PATCH|DELETE /reminders/{id}`.
- `POST /reminders/{id}/cancel`.
- `GET /reminders/{id}/runs`, `GET /reminders/runs/{run_id}` — история.

Примечания по времени (`trigger_at`): если строка содержит явный offset/zone —
конвертируется в UTC; если without — интерпретируется в `timezone` (поле
запроса, по умолчанию `UTC`). Для «сработает сейчас» передавайте
`trigger_at` в прошлом в UTC (или укажите `timezone`, например
`Europe/Moscow`).

## Модуль Уведомления (`/notifications`)

- `GET /notifications` — список.
- `GET /notifications/channels` — каналы.
- `POST /notifications/{id}/read`, `POST /notifications/read-all`.

## Фронтенд (без префикса)

- `GET /` — index.html; `GET /app.js`, `GET /style.css`; `GET /static/*` —
  статические файлы.

## Примеры

```bash
# Логи за сегодня, только ошибки, по логгеру telegram
GET /api/v1/logs?errors_only=true&module=telegram&from_date=2026-09-11

# Получить модели Ollama
GET /api/v1/ai/ollama/models?base_url=http://localhost:11434

# Проверка подключения к Ollama
POST /api/v1/ai/test
{"llm_provider":"ollama","llm_model":"llama3.2:latest","llm_api_url":"http://localhost:11434/v1"}

# Посмотреть, что предшествовало ошибке (контекст до ts)
GET /api/v1/logs?to_date=<ts ошибки>&order=desc&limit=15
```