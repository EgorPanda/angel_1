# Angel AI — Workers

Два асинхронных механизма в `app/workers/`:

## WorkerPool (`runner.py`)
Конвейер off-щих фоновых задач в рамках event loop.

- `enqueue(kind, payload)` — кидает `WorkItem` в `asyncio.Queue`; `kind` обязан быть
  зарегистрирован (`KeyError` иначе).
- `register(kind, handler)` — обработчик `async def handler(payload, item)`.
- `start()` создаёт `concurrency` воркеров (`_consume`), `stop()` отменяет.
- Retries: при исключении `remaining_retries-1`, `delay(retry_delay)` и возврат в очередь
  (настраивается через `ANGEL_WORKER_CONCURRENCY`, `ANGEL_WORKER_RETRY_ATTEMPTS`).
- Статистика: `processed/failed/enqueued/active`, `status()` для `/api/v1/workers/status`.

## Scheduler (`scheduler.py`)
Периодический цикл (`scheduler_interval`) — отвечает ТОЛЬКО за время, не за отправку.

- `_scan()`: `RemindersService.due(now)` → для каждого: `run_for_occurrence` (исключает дубль) →
  `create_run` (UNIQUE-ключ) → событие `reminders.reminder_triggered`.
- `create_run` устойчив к гонкам (перехват IntegrityError → возврат существующего run).
- Статус/статистика для `/api/v1/scheduler/status` (`last_scan_at`, `scanned`, `triggered`,
  `last_error`).

## WorkersModuleConnector (`module.py`)
Связывает события и задачи:
- Подписка `reminders.reminder_triggered` → enqueue `process_reminder`.
- `process_reminder(payload, item)`: run → статус `processing` → AI Runtime с
  `tool_names=["send_reminder_notification"]` → fallback шаблонным сообщением, если AI слабо
  отвечает или недоступен → `processed` с результатом. Идемпотентность: повторная обработка
  run со статусом `processed` пропускается.
- `sync_markdown(payload, item)`: действия `note|delete|folder|full`.
- Регистрирует health `scheduler` и `workers`.

## Конфигурация
| Переменная | По умолчанию |
|---|---|
| `ANGEL_SCHEDULER_INTERVAL` | 5.0 |
| `ANGEL_WORKER_CONCURRENCY` | 2 |
| `ANGEL_WORKER_RETRY_ATTEMPTS` | 3 |

## Поток напоминания (end-to-end)
`Scheduler._scan` → `Run` (idempotent) → `reminder_triggered` → `process_reminder` →
`AI Runtime (tool send_reminder_notification)` → `NotificationService` → web/telegram →
run → `processed`.