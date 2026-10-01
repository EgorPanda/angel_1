# Angel AI — Architecture

Angel AI — персональная модульная AI-система-компаньон. Ядро — **модульный монолит**: один процесс
(uvicorn/FastAPI) размещает все доменные модули, AI-рантайм, инструменты, события, воркеры
и интерфейсы. PostgreSQL задуман как источник правды (SSOT), Markdown-хранилище — утилитарная
**проекция** для использования в Obsidian.

## Принципы

1. **PostgreSQL — source of truth.** Все данные живут в БД. Markdown Vault — производная проекция,
   её можно удалить и пересоздать из БД без потерь.
2. **Модульная монолитность.** Одно развёртывание, которое можно расширять блоками; каждый модуль —
   самодостаточен (models + service + tools + API + события).
3. **AI не трогает БД напрямую.** Модель взаимодействует только через **инструменты** (tools),
   которые проходят проверку разрешений и логируются.
4. **События вместо прямых связей.** Модули общаются через EventBus; События персистятся
   (таблица `events`) для аудита и последующей аналитики.
5. **Идемпотентность и безопасность по умолчанию.** Уникальные ключи, одноразовые подтверждения,
   отказоустойчивый scheduler и worker pool с retries.

## Компоненты

```
                    ┌────────────────────────────────────────────────┐
   Telegram  ◄────► │              Angel AI (FastAPI)                │
   Browser   ◄────► │                                                │
                    │  Core: lifecycle, events, permissions,         │
                    │        activity, health, modules registry,     │
                    │        tools registry                           │
                    │                                                │
                    │   Modules:  notes · reminders · notifications  │
                    │              · ai · markdown                    │
                    │   AI Runtime: Agent → LLM providers → Tools    │
                    │   Workers:   Scheduler + WorkerPool            │
                    └─────────────┬──────────────────┬───────────────┘
                                  │                  │
                      PostgreSQL  │                  │  Markdown Vault
                     (source of truth)              │  (projection)
```

## Слои

| Слой | Путь | Ответственность |
|---|---|---|
| Interfaces | `app/interfaces/` | Telegram long-polling бот |
| API | `app/api/`, `app/modules/*/api.py` | REST `/api/v1/*`, обслуживание SPA |
| AI Runtime | `app/ai/` | Agent, providers, prompt/context builders |
| Modules | `app/modules/{notes,reminders,notifications,ai}/` | Домены |
| Markdown | `app/markdown/` | Проекция в vault |
| Workers | `app/workers/` | Scheduler (время) + WorkerPool (выполнение) |
| Core | `app/core/` | Шины событий/команд, разрешения, активность, lifecycle |
| Infrastructure | `app/infrastructure/` | БД (engine/session), утилиты |

## Зависимости модулей

```
notes ───────────────► markdown (проекция событий notes)
notes ───────────────► ai (использует инструменты notes)
reminders ◄────────── scheduler (ReminderTriggered)
reminders ◄────────── workers (process_reminder задача)
notifications ◄────── reminders worker (send_reminder_notification)
```

## Ключевые потоки

### Напоминание
`Scheduler._scan()` → `RemindersService.due()` → `create_run()` (уникальный `occurrence_key`) →
событие `reminders.reminder_triggered` → `WorkersModuleConnector._on_reminder_triggered` →
задача `process_reminder` в `WorkerPool` → AI Runtime (инструмент `send_reminder_notification`) →
`NotificationService` → канал Telegram/Web. Если LLM недоступен — шаблонное сообщение (fallback).

### Заметка
`NotesService.create()` → событие `notes.note_created` → (а) `MarkdownModule` ставит задачу
`sync_markdown` в воркер; (б) событие сохраняется в `events`.

### Разговор с AI
`/api/v1/ai/chat` → `Agent.run()` → цикл: вызвать LLM → разобрать ответ (JSON-конверт
`{"tool": ..., "arguments": ...}` или native `tool_calls`, либо `{"text": ...}`) → проверить
инструмент → выполнить через PermissionService → вернуть результат модели → повторить
(до `llm_max_steps`).

## Идемпотентность

- `reminder_runs(reminder_id, occurrence_key)` — UNIQUE; `create_run` устойчив к гонке двух сканов.
- Подтверждения `confirmations(params_hash)` — одноразовые (status `pending → approved/used`).
- События персистятся с `occurred_at`; обработчики идемпотентны по бизнес-ключам.

## Безопасность

- Инструменты имеют `permission` + `default_mode` (`allow|confirm|forbid`).
- Режимы переопределяются правилами `permission_rules` (можно per-user).
- `delete_*` и `send_notification` по умолчанию требуют подтверждения.
- Подтверждения: параметры хэшируются (`params_hash`), TTL из `confirmation_ttl_seconds`.