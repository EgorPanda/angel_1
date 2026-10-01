# Angel AI — Markdown Vault (проекция)

`app/markdown/sync.py`. Vault — утилитарная проекция для Obsidian; **не источник правды**.

## Принцип
Полная перестройка vault из БД без потерь возможна всегда (`full_sync`). Файлы сверяются через
манифест `_angel_manifest.json` (список управляемых `.md`); при `full_sync` управляемые файлы
удаляются и пересоздаются, пустые подпапки чистятся.

## Структура файла заметки
```markdown
---
id: <uuid>            # главный ключ (по нему ищется файл)
title: ...
category: ...
tags: [a, b]
importance: high
created_at: ...
updated_at: ...
parent_id: ...
---
<content>
```
Имя файла — slug заголовка (`_slug`), при коллизии добавляется префикс id (`<title>-<id8>.md`).
Вложенность по папкам: `vault/<Папка>/<Подпапка>/...`.

## Индексы
- `vault/_Index.md` — корневой индекс: папки `[[name|name/]]` и корневые заметки `[[title|title]]`.
- `vault/<folder>/_Index.md` — индекс папки: подпапки и заметки папки (wikilinks).

## Операции
| Метод | Действие |
|---|---|
| `full_sync()` | пересоздаёт всё, возвращает `{synced, deleted, disabled}` |
| `sync_note(id)` | пишет/обновляет файл заметки + индексы |
| `delete_note(id)` | ищет файл по frontmatter `id:` и удаляет + пересобирает индексы |
| `sync_folder(id)` | полная пересборка (после изменений в папке) |

## Интеграция
- `MarkdownModule` подписан на события notes (`note_created/updated/deleted`, `folder_*`) и
  enqueue в воркер задачи `sync_markdown`.
- При старте модуля выполняется `full_sync`.
- `POST /api/v1/markdown/sync` — ручной `full_sync` (ответ включает отчёт).

## Настройка
- `ANGEL_MARKDOWN_VAULT_PATH` (по умолчанию `../vault`), `ANGEL_MARKDOWN_ENABLED=true|false`.