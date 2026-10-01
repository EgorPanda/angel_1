# 05. Система модулей и конфигурирование

## Базовый модуль

`app/core/module.py`, класс `Module`. Атрибуты класса:

| Атрибут | Описание |
|---------|----------|
| `name` | уникальное имя (напр. `notes`, `reminders`, `ai`) |
| `version` | семвер |
| `description`, `description_ru` | описание для UI |
| `dependencies` | имена модулей, от которых зависит |
| `capabilities` | списком строк (напр. `ai.chat`, `ai.tools`) |
| `enabled` | включён ли по умолчанию |
| `config_fields` | список `ConfigField` (форма настроек в UI) |

Экземплярные поля: `status`, `tools`, `routers`, `event_subscriptions`,
`core`.

## Lifecycle модуля

- `on_register(core)`: получает `core`, **регистрирует свои инструменты** в
  `core.tools`, **подписки** в `core.events`, и **роутер** в приложение
  (через `core.include_module_router`).
- `start()` / `stop()` / `restart()` (последовательность stop→start,
  при рестарте модуля через registry — reconfigure).
- `reconfigure()`: применяет сохранённую конфигурацию. У `ai` — пишет значения
  в `core.settings` и вызывает `core.reload_llm()`.
- `health_check()` → `(bool, detail)` — попадает в `/api/v1/system/health` под
  ключом `module:<name>`.
- `info()` — метаданные для `/api/v1/system/modules`.

## Конфигурация модуля (ConfigField + module_settings)

`app/core/module_config.py`:

- `ConfigField(key, label_ru, field_type, default, hint, options, value_type)`.
  - `field_type`: `text | password | number | bool | select`.
  - `value_type`: `str | int | float | bool`.
  - `cast(value)`: приведение к типу; устойчив к «двойному кодированию» строк
    (снимает лишние кавычки, см. `04-database.md` про JSON-столбец).
  - `options`: для select — список `{value, label}`.
- `Module.config_values()`: **дефолт поля** + сохранённое значение из
  `module_settings` (БД имеет приоритет), с `cast` по типу.
- `Module.save_config(values)`: сохраняет только заявленные поля, приводит к
  типам. `.env`/дефолты остаются как фолбэк.
- `ModuleConfigService`: `all(module)`, `set_many(module, values)`,
  `delete(module, key)`.

> Важно: сохранение конфигурации **не перезапускает** модуль само по себе.
> Применение происходит на restart (registry.restart → stop → reconfigure →
> start). В UI кнопки: «Сохранить (применить)» + «Перезапустить для применения»;
> в «Настройках» блок AI сам делает PUT config + POST restart.

## Реестр модулей

`app/core/registry.py`, `ModuleRegistry`:

- `register(module)`, `get(name)`, `require(name)`, `info()`, `statuses()`,
  `capabilities()`, `list()`.
- `start/stop/restart(name)`; `start_all()/stop_all()`.
- `restart`: гарантирует stop → reconfigure → start (пересборка под новую
  конфигурацию).

## Зарегистрированные модули (main.py)

| Модуль | Name | Конфигурируемые поля |
|--------|------|----------------------|
| Заметки | `notes` | (неконфигурируемый) |
| Напоминания | `reminders` | (неконфигурируемый) |
| Уведомления | `notifications` | (неконфигурируемый) |
| AI | `ai` | `llm_provider`, `llm_model`, `llm_api_url`, `llm_api_key`, `llm_temperature`, `llm_max_tokens`, `llm_timeout`, `llm_max_steps`, `llm_fallback_*` (см. `06`) |
| Markdown | `markdown` | `vault_path` (override), `enabled` |
| Telegram | `telegram` | `token`, `poll_interval`, `enabled` |

## Как добавить новый модуль (кратко)

1. Класс `Module` с `name`, `config_fields`, `tools`, `routers`,
   `event_subscriptions`.
2. Регистрация в `bootstrap_core` (`main.py`) до `core.start()`.
3. Опционально: HTTP-роутер (FastAPI APIRouter), инструменты для агента,
   подписка на события.
4. Тесты в `backend/tests/`, обновление документации (обязательно).
5. Если нужны поля в БД — новая Alembic-миграция.