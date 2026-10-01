# 14. Логирование и «Статистика»

## Как устроено логирование

Два параллельных потока записи (обе работают всегда):

1. **stdout** — корневой `StreamHandler` c JSON-форматом (`JsonFormatter`,
   `app/core/logging.py`). Строка вида:
   ```
   {"ts":"2026-09-10T21:24:47","level":"ERROR","logger":"telegram",
    "message":"telegram poll failed: [Errno 11001] getaddrinfo failed"}
   ```
   Поля: `ts`, `level`, `logger`, `message`; добавляются при наличии:
   `correlation_id`, `request_id`, `task_id`, `user_id`, `exc`, `extra_fields`.
2. **БД** — `DatabaseLogHandler`, пишет структурированные записи в таблицу
   `log_records` (устанавливается в `bootstrap_core` через
   `install_db_logging`). Это то, что показывает раздел «Статистика».

Контекст запросов: middleware ставит `correlation_id`/`request_id`
(из заголовков `x-correlation-id` или UUID), воркеры — `task_id`.
По `correlation_id` в логах и `events` можно проследить всю цепочку.

## Как проверять логи

### Способ 1 (рекомендуемый): раздел «Статистика» в веб-интерфейсе
Сайдбар → **Статистика**. Возможности:
- **Сводка**: всего записей, ошибок за 24 ч, предупреждений, записей за 24 ч,
  топ-логгеры, карточка «Последняя ошибка».
- **Фильтры**:
  - уровень: все / только ошибки (ERROR+CRITICAL) / DEBUG / INFO / WARNING /
    ERROR / CRITICAL;
  - модуль/логгер (содержит подстроку, напр. `telegram`, `llm`, `core`);
  - поиск по тексту сообщения и трейсу;
  - даты «С» / «По» (YYYY-MM-DD).
- **Таблица**: время (локальное), уровень, логгер, сообщение.
  Клик по строке — детали: extra-поля, correlation/request/task id, **трейс
  исключения** (`exc_text`).
- **«Контекст до»** (у ошибок) — показывает 15 записей, предшествующих
  ошибке (то, что ей предшествовало), в хронологическом порядке.
- **Автообновление** — галочка, обновление каждые 5 с.
- **Экспорт .txt** — текущий отфильтрованный набор.
- **Очистить по фильтру** — удаление записей (с подтверждением).

### Способ 2: JSON-лог консоли
Лаунчер `start.bat` показывает stdout uvicorn в консольном окне. Строки — JSON.

### Способ 3: SQL (для продвинутых)
```sql
SELECT ts, level, logger, message, exc_text FROM log_records
WHERE level IN ('ERROR','CRITICAL') ORDER BY ts DESC LIMIT 50;
```

### Способ 4: API
`GET /api/v1/logs?errors_only=true&module=telegram&from_date=2026-09-11`
(см. `11-api.md`).

## Как читать запись лога

- `ts` — время (UTC raw / локальное в UI).
- `level` — DEBUG/INFO/WARNING/ERROR/CRITICAL.
- `logger` — источник: `core`, `modules.ai`, `llm.http`, `telegram`,
  `markdown.sync`, `workers.scheduler`, `ai.agent`, `events` и т.д.
- `message` — текст; у ошибок — причина.
- `exc`/`exc_text` — полный трейс (в UI — в раскрытой строке).
- `correlation_id` — связать записи одного запроса/действия.

## Пример разбора типичной ошибки

Запись: `ERROR telegram "telegram poll failed: [Errno 11001] getaddrinfo failed"`.
- `11001` (Windows `WSAHOST_NOT_FOUND`) + `getaddrinfo` = **сбой DNS** при
  обращении к `api.telegram.org`, т.е. нет выхода в интернет/сбой резолвера
  в момент опроса. Это не ошибка приложения: следующий цикл опроса повторится
  автоматически (health-статус telegram в «Системе» вернётся в норму после
  восстановления сети).
- Как искать причину: «Статистика» → фильтр `module=telegram`, раскрыть строку,
  при ошибке — кнопка «Что предшествовало» (например, перед этим может быть
  `telegram bot started` без дальнейших успешных poll).

## Уровни и удержание (retention)

- В БД пишутся записи от уровня `ANGEL_LOG_LEVEL` (INFO по умолчанию; в dev
  полезно DEBUG).
- Устаревшие записи удаляются автоматически в процессе записи: retention
  14 дней, «чистка» каждые ~256 записей.
- Очистить всё/выборку вручную — кнопка «Очистить по фильтру» (или
  `DELETE /api/v1/logs`).

## Советы

- При проблеме в Telegram: смотрите `module=telegram`, ключевые строки
  `telegram bot started` (после перезапуска модуля) и `telegram poll failed`.
- При проблеме AI: фильтр `module=llm` или `module=ai`; ошибка 404 на
  `/v1/chat/completions` = модель не найдена в Ollama — проверьте раздел
  «Настройки → AI и Ollama» и кнопку «Получить модели».
- При проблемах синхронизации vault: `module=markdown`.