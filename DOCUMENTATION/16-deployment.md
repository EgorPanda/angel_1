# 16. Развёртывание

## Локальное развёртывание (рекомендуемый путь)

Требования: Windows, Python 3.14, доступ в интернет для первого
`pip install`.

1. Положите проект в папку, например `E:\angel` (backend, frontend,
   start.bat, DOCUMENTATION).
2. Запустите **`E:\angel\start.bat`** двойным кликом. Он делает сам:
   - создаёт venv `backend\.venv`, если его нет;
   - устанавливает зависимости из `backend\requirements*.txt` (маркер
     `.venv\.deps_ok` — один раз; чтобы переустановить, удалите маркер);
   - применяет миграции БД: `alembic upgrade head`;
   - открывает браузер `http://127.0.0.1:8000`;
   - запускает `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
3. Окно консоли закрывать нельзя — это сервер (+ в нём линейка JSON-логов).

Стоп: закрыть окно (Ctrl+C). БД — `backend\angel.db` (файл, копируется как
резервная копия целиком).

### Вручную (для разработки)
```powershell
cd E:\angel\backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

## Подключение Ollama (локальный AI)

1. Установите **Ollama** (https://ollama.com) и запустите её (трей-иконка;
   слушает `http://localhost:11434`).
2. Скачайте модель, например:
   ```
   ollama pull llama3.2:latest
   ```
   (для качественного tool-calling хороши qwen2.5-инструкт-модели).
3. Проверьте: браузер → `http://localhost:11434` (или `ollama list`).
4. В интерфейсе Angel: «Настройки → AI и Ollama»:
   - провайдер: **Ollama (локально)**;
   - URL API: `http://localhost:11434/v1`;
   - модель: нажмите «Получить модели из Ollama», выберите установленную;
   - «Проверить подключение» — ожидайте «Подключение работает»;
   - «Сохранить» (модуль ai перезапустится автоматически).
5. Проверьте чат в «AI-чат» и здоровье в «Система → Здоровье» (`llm` — ok).

Внешний AI: провайдер `api`, заполняйте URL и `API-ключ`. Резервный провайдер
настраивается в «Система → Модули → ai» (поля `llm_fallback_*`).

## PostgreSQL (для продакшена)

1. Создайте БД и пользователя.
2. В `backend\.env`:
   ```
   ANGEL_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/angel
   ANGEL_APP_ENV=prod
   ANGEL_LOG_LEVEL=INFO
   ```
   (при необходимости добавьте `psycopg` в зависимости).
3. Примените миграции: `alembic upgrade head` (в `backend/`).
4. Запустите сервер (`uvicorn`/сервис). Для Windows-службы — `pywin32`/nssm
   или Task Scheduler; главное — держать процесс живым и включить автозапуск.

## Обновление (как обновлять после изменений кода)

1. Остановите сервер.
2. `git pull` (или скопируйте новые файлы).
3. Примените миграции: `alembic upgrade head`.
4. Запустите `start.bat`.
5. Если после обновления логи не пишутся — таблицы `log_records`,
   `module_settings` создадут недостающие элементы сами на старте
   (`create_all`); миграции нужны для согласованного прод-обновления.

## Резервное копирование и восстановление

- SQLite: скопируйте `backend\angel.db` (и папку vault). Восстановление —
  заменой файла + `alembic upgrade head`.
- Продакшен (PostgreSQL): стандартные `pg_dump`/`pg_restore`.
- Логи в БД: если не нужна история — «Статистика → Очистить по фильтру» или
  удалите записи старее N дней; retention автоматический (14 дней).

## Запуск без start.bat (например, в коде / для отладки)

```python
from app.main import app  # приложение-module для uvicorn
```
Или: `python -m uvicorn app.main:app`.

## Бонус: Open WebUI (веб-чат с локальными моделями)

Open WebUI — отдельный самохостящийся веб-интерфейс для общения с моделями
Ollama (и OpenAI-совместимыми API), хранит историю чатов. Дополняет Angel AI
(ручной чат; в Angel — агенты/инструменты).

Установка (выполненно однократно, Python 3.12 через uv, не трогает систему):
```powershell
# Python 3.12 управляется uv:
& E:\angel\backend\.venv\Scripts\uv.exe python install 3.12
& E:\angel\backend\.venv\Scripts\uv.exe venv --python 3.12 E:\angel\openwebui-env
& E:\angel\backend\.venv\Scripts\uv.exe pip install --python E:\angel\openwebui-env\Scripts\python.exe "open-webui==0.11.3"
```
Запуск: `E:\angel\openwebui-start.bat` (или вручную:
`E:\angel\openwebui-env\Scripts\open-webui.exe serve --host 127.0.0.1 --port 8080`).
UI: `http://127.0.0.1:8080`. Первый вход создаёт администратора; Open WebUI сам
находит Ollama на `127.0.0.1:11434` и показывает установленные модели
(у нас — `llama3.2:latest`). Порт 8080 не конфликтует с Angel (8000).
При первом старте сервер скачивает embedding-модель (RAG) — это нормально.
Проверка: `GET /health` → `{"status":true}`.

## Безопасность и эксплуатация

- Не открывать сервер в интернет без прокси+TLS и аутентификации
  (приложение рассчитано на локальное использование; доработайте аутентификацию
  перед публичным доступом).
- Токены (telegram, llm_api_key) не публикуйте; `.env` — в `.gitignore`.
- Следите за логами («Статистика»), особенно ERROR/CRITICAL.