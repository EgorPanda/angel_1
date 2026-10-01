# Angel AI — AI Runtime

Логика AI изолирована в `app/ai/`. Модель не имеет доступа к БД напрямую — только через
инструменты (см. `docs/tools.md` и `docs/permissions.md`).

## Провайдеры (`app/ai/providers/`)
- `local` — OpenAI-совместимый HTTP (по умолчанию `http://localhost:11434/v1`, Ollama).
- `http` — произвольный OpenAI-совместимый эндпоинт (`llm_api_url`/`llm_api_key`).
- `fallback` — один резервный провайдер на случай недоступности основного.
- Выбор: `Settings.llm_provider`, резерв — `llm_fallback_provider`.

Интерфейс `LLMProvider`:
- `complete(messages, tools, temperature, max_tokens, timeout)` → `Completion(text, tool_calls, usage)`;
- `available()`, `health_check()`.

## Agent (`app/ai/agent.py`)
`Agent.run()` — цикл:
1. Формирует сообщения: system-prompt + контекст (`ContextBuilder`: дата, окружение, сводка) + запрос пользователя.
2. Вызывает `provider.complete(...)`.
3. Разбирает ответ:
   - native `tool_calls` (OpenAI-style) — используется напрямую;
   - JSON-конверт в тексте: `{"tool": "...", "arguments": {...}}` или `{"text": "..."}` (допустимы ключи `tool_name`, `response`, `answer`; поддерживаются ```-fences);
   - иначе итог — финальный текст.
4. Для каждого вызова инструмента: проверка `tool_names`-ограничения → `Tool.execute` → результат
   добавляется сообщением `[TOOL RESULT for <name>]` (role user) → следующий шаг.
5. Лимит шагов: `llm_max_steps` (по умолчанию 8).
6. При `needs_confirmation` возвращает `awaiting_confirmation` + `confirmation_id`.

Результат: `AgentOutcome(status, text, tool_calls, confirmation_id, steps, usage, error)`.

## AIRuntime (`app/ai/runtime.py`)
Фасад `chat(text, user_id, kind, tool_names, message_history)` → создаёт `Agent`, сохраняет
задачу в `AITask`, возвращает `AgentOutcome`.

## Контекст
`ContextBuilder.build(user_id)` собирает: текущее время/дату, env, наличие LLM/Telegram,
счётчики по заметкам/напоминаниям/уведомлениям. Рендерится text-блоком перед запросом.

## Каталог инструментов
`PromptBuilder.tool_catalog(tool_names)` формирует JSON-схему (или список) доступных инструментов.
При `tool_names=[]` доступны все зарегистрированные инструменты модулей.

## Ограничения
- Расход контекста контролируется ленивой подгрузкой: промежуточные результаты НЕ сохраняются
  между вызовами `/ai/chat` (кроме сквозного `message_history` при необходимости).
- Ошибки LLM отображаются как `LLMError`; падения внутри шага помечаются в `AITask` как `failed`.