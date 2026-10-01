from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger("core.module_config")


class ConfigField:
    """Описание поля конфигурации модуля."""

    def __init__(self, key: str, label_ru: str, field_type: str = "text", default=None,
                 hint: str = "", options: list[dict] | None = None, value_type: str = "str") -> None:
        self.key = key
        self.label_ru = label_ru
        self.field_type = field_type  # text | password | number | bool | select
        self.default = default
        self.hint = hint
        self.options = options or []
        self.value_type = value_type  # str | int | float | bool

    def cast(self, value):
        if value is None:
            return value
        if self.value_type == "int":
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
        if self.value_type == "float":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        if self.value_type == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on", "да")
        if isinstance(value, str) and value.startswith('"') and value.endswith('"') and len(value) >= 2:
            try:
                import json

                return json.loads(value)
            except ValueError:
                pass
        return str(value) if value != "" else ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label_ru": self.label_ru,
            "field_type": self.field_type,
            "default": self.default,
            "hint": self.hint,
            "options": self.options,
            "value_type": self.value_type,
        }


class ModuleConfigService:
    """Хранилище конфигурации модулей (поверх .env / дефолтов)."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def all(self, module: str) -> dict:
        from sqlalchemy import select

        from app.core.models import ModuleSetting

        session = self._sf()
        try:
            rows = session.execute(
                select(ModuleSetting).where(ModuleSetting.module == module)
            ).scalars().all()
            return {r.key: r.value for r in rows}
        finally:
            session.close()

    def set_many(self, module: str, values: dict) -> None:
        from sqlalchemy import select

        from app.core.models import ModuleSetting

        session = self._sf()
        try:
            for key, value in values.items():
                row = session.execute(
                    select(ModuleSetting).where(
                        ModuleSetting.module == module, ModuleSetting.key == key
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = ModuleSetting(module=module, key=key, value=value)
                    session.add(row)
                else:
                    row.value = value
            session.commit()
        finally:
            session.close()

    def delete(self, module: str, key: str | None = None) -> None:
        from sqlalchemy import delete, select

        from app.core.models import ModuleSetting

        session = self._sf()
        try:
            stmt = delete(ModuleSetting).where(ModuleSetting.module == module)
            if key is not None:
                stmt = stmt.where(ModuleSetting.key == key)
            session.execute(stmt)
            session.commit()
        finally:
            session.close()