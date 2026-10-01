# AGENTS.md — правила для команд/ассистентов (Angel AI)

## Обязательное правило (НЕЛЬЗЯ нарушать)

**Каждое изменение кода приложения должно сопровождаться обновлением
соответствующей документации.** Это касается любых правок: фиксов,
добавления функций, рефакторинга, схемы БД, API, настроек.

Документация живёт в `DOCUMENTATION/` (см. `DOCUMENTATION/README.md`).
Перед завершением задачи проверьте, что актуализированы ВСЕ затронутые факты:
эндпоинты (`11-api.md`), таблицы БД (`04-database.md`), поля конфигурации
модулей (`05-modules.md`, `06-ai-agents.md`, `13-configuration.md`),
инструменты/разрешения (`07-tools-permissions.md`), разделы интерфейса и UI
(`12-frontend.md`, `15-user-guide.md`), логирование (`14-logging.md`),
развёртывание/настройки Ollama (`16-deployment.md`, `06-ai-agents.md`).

## Технический стек и ключевые факты (для быстрого контекста)

- Python 3.14; venv `backend\.venv`; запуск тестов:
  `& "E:\angel\backend\.venv\Scripts\python.exe" -m pytest -q` (из `backend/`).
- FastAPI + SQLAlchemy 2 (sync) + Alembic; UI — vanilla JS в `frontend/`.
- Приложение: FastAPI на `127.0.0.1:8000`; лаунчер — `E:\angel\start.bat`
  (venv → deps → `alembic upgrade head` → браузер → uvicorn).
- Health-ключи: `core, database, llm, module:<name>, telegram, scheduler,
  workers` (внимание: БД — `database`, не `db`).
- DB logging: `DatabaseLogHandler` пишет в `log_records` (эндпоинты `/logs*`);
  конфигурация ai из БД применяется к settings ДО `build_provider` в bootstrap.
- Доступ к данным — только через SQLAlchemy/`core.session_factory()`;
  строки в JSON-колонках (`module_settings.value`) — сериализованный JSON,
  редактировать только через приложение/ORM (не сырым sqlite-текстом).
- Конфигурация модулей: дефолты + `module_settings` (БД приоритетнее); после
  `save_config` нужен перезапуск модуля; модуль ai в UI сам перезапускается.
- Провайдеры LLM: `ollama`/`local` → LocalProvider (`/v1`), `api` → HttpProvider;
  список моделей Ollama — `GET /ai/ollama/models` (`{base}/api/tags`);
  проверка подключения — `POST /ai/test`.
- Модель по умолчанию `qwen2.5:7b`; на ПК пользователя установлена
  `llama3.2:latest`. Неверная модель → 404 на `/v1/chat/completions`.
- Telegram-бот: токен в конфиге модуля; неизвестные пользователи создаются с
  ролью `member`; owner защищён.
- Не добавлять лишних комментариев в код. Не использовать эмодзи в UI/коде.
- Не коммитить/публиковать секреты (`.env`, token, ключи).

## Порядок работы с задачами

1. Изучите текущий код и `DOCUMENTATION/` (не противоречьте коду).
2. Вносите изменения; запускайте `pytest`; проверяйте E2E при необходимости.
3. Обновите документацию (см. правило выше).
4. Кратко отчитайтесь: что изменено, что обновлено в документации.