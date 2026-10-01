# 17. Руководство разработчика

## Окружение

```powershell
cd E:\angel\backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q        # тесты (эталон 61 passed)
.venv\Scripts\python -m alembic upgrade head   # миграции
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

## Как добавить модуль

1. Папка `app/modules/<name>/` (или `app/interfaces/...` для интеграций).
2. Класс `Module` (наследовать `app.core.module.Module`):
   - `name`, `version`, `description(_ru)`, `capabilities`;
   - `config_fields` — форма настроек;
   - `tools = [Tool(...)]`, `routers = [APIRouter(...)]`,
     `event_subscriptions = {...}` (всё подхватывается в `on_register`).
   - реализовать `start/stop/reconfigure/health_check`.
3. Зарегистрировать в `bootstrap_core` (main.py) до `core.start()`.
4. Если нужна новая таблица — модель + Alembic-миграция.
5. Тесты: `tests/test_<name>.py` (fixture `core` из conftest).
6. Запустить `pytest`, обновить `DOCUMENTATION/*` (обязательно!).

## Как добавить инструмент агента

1. Класс `Tool`: `name`, `description`, `permission` (`module.action`),
   `default_mode`, при желании `input_schema` (pydantic), `async run(...)`.
2. В `module.tools` добавить экземпляр → инструмент попадёт в агент и в
   `/system/permissions`.
3. По умолчанию режим `ALLOW`; для «спрашивать человека» — предложить
   `CONFIRM` в UI/логах.
4. Документировать: новый инструмент, permission, описание — в `07-*`.

## Как добавить HTTP-эндпоинт

- Системный роутер: `app/api/system.py` (внутри `build_router(core)`) — для
  инфраструктуры.
- Модульный роутер: в `module.routers` (APIRouter своего модуля).
- Соглашения: параметры через запрос/пейлоад, сессии через
  `core.session_factory()`, JSON-ответ, HTTPException с русским сообщением,
  углой обработкой ошибок — `AngelError`.
- Обновить `11-api.md` и `14-logging.md` (если новый экран).

## Как добавить настройку модуля

- `ConfigField(key, label_ru, field_type, default, hint, options, value_type)`.
- `save_config(values)` автоматически сохранит в `module_settings`.
- Применение — в `reconfigure()` (или на restart).
- Обновить `05-*`/`06-*`/`13-configuration.md`.

## Как работать с логами в коде

```python
from app.core.logging import get_logger, log_extra
logger = get_logger("mymodule")
logger.info("делаю что-то", extra=log_extra({"key": "value"}))
logger.warning("предупреждение")
logger.error("ошибка: %s", exc, exc_info=True)   # трейс попадёт в log_records
```
- Не логируйте пароли/токены.
- `correlation_id`/`request_id` подставляются автоматически для HTTP-запросов.

## Как добавить фон-задачу/план

- Обработчик пула: зарегистрировать в `WorkersModuleConnector`
  (`process_reminder`, `sync_markdown` — примеры).
- Планировщик сам тикает и ставит задачи; смотрите `scheduler.py`.

## Миграции

```powershell
.venv\Scripts\python -m alembic revision --autogenerate -m "описание"
# проверить сгенерированный файл (учесть конфликты с create_all), затем:
.venv\Scripts\python -m alembic upgrade head
```
Для новой таблицы существующей БД добавляйте с guard-проверкой
(`if "name" in inspector.get_table_names(): return`), как в миграции
`365e95b1cf71` (add log_records).

## Правила ревью и качества

- Все тесты зелёные (`pytest -q`).
- Нет секретов в коде/гит.
- **Документация обновлена** (см. AGENTS.md): эндпоинты, таблицы, поля
  конфигурации, инструменты, `.env`, разделы UI, шаги развёртывания.
- Согласованный стиль: русские сообщения UI и HTTPError, `log_extra` для
  контекста, UTC-время в БД.

## Типичные ловушки

- Забыл зарегистрировать модуль в bootstrap → роутер/инструменты не видны.
- Менял схему БД без миграции → падает prod-обновление.
- Хранил строку в `module_settings` не через ORM → ломается JSON-столбец.
- `llm_model` не совпадает с установленной в Ollama → HTTP 404 на
  `/v1/chat/completions` (лечится выбором модели в «Настройки»).
- Редактировал ячейку `log_records`/`module_settings` вручную (SQLite-raw) →
  битый JSON; править только через приложение.