# 08. События, команды, пул задач, планировщик

## Шина событий (EventBus)

`app/core/events.py`:

- `Event {type, aggregate_type, aggregate_id, payload, correlation_id,
  user_id, occurred_at}`.
- `Command {type, payload, ...}` — императивные команды.
- `EventBus`:
  - `subscribe(event_type, handler)` / `unsubscribe(...)`;
  - `async publish(event)` — сначала вызывает **sink** (по умолчанию —
    персист в таблицу `events`), затем всех подписчиков (async/async safe);
  - ошибки изолированы (`logger.exception`, не роняют остальных).
- `InProcessCommandBus`: `register(command_type, handler)`, `dispatch(command)`.
- `core.publish(event | **kwargs)` — публикует событие (в текущем loop или в
  фоновой задаче), `core.command(...)` — создаёт команду.

События модулей (точный список — в коде модулей; при изменении — обновить
этот раздел). Напоминания (`aggregate_type="reminder"`):
- `reminders.reminder_created` — создано напоминание; payload `{text}`,
  `user_id` — автор.
- `reminders.reminder_updated` / `reminders.reminder_deleted` /
  `reminders.reminder_cancelled` — аналогично.
- `reminders.reminder_triggered` — напоминание сработало.
- `reminders.reminder_run_created` — создан run (история срабатывания);
  `aggregate_id` = id напоминания, payload
  `{run_id, reminder_id, occurrence_key, scheduled_at, text}`,
  `user_id` отсутствует (контекст планировщика).
Уведомления (`aggregate_type="notification"`): `notifications.notification_requested`.
Заметки (`aggregate_type="note"`): `notes.note_created`, `notes.note_deleted`
(и др.). Markdown: `markdown:synced`.

## Журнал событий

Sink пишет каждое событие в `events` (payload — JSON). Это хроника:
по `correlation_id` можно восстановить всю цепочку действий.

## Пул задач (WorkerPool)

`app/workers/runner.py`:

- `WorkerPool(concurrency, retry_policy)`: очередь задач + N воркеров.
- `enqueue(name, payload)` — постановка; `processed/failed/enqueued/active`
  счётчики.
- Ретраи по политике (`worker_retry_attempts`, default 3).
- Статус: `GET /api/v1/workers/status`.

## Планировщик (Scheduler)

`app/workers/scheduler.py`:

- Тикает с периодом `scheduler_interval` (default 5 сек).
- Каждый тик сканирует модули на «запланированные работы» (напр. reminder
  со `status=scheduled` и `trigger_at <= now`) и ставит задачи в пул.
- Метрики тика: `scanned`, `triggered`, `last_tick`, `last_error`.
- Статус: `GET /api/v1/scheduler/status`.

## Коннектор модуля workers (WorkersModuleConnector)

`app/workers/module.py` (не является обычным модулем, ставится в bootstrap):

- Регистрирует обработчики пула для модулей:
  - `process_reminder` — срабатывание напоминания → создаёт `Notification`;
  - `sync_markdown` — полная синхронизация vault (см. `10`).
- Вешает на шину событий/функции модулей задачи (взаимосвязь:
  напоминания → уведомления).

## Связка картинкой

```
Ticker (планировщик)
   │  tick каждые N сек
   ▼
scan модулей → задачи (reminder due и т.п.)
   │                          ▲
   ▼                          │
WorkerPool (N воркеров, retry)│
   │  обработчик              │ activity/уведомления
   ▼                          │
выполнить бизнес-действие ─────┘
   │
   ▼
EventBus.publish → events + подписчики
```

## Настройки workers/планировщика (`.env`)

- `ANGEL_SCHEDULER_INTERVAL` (сек)
- `ANGEL_WORKER_CONCURRENCY`
- `ANGEL_WORKER_RETRY_ATTEMPTS`
- `ANGEL_TASK_ENQUEUE_INTERVAL`