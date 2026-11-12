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
    """Último estado conhecido da conta (somente leitura para plugins)."""

    level: int | None = None
    hunt_slug: str | None = None
    items: dict[str, int] | None = None


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
