"""Plugin evolve: evolui o pokémon ativo quando chega o nível e a pedra do tipo está na bolsa.

Sempre ligado, em qualquer foco (antes só o foco XP evoluía, e uma conta no foco gemas ficava com o
inicial parado na primeira forma; 17/11). A regra e a confirmação são as do `Progress`
(docs/design/simulador-2-progressao.md): uma tentativa por pokémon e espécie a cada 10 min,
`progress.evolve` ao pedir, `progress.evolved` ou `progress.evolve_failed` depois.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from ..events import Event
from ..progress import Progress
from .base import Plugin, PluginContext


class EvolveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool = True  # false: não evolui sozinho (o plugin sobe sempre)


class EvolvePlugin(Plugin):
    name: ClassVar[str] = "evolve"
    description: ClassVar[str] = "Evolui o pokémon ativo quando há nível e pedra, em qualquer foco"
    config_model: ClassVar[type[BaseModel]] = EvolveConfig
    subscribes: ClassVar[set[str]] = {"kill", "state.snapshot", "state.patch"}
    always_on: ClassVar[bool] = True

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: EvolveConfig = ctx.config  # type: ignore[assignment]
        self.progress = Progress(ctx, source=self.name, now=lambda: self.now())

    async def on_event(self, event: Event) -> None:
        if not self.cfg.active or self.ctx.species is None:
            return
        await self.progress.maybe_evolve()
