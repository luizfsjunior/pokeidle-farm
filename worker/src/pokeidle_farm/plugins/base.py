"""Interface de plugin (ver docs/design/fase-2.md, seção 2).

Regras:
- Plugins não falam com o WebSocket; ações só pelo `ctx.actions`.
- A config é validada pelo `config_model`; config inválida desliga o plugin.
- Um plugin novo é um módulo mais uma linha em [project.entry-points] do
  pyproject.toml.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel

from ..actions import ActionGateway
from ..bus import EventBus
from ..events import Event
from ..store.base import Store


class EmptyConfig(BaseModel):
    pass


@dataclass
class AccountStateView:
    """Último estado conhecido da conta (somente leitura para plugins).

    A sessão chama `apply` com cada evento antes de publicá-lo, então um plugin
    que recebe um `state.patch` já enxerga o estado atualizado.
    """

    level: int | None = None
    hunt_slug: str | None = None
    items: dict[str, int] | None = None
    balls: dict[str, int] | None = None
    gold: int | None = None
    automation: dict[str, Any] | None = None
    # trava de combate (estado.centroLivreEm) e intervalo entre trocas (trocaLivreEm),
    # no relógio do servidor; a sessão copia o server_offset do tradutor
    combat_free_at: datetime | None = None
    switch_free_at: datetime | None = None
    server_offset: timedelta | None = None  # servidor − local
    active_level: int | None = None  # nível do pokémon ativo (do último abate)

    def server_now(self, now: datetime | None = None) -> datetime:
        """Relógio do servidor (o local, se o offset ainda não é conhecido)."""
        now = now or datetime.now(UTC)
        return now + self.server_offset if self.server_offset is not None else now

    def apply(self, event: Event) -> None:
        d = event.data
        if event.type == "kill":
            if isinstance(d.get("active_level"), int):
                self.active_level = d["active_level"]
            return
        if event.type == "hunt.changed":
            free = _as_datetime(d.get("switch_free_at"))
            if free is not None:
                self.switch_free_at = free
            return
        if event.type not in ("state.snapshot", "state.patch"):
            return
        lock = d.get("centro_livre_em")
        if isinstance(lock, int | float):
            self.combat_free_at = datetime.fromtimestamp(lock / 1000, UTC)
        for name in ("level", "hunt_slug", "gold", "automation"):
            if d.get(name) is not None:
                setattr(self, name, d[name])
        # bolas e itens: merge, porque um patch pode trazer só parte do mapa
        for name in ("items", "balls"):
            if isinstance(d.get(name), dict):
                setattr(self, name, {**(getattr(self, name) or {}), **d[name]})


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


@dataclass
class PluginContext:
    account_id: UUID
    nick: str
    config: BaseModel
    bus: EventBus
    actions: ActionGateway
    state: AccountStateView
    store: Store
    settings: Any
    log: logging.Logger
    catalog: Any = None  # HuntCatalog do último welcome (fase 3b)
    species: Any = None  # SpeciesCatalog (Pokedex), compartilhado pelo worker


class Plugin(ABC):
    name: ClassVar[str]
    description: ClassVar[str] = ""
    config_model: ClassVar[type[BaseModel]] = EmptyConfig
    subscribes: ClassVar[set[str] | Literal["*"]] = "*"
    excludes: ClassVar[set[str]] = set()
    queue_size: ClassVar[int] = 1000
    # Plugins "core" sobem sempre; os outros só se ligados em strategy_configs.
    always_on: ClassVar[bool] = False

    ctx: PluginContext

    async def start(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    @abstractmethod
    async def on_event(self, event: Event) -> None: ...

    async def stop(self) -> None:  # noqa: B027 - opcional para subclasses
        pass
