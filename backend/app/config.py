from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ANGEL_", extra="ignore")

    app_name: str = "Angel AI"
    app_env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./angel.db"
    default_user_username: str = "angel"

    telegram_bot_token: str = ""
    telegram_poll_interval: float = 2.0

    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_api_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024
    llm_timeout: float = 60.0
    llm_max_steps: int = 8
    llm_fallback_provider: str = ""
    llm_fallback_api_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""

    markdown_vault_path: str = "../vault"
    markdown_enabled: bool = True

    scheduler_interval: float = 5.0
    worker_concurrency: int = 2
    worker_retry_attempts: int = 3
    task_enqueue_interval: float = 5.0

    confirmation_ttl_seconds: int = 300

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def vault_path(self) -> str:
        import os

        if os.path.isabs(self.markdown_vault_path):
            return self.markdown_vault_path
        return str(os.path.abspath(self.markdown_vault_path))


@lru_cache
def get_settings() -> Settings:
    return Settings()