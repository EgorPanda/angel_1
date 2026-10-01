from __future__ import annotations

import time
from typing import Callable


class HealthChecker:
    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], tuple[bool, str]]] = {}

    def register(self, name: str, check: Callable[[], tuple[bool, str]]) -> None:
        self._checks[name] = check

    def unregister(self, name: str) -> None:
        self._checks.pop(name, None)

    def snapshot(self) -> dict:
        started = time.monotonic()
        result = {}
        for name, check in self._checks.items():
            try:
                ok, detail = check()
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            result[name] = {"ok": ok, "detail": detail}
        result["_checked_ms"] = int((time.monotonic() - started) * 1000)
        return result

    @property
    def healthy(self) -> bool:
        return all(entry["ok"] for key, entry in self.snapshot().items() if not key.startswith("_"))