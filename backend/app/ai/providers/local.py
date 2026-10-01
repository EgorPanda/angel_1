from app.ai.providers.http import HttpProvider


class LocalProvider(HttpProvider):
    name = "local"

    def __init__(self, api_url: str = "http://localhost:11434/v1", model: str = "default",
                 timeout: float = 60.0) -> None:
        super().__init__(api_url=api_url, api_key="", model=model, timeout=timeout)