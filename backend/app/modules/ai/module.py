from __future__ import annotations

import logging

from app.core.logging import get_logger
from app.core.module import Module
from app.core.module_config import ConfigField

logger = get_logger("modules.ai")


class AIModule(Module):
    name = "ai"
    version = "0.2.0"
    description = "AI reasoning runtime: agent loop, LLM providers and context."
    description_ru = "AI-рантайм: агент, провайдеры LLM и контекст."
    capabilities = ["ai.chat", "ai.tools", "ai.multistep", "ai.fallback"]

    PROVIDER_CHOICES = [
        {"value": "ollama", "label": "Ollama (локально, рекомендуется)"},
        {"value": "local", "label": "Local (OpenAI-совместимый)"},
        {"value": "api", "label": "API (OpenAI-совместимый HTTP)"},
    ]

    config_fields = [
        ConfigField("llm_provider", "Провайдер", field_type="select", default="ollama",
                    options=PROVIDER_CHOICES, hint="ollama — локальный эндпоинт Ollama, local — любой OpenAI-совместимый (напр. LM Studio), api — удалённый API"),
        ConfigField("llm_model", "Модель", default="qwen2.5:7b", hint="Имя модели у провайдера"),
        ConfigField("llm_api_url", "URL API", default="http://localhost:11434/v1", hint="Например http://localhost:11434/v1"),
        ConfigField("llm_api_key", "API-ключ", field_type="password", default="", hint="Оставьте пустым, если ключ не нужен"),
        ConfigField("llm_temperature", "Температура", field_type="number", default=0.3, value_type="float", hint="0.0 — детерминированно, 1.0 — креативно"),
        ConfigField("llm_max_tokens", "Макс. токенов", field_type="number", default=1024, value_type="int"),
        ConfigField("llm_timeout", "Таймаут (сек)", field_type="number", default=60.0, value_type="float"),
        ConfigField("llm_max_steps", "Макс. шагов агента", field_type="number", default=8, value_type="int"),
        ConfigField("llm_fallback_provider", "Резервный провайдер", field_type="select", default="",
                    options=[{"value": "", "label": "Выключен"}] + PROVIDER_CHOICES, hint="Используется при недоступности основного"),
        ConfigField("llm_fallback_api_url", "Резервный URL API", default=""),
        ConfigField("llm_fallback_api_key", "Резервный API-ключ", field_type="password", default=""),
        ConfigField("llm_fallback_model", "Резервная модель", default=""),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.runtime = None

    async def reconfigure(self) -> None:
        cfg = self.config_values()
        for key, value in cfg.items():
            setattr(self.core.settings, key, value)
        try:
            self.core.reload_llm()
            logger.info("ai module reconfigured: provider=%s model=%s", cfg.get("llm_provider"), cfg.get("llm_model"))
        except Exception:  # noqa: BLE001
            logger.exception("failed to rebuild LLM provider after config change")

    def health_check(self) -> tuple[bool, str]:
        if self.core is None or getattr(self.core, "ai_runtime", None) is None:
            return False, "runtime not initialized"
        return self.core.ai_runtime.health_check()

    def info(self) -> dict:
        data = super().info()
        if self.core is not None:
            data["provider"] = getattr(self.core.llm, "name", "none") if self.core.llm else "none"
        return data