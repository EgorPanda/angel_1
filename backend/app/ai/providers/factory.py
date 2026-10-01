from __future__ import annotations

from functools import lru_cache

from app.ai.providers.base import LLMProvider
from app.ai.providers.fallback import FallbackProvider
from app.ai.providers.http import HttpProvider
from app.ai.providers.local import LocalProvider
from app.config import get_settings


def build_provider(settings=None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "api":
        primary: LLMProvider = HttpProvider(
            api_url=settings.llm_api_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )
    else:
        primary = LocalProvider(api_url=settings.llm_api_url, model=settings.llm_model, timeout=settings.llm_timeout)
    if settings.llm_fallback_provider:
        if settings.llm_fallback_provider == "api":
            fallback = HttpProvider(
                api_url=settings.llm_fallback_api_url or settings.llm_api_url,
                api_key=settings.llm_fallback_api_key,
                model=settings.llm_fallback_model or settings.llm_model,
                timeout=settings.llm_timeout,
            )
        else:
            fallback = LocalProvider(
                api_url=settings.llm_fallback_api_url or settings.llm_api_url,
                model=settings.llm_fallback_model or settings.llm_model,
                timeout=settings.llm_timeout,
            )
        return FallbackProvider(primary, fallback)
    return primary


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider()