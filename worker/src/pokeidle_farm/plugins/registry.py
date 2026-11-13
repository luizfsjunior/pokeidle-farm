"""Descoberta e ciclo de vida dos plugins de uma sessão."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

from pydantic import ValidationError

from ..bus import EventBus, Unsubscribe
from .base import Plugin, PluginContext

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "pokeidle_farm.plugins"


def discover() -> dict[str, type[Plugin]]:
    """Plugins registrados por entry point (inclui os nativos)."""
    found: dict[str, type[Plugin]] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            cls = ep.load()
        except Exception:
            log.exception("plugin %s: falha ao carregar", ep.name)
            continue
        if isinstance(cls, type) and issubclass(cls, Plugin):
            found[cls.name] = cls
    return found


class PluginHost:
    """Sobe e para os plugins de uma conta."""

    def __init__(self, available: dict[str, type[Plugin]]) -> None:
        self.available = available
        self.running: dict[str, Plugin] = {}
        self.degraded: dict[str, str] = {}
        self._unsubs: dict[str, Unsubscribe] = {}

    async def start_all(
        self,
        bus: EventBus,
        configs: dict[str, tuple[bool, dict[str, Any]]],
        make_ctx: Any,  # Callable[[type[Plugin], BaseModel], PluginContext]
        *,
        only_always_on: bool = False,
    ) -> None:
        """Sobe os plugins ligados que ainda não estão rodando (idempotente)."""
        for name, cls in self.available.items():
            if name in self.running or (only_always_on and not cls.always_on):
                continue
            enabled, raw_cfg = configs.get(name, (cls.always_on, {}))
            if not (enabled or cls.always_on):
                continue
            try:
                cfg = cls.config_model.model_validate(raw_cfg)
            except ValidationError as exc:
                self.degraded[name] = f"config inválida: {exc.error_count()} erro(s)"
                log.error("plugin %s desligado: config inválida\n%s", name, exc)
                continue
            plugin = cls()
            ctx: PluginContext = make_ctx(cls, cfg)
            try:
                await plugin.start(ctx)
            except Exception as exc:
                self.degraded[name] = f"falha ao iniciar: {exc!r}"
                log.exception("plugin %s: falha ao iniciar", name)
                continue
            self._unsubs[name] = bus.subscribe(
                f"{ctx.nick}:{name}",
                cls.subscribes,
                plugin.on_event,
                exclude=cls.excludes,
                maxsize=cls.queue_size,
            )
            self.running[name] = plugin
            log.info("[%s] plugin %s iniciado", ctx.nick, name)

    def mark_degraded(self, subscriber: str, exc: BaseException) -> None:
        name = subscriber.split(":", 1)[-1]
        self.degraded[name] = repr(exc)

    async def stop_one(self, name: str) -> None:
        unsub = self._unsubs.pop(name, None)
        plugin = self.running.pop(name, None)
        self.degraded.pop(name, None)
        if unsub is not None:
            await unsub()
        if plugin is not None:
            try:
                await plugin.stop()
            except Exception:
                log.exception("plugin %s: falha ao parar", name)

    async def stop_all(self) -> None:
        for name, unsub in list(self._unsubs.items()):
            await unsub()  # drena a fila antes de parar
            try:
                await self.running[name].stop()
            except Exception:
                log.exception("plugin %s: falha ao parar", name)
        self._unsubs.clear()
        self.running.clear()
