# 06. AI: провайдеры LLM, агент, инструменты, Ollama

## Провайдеры LLM

`app/ai/providers/`:

- `base.py`: интерфейс `LLMProvider` (`name`, `complete(messages, tools,
  temperature, max_tokens, timeout) → Completion`, `available()`,
  `health_check()`), датаклассы `Message`, `Completion`, `ToolCall`.
- `http.py` `HttpProvider` («api»): OpenAI-совместимый
  `POST {api_url}/v1/chat/completions` (умный выбор endpoint: если URL
  заканчивается на `/v1` — `.../v1/chat/completions`, иначе добавляет `/v1/...`),
  поддержка `tools`/`tool_choice: auto`, `Authorization: Bearer`.
- `local.py` `LocalProvider` («local»/«ollama»): наследник `http`, без ключа;
  по умолчанию `http://localhost:11434/v1`.
- `fallback.py` `FallbackProvider`: пробует primary, при ошибке — fallback.
- `factory.py`: `build_provider(settings)` + `get_provider()` (lru_cache).
  - `llm_provider == "api"` → `HttpProvider`.
  - иначе (`local`, `ollama`) → `LocalProvider`.
  - если задан `llm_fallback_provider` → `FallbackProvider(primary, fallback)`.

## Провайдеры и конфигурация

Поле `llm_provider` поддерживает значения (см. модуль `ai`):
- `ollama` — локальная Ollama (рекомендуется; URL `http://localhost:11434/v1`).
- `local` — любой локальный OpenAI-совместимый (LM Studio и т.п.).
- `api` — удалённый OpenAI-совместимый API (ключ).

Строка подключения и модель выбираются в веб-интерфейсе:
«Настройки → AI и Ollama» (или «Система → Модули → ai»).
Кнопки: «Получить модели из Ollama» (список из `GET /api/tags`), «Проверить
подключение» (`POST /api/v1/ai/test`), «Сохранить» (+ авто-перезапуск модуля).

### Список моделей Ollama
Эндпоинт `GET /api/v1/ai/ollama/models?base_url=...` стучится в нативный
Ollama-API (`{base}/api/tags`) и возвращает `{"models": [...], "base_url": ...}`.
Базовый URL выводится из `llm_api_url` (отрезается `/v1`).

### Проверка подключения
`POST /api/v1/ai/test` собирает провайдера из переданных (или текущих)
настроек и зовёт `provider.available()` (GET на эндпоинт; ответ <500 = доступен).
Возвращает `{ok, provider, model, api_url, message}`.

## AI-рантайм и агент

`app/ai/runtime.py` `AIRuntime`:

- `chat(text, user_id, correlation_id, tool_names, kind) → AgentOutcome`.
- `ensure_agent()` создаёт/переиспользует `Agent(core, core.llm)`.
- `health_check()` → health провайдера.

`app/ai/agent.py` `Agent`:

- Многошаговый цикл (до `llm_max_steps`, по умолчанию 8).
- На каждом шаге `llm.complete(messages, tools=схемы инструментов)`.
- **Нативные tool_calls включены по умолчанию** (`AgentRequest.native_tools=True`);
  если модель не вернула `tool_calls`, агент парсит JSON-конверт из текста
  (`_parse_envelope`) — `{"tool": "...", "arguments": {...}}`.
- **Внутренние инструменты скрыты от модели**: `Tool.internal=True` исключается
  из каталога (`tool_catalog`), поэтому агент не может их вызвать.
- **Защита от зацикливания**: одинаковые вызовы (name+arguments) не
  выполняются дважды за один запуск — на повтор агент даёт гард-сообщение
  модели; если после этого модель снова просит инструмент — цикл завершается
  (`status=completed` с текстом). Лимит шагов тоже завершает запуск мягко, а не
  ошибкой.
- **Режим «строгого формата»**: если пользователь явно требует точный формат
  вывода («строго в формате», «чистый json», «без пояснений» и т.п. — список в
  `Agent._is_strict_format`), запуск идёт в чистом режиме: минимальный системный
  промпт, без контекста и без инструментов; ответ возвращается дословно
  (status=completed, steps=1). Режим не активируется, если в тексте есть
  действия («создай», «удали», «отправь»…).
- При `tool_calls` выполняет инструменты через `ToolRegistry`; перед
  выполнением — `core.permissions.request(...)`.
- При тексте — завершает.
- Результат: `AgentOutcome {status, text, tool_calls, confirmation_id, error,
  steps}`.

## Доступные инструменты агента (ToolRegistry)

Регистрируются модулями в `on_register`.

Заметки (`permission` по умолчанию `allow`):
- `create_note`, `get_note`, `update_note`, `delete_note`, `search_notes`,
  `list_notes`, `create_folder`, `update_folder`, `delete_folder`,
  `create_category`, `rename_category`, `delete_category`.

Напоминания: `create_reminder`, `update_reminder`, `delete_reminder`,
`cancel_reminder`, `list_reminders`.

Уведомления: `send_notification`, `send_reminder_notification`
(`send_reminder_notification` — внутренний инструмент планировщика:
`internal=True`, модели не показывается).

Режимы по умолчанию и права см. `07-tools-permissions.md`.

## Параметры AI (поля конфигурации модуля `ai`)

| Поле | Тип | Дефолт | Назначение |
|------|-----|--------|-----------|
| `llm_provider` | select | `ollama` | `ollama` / `local` / `api` |
| `llm_model` | text | `qwen2.5:7b`* | имя модели у провайдера |
| `llm_api_url` | text | `http://localhost:11434/v1` | строка подключения |
| `llm_api_key` | password | `` | для api-провайдера |
| `llm_temperature` | number(float) | 0.3 | креативность |
| `llm_max_tokens` | number(int) | 1024 | лимит токенов ответа |
| `llm_timeout` | number(float) | 60 | таймаут запроса, сек |
| `llm_max_steps` | number(int) | 8 | шаги агента |
| `llm_fallback_provider` | select | `` / выключен | резервный провайдер |
| `llm_fallback_api_url/api_key/model` | … | `` | конфиг резерва |

\* В `angel.db` для модуля `ai` сохранено переопределение
   `llm_model` → `qwen2.5:7b-instruct` (текущая дефолтная модель на ПК;
   установлены также `llama3.1:8b` и `llama3.2:latest`). Дефолты в коде:
   `qwen2.5:7b`.

## Важные нюансы

1. **Модель должна быть установлена в Ollama.** Если `llm_model` не найден,
   Ollama отвечает HTTP 404 → `LLMError`. Поэтому в UI есть «Получить модели».
2. **Применение конфигурации**: изменения вступают в силу после перезапуска
   модуля ai; при старте приложения конфигурация ai из БД применяется к
   `settings` до сборки провайдера (см. `02-architecture.md`).
3. **Небольшие модели** (llama3.2/llama3.1:8b) могут вместо точного ответа
   «выдумывать» действия по содержанию контекста (например, заметок) или
   оборачивать JSON в markdown-фенсы. Для надёжного tool-calling и строгого
   JSON рекомендуется `qwen2.5:7b-instruct` (установлена на ПК).
4. `/ai/chat` использует `core.ai_runtime`; текст пользователя — обязателен,
   пустой → 422.