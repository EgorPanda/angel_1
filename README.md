# Angel AI

Персональная модульная AI-система-компаньон. Один процесс (FastAPI) объединяет доменные модули,
AI Runtime (агент с инструментами), событийную шину, воркеры (планировщик напоминаний),
интерфейсы (Web + Telegram) и проекцию данных в Markdown Vault для Obsidian.

## Возможности
- **Заметки**: иерархия, папки, категории, теги, связи, полнотекстовый поиск.
- **Напоминания**: разовые и повторяющиеся (daily/weekly/monthly), с учётом timezone и идемпотентными запусками.
- **Уведомления**: каналы web и telegram.
- **AI-агент**: цикл «LLM → инструменты → результат», провайдеры (Ollama/OpenAI-compatible), подтверждения опасных действий.
- **Permissions**: allow/confirm/forbid на каждый инструмент; одноразовые подтверждения по хэшу параметров.
- **Markdown Vault**: проекция БД в Obsidian-совместимые `.md` с frontmatter и индексами.
- **Telegram**: long-polling бот (`/start`, `/status`, `/confirm <id>`, `/deny <id>`).
- **Веб-интерфейс**: SPA (Dashboard, Notes, Reminders, AI Chat, Activity, Settings).

## Быстрый старт

```powershell
# 1) зависимости
& "E:\angel\backend\.venv\Scripts\python.exe" -m pip install -r backend\requirements.txt

# 2) конфигурация (необязательно — есть defaults)
#   скопируйте backend\.env.example → backend\.env

# 3) запуск
& "E:\angel\backend\.venv\Scripts\python.exe" -m app.main
# → http://127.0.0.1:8000   API: /api/v1

# 4) тесты
& "E:\angel\backend\.venv\Scripts\python.exe" -m pytest
```

Без переменных `ANGEL_LLM_API_URL`/токена бот работает в режиме: health `llm/telegram = false`,
напоминания уходят шаблонным текстом (fallback).

## Структура
```
backend/
  app/
    core/            # события, разрешения, активность, lifecycle, health, tools
    infrastructure/  # БД
    modules/         # notes, reminders, notifications, ai
    markdown/        # проекция в vault
    workers/         # scheduler + worker pool
    ai/              # agent, providers
    interfaces/      # telegram
    api/             # /api/v1  (system, модульные роутеры)
    main.py          # bootstrap + приложение
  tests/             # pytest (58 тестов)
  requirements.txt
frontend/            # SPA (index.html, app.js, style.css)
docs/                # архитектура и руководства
vault/               # Markdown-проекция
```

## Документация
`docs/architecture.md`, `docs/implementation-plan.md`, `docs/modules.md`, `docs/ai.md`,
`docs/tools.md`, `docs/permissions.md`, `docs/database.md`, `docs/workers.md`,
`docs/markdown-sync.md`, `docs/development.md`.

## Docker (PostgreSQL + backend)
```bash
docker compose up --build
# backend: http://localhost:8000
```

## Лицензия
Проприетарная (личный проект).