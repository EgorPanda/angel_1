from __future__ import annotations

from app.core.lifecycle import ModuleStatus


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, Any] = {}

    def register(self, module: Any) -> None:
        if module.name in self._modules:
            raise ValueError(f"module {module.name} already registered")
        self._modules[module.name] = module

    def unregister(self, name: str) -> None:
        self._modules.pop(name, None)

    def get(self, name: str):
        return self._modules.get(name)

    def require(self, name: str):
        module = self._modules.get(name)
        if module is None:
            raise KeyError(f"module {name} not found")
        return module

    def list(self) -> list:
        return list(self._modules.values())

    def capabilities(self) -> dict[str, list[str]]:
        return {mod.name: list(mod.capabilities) for mod in self._modules.values()}

    def statuses(self) -> dict[str, str]:
        return {mod.name: mod.status.value for mod in self._modules.values()}

    async def start(self, name: str) -> None:
        module = self.require(name)
        if module.status == ModuleStatus.RUNNING:
            return
        for dep in module.dependencies:
            if dep in self._modules:
                await self.start(dep)
        module.status = ModuleStatus.STARTING
        try:
            await module.start()
        except Exception:  # noqa: BLE001
            module.status = ModuleStatus.ERROR
            raise

    async def stop(self, name: str) -> None:
        module = self.require(name)
        module.status = ModuleStatus.STOPPING
        try:
            await module.stop()
        except Exception:  # noqa: BLE001
            module.status = ModuleStatus.ERROR
            raise

    async def restart(self, name: str) -> None:
        module = self.require(name)
        module.status = ModuleStatus.STOPPING
        try:
            await module.stop()
            await module.reconfigure()
        except Exception:  # noqa: BLE001
            module.status = ModuleStatus.ERROR
            raise
        module.status = ModuleStatus.STARTING
        try:
            await module.start()
        except Exception:  # noqa: BLE001
            module.status = ModuleStatus.ERROR
            raise

    def status(self, name: str) -> str:
        return self.require(name).status.value

    async def start_all(self) -> None:
        for module in self._modules.values():
            await self.start(module.name)

    async def stop_all(self) -> None:
        for module in reversed(list(self._modules.values())):
            await self.stop(module.name)

    def info(self) -> list[dict]:
        return [
            {
                "name": mod.name,
                "version": mod.version,
                "description": mod.description,
                "description_ru": getattr(mod, "description_ru", "") or mod.description,
                "dependencies": list(mod.dependencies),
                "capabilities": list(mod.capabilities),
                "status": mod.status.value,
                "enabled": mod.enabled,
                "config_fields": [f.to_dict() for f in getattr(mod, "config_fields", [])],
                "config_values": mod.config_values() if mod.core is not None else {},
            }
            for mod in self._modules.values()
        ]