# Angel AI — Инструменты (Tools)

Инструменты — единственный способ, которым AI влияет на систему. Реализация: `app/core/tools.py`.

## Определение инструмента
```python
class CreateNoteTool(NotesTool):
    name = "create_note"
    description = "Создаёт заметку"
    permission = "notes.create"
    default_mode = PermissionMode.ALLOW
    input_schema = NotesCreateSchema

    async def run(self, validated, ctx):
        ...
        return {"id": str(note.id), "title": note.title}
```
- `run` получает провалидированные аргументы и `ToolContext(user_id, correlation_id, task_id, core)`.
- `ToolRegistry` собирает инструменты всех модулей в `core.tools`.

## Каталог (19 шт.)

### Notes (12)
| Инструмент | Permission | Default | Действие |
|---|---|---|---|
| `create_note` | notes.create | allow | создание заметки (+теги) |
| `get_note` | notes.read | allow | получение заметки с деталями |
| `update_note` | notes.update | allow | обновление полей/иерархии/тегов |
| `delete_note` | notes.delete | confirm | удаление заметки |
| `search_notes` | notes.read | allow | поиск по тексту/категории/тегу |
| `list_notes` | notes.read | allow | список по папке/родителю |
| `create_folder` | notes.create | allow | создать папку |
| `update_folder` | notes.update | allow | переименовать/переместить |
| `delete_folder` | notes.delete | confirm | удалить папку (возврат заметок к родителю) |
| `create_category` | notes.create | allow | создать категорию |
| `rename_category` | notes.update | allow | переименовать |
| `delete_category` | notes.delete | confirm | удалить категорию |

### Reminders (5)
| Инструмент | Permission | Default | Действие |
|---|---|---|---|
| `create_reminder` | reminders.create | allow | создать напоминание (повторения, tz) |
| `update_reminder` | reminders.update | allow | изменить |
| `delete_reminder` | reminders.delete | confirm | удалить |
| `cancel_reminder` | reminders.update | allow | отменить |
| `list_reminders` | reminders.read | allow | список по статусу/диапазону |

### Notifications (2)
| Инструмент | Permission | Default | Действие |
|---|---|---|---|
| `send_notification` | notifications.send | confirm | отправить уведомление пользователю |
| `send_reminder_notification` | notifications.send | allow | служебное уведомление напоминания |

## Выполнение (`Tool.execute`)
1. Валидация аргументов через `input_schema` (pydantic) + `extra` контроль.
2. `core.permissions.request(permission, ..., default_mode)`:
   - `allow` → выполнение;
   - `confirm` → если есть approved-подтверждение с тем же `params_hash` → выполнение (подтверждение расходится);
   - иначе → `ToolResult.needs_confirmation=True` + `confirmation_id`;
   - `forbid` → `PermissionDenied`.
3. Бизнес-операция в `run()`, результат оборачивается в `ToolResult(success, data, ...)`.
4. Ошибки: `ValidationError` (некорректные аргументы), `ToolExecutionError` (сбой сервиса) —
   возвращаются модели как обычный tool result, цикл продолжается.

## ToolContext
`user_id`, `correlation_id`, `task_id`, `core` — используется для аудита и обращений к сервисам.