# 13. Конфигурация

## Переменные окружения (`.env`)

Файл `.env` создаётся в `backend/` (или рядом с запуском). Префикс всех
переменных: `ANGEL_`. Настройки приоритета: **модульные настройки (БД) >
`.env` > дефолты в коде** (для полей, которые есть у модулей).

| Переменная | Дефолт | Назначение |
|-----------|--------|-----------|
| `ANGEL_APP_NAME` | `Angel AI` | название |
| `ANGEL_APP_ENV` | `dev` | env |
| `ANGEL_LOG_LEVEL` | `INFO` | уровень логов (stdout + БД) |
| `ANGEL_DATABASE_URL` | `sqlite:///./angel.db` | БД |
| `ANGEL_DEFAULT_USER_USERNAME` | `angel` | основной пользователь (owner) |
| `ANGEL_TELEGRAM_BOT_TOKEN` | `` | токен бота |
| `ANGEL_TELEGRAM_POLL_INTERVAL` | `2.0` | опрос бота, сек |
| `ANGEL_LLM_PROVIDER` | `ollama` | `ollama` / `local` / `api` |
| `ANGEL_LLM_MODEL` | `qwen2.5:7b` | модель |
| `ANGEL_LLM_API_URL` | `http://localhost:11434/v1` | строка подключения LLM |
| `ANGEL_LLM_API_KEY` | `` | ключ (для api) |
| `ANGEL_LLM_TEMPERATURE` | `0.3` | температура |
| `ANGEL_LLM_MAX_TOKENS` | `1024` | токены |
| `ANGEL_LLM_TIMEOUT` | `60.0` | таймаут, сек |
| `ANGEL_LLM_MAX_STEPS` | `8` | шаги агента |
| `ANGEL_LLM_FALLBACK_*` | `` | резервный провайдер |
| `ANGEL_MARKDOWN_VAULT_PATH` | `../vault` | путь хранилища |
| `ANGEL_MARKDOWN_ENABLED` | `true` | вкл маркдаун |
| `ANGEL_SCHEDULER_INTERVAL` | `5.0` | период планировщика, сек |
| `ANGEL_WORKER_CONCURRENCY` | `2` | воркеры |
| `ANGEL_WORKER_RETRY_ATTEMPTS` | `3` | ретраи |
| `ANGEL_TASK_ENQUEUE_INTERVAL` | `5.0` | интервал постановки задач |
| `ANGEL_CONFIRMATION_TTL_SECONDS` | `300` | TTL подтверждений |
| `ANGEL_CORS_ORIGINS` | `http://localhost:5173,...` | CORS |

## Модульные настройки (таблица `module_settings`)

Изменяются через UI (Система → Модули, или раздел «Настройки») и не требуют
правки `.env`. Поля модулей: см. `05-modules.md` и `06-ai-agents.md`.
Секреты (telegram token, llm_api_key) хранятся в БД с пометкой `password`
(показ точки; в API возвращаются как есть — доступ только локальный).

## Секреты и безопасность

- Не коммитить `.env` с токенами и ключами (в репозиторий — только пример).
- Telegram-токен и LLM-ключи — конфиденциальны; при утечке — отозвать.
- Приложение рассчитано на локальную работу (127.0.0.1). Для публичного
  доступа — прокси со TLS и ограничением доступа.

## Применение настроек

- `.env` читается при старте (`pydantic-settings`).
- Модульные — сразу после сохранения + **перезапуск модуля** (или авто-
  перезапуск модуля ai в разделе «Настройки»).
- Логирование стартует из `ANGEL_LOG_LEVEL`.