# Angel AI — Development

## Окружение
Windows/PowerShell. **Важно:** `python` в PATH может быть Store-заглушкой; используйте
реальный интерпретатор или venv:

```powershell
# создание venv (реальный Python)
E:\angel\backend\.venv\Scripts\python.exe   # уже создано
```

Установка зависимостей:
```powershell
& "E:\angel\backend\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

## Запуск
```powershell
# из backend/
& ".venv\Scripts\python.exe" -m app.main
# сайт: http://127.0.0.1:8000, API: /api/v1
```

Конфигурация — env `ANGEL_*` или `.env` в `backend/` см. `.env.example`.

## Тесты
```powershell
& ".venv\Scripts\python.exe" -m pytest            # 58 тестов
& ".venv\Scripts\python.exe" -m pytest tests/test_notes.py -q
```
- `pytest.ini`: `asyncio_mode=auto`, путь на `tests/`.
- `conftest.py` собирает тестовый `Core` (SQLite-файл во временной папке, изолированный vault),
  тестовый «фиктивный» LLM (`FakeProvider` с JSON-конвертом) и dry-scheduler (без фонового тика).
- Покрытие: core/events, notes (CRUD, иерархия, циклы, папки/категории/связи/поиск, события),
  reminders (повторения, idempotency runs, timezone), permissions (все режимы, подтверждения),
  tools (валидация/права/confirm), agent (одношаговые, мультишаг, unknown tool, security),
  scheduler-воркер end-to-end, markdown (frontmatter/индексы/удаление/подписка на события),
  API через TestClient.

## Стиль
- Python 3.14, аннотации `| None`.
- Sync-сервисы вызываются в API/воркерах напрямую или через `asyncio.to_thread`.
- UUID везде строкой: нормализация `to_uuid()` перед связыванием с `Uuid`-колонками.
- Никаких «тайных» подключений к БД в AI; всё через инструменты.
- Комментарии в коде — по минимуму; логи через `app.core.logging.get_logger`.

## Известные локальные особенности
- Без LLM и Telegram-токена health `llm`/`telegram` = false (ожидаемо).
- SQLite не держит tz — при сравнении datetime нормализуем к aware UTC.
- События персистятся асинхронно (`core.publish` создаёт задачу).