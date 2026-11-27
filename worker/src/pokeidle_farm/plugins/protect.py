"""Plugin protect: espelha os pokémon protegidos na Coleção do jogo (épico C1).

Ver docs/design/protegidos-e-bosses.md. A regra de quem é protegido está em `protection.py`; os
comandos do painel (Depot, Coleção, equipe) leem a lista na hora. Este plugin cuida do resto: põe na
Coleção do jogo (`colecao.mover`) todo protegido firme (shiny ou marcado no painel) que está no Depot,
para que nenhuma venda do Depot leve (nem a nossa, nem a Auto Venda do próprio jogo).

- relê a lista marcada no painel (`protected_pokemon`) a cada `refresh_s`;
- manda no máximo uma marca a cada `mirror_every_s`, e não repete a mesma por `retry_min`;
- grava `protect.mirrored` (uma linha por marca mandada; raro: só quando aparece um shiny ou uma
  marca nova no painel).

Sempre ligado; `mirror: false` na config desliga o espelho (a regra nos comandos continua valendo).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, CollectionMove
from ..events import Event
from ..profile import ProfileState, set_travado
from ..protection import needs_mirror
from .base import Plugin, PluginContext


class ProtectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mirror: bool = True
    refresh_s: float = Field(60.0, ge=10)
    mirror_every_s: float = Field(20.0, ge=2)
    retry_min: float = Field(10.0, gt=0)


class ProtectPlugin(Plugin):
    name: ClassVar[str] = "protect"
    description: ClassVar[str] = (
        "Guarda na Coleção do jogo os pokémon protegidos (shiny e os marcados no painel)"
    )
    config_model: ClassVar[type[BaseModel]] = ProtectConfig
    subscribes: ClassVar[set[str]] = {"state.snapshot", "state.patch"}
    queue_size: ClassVar[int] = 5000
    always_on: ClassVar[bool] = True

    def __init__(self) -> None:
        self.profile = ProfileState()
        self.manual: set[int] | None = None  # None: ainda não leu (não espelha no escuro)
        self.clock = time.monotonic
        self.sleep = asyncio.sleep
        self._last_send = -1e9
        self._sent: dict[int, float] = {}
        self._timer: asyncio.Task[None] | None = None

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: ProtectConfig = ctx.config  # type: ignore[assignment]
        await self.refresh()
        self._timer = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer

    async def refresh(self) -> None:
        try:
            self.manual = await self.ctx.store.protected_pokemon(self.ctx.account_id)
        except Exception as exc:  # fica com a lista anterior
            self.ctx.log.warning("protect: falha ao ler protected_pokemon (%r)", exc)

    async def _loop(self) -> None:
        while True:
            await self.sleep(self.cfg.refresh_s)
            await self.refresh()
            await self.tick()

    async def on_event(self, event: Event) -> None:
        estado = event.raw.get("estado")
        if not isinstance(estado, dict):
            return
        if event.type == "state.snapshot":
            self.profile.apply_snapshot(estado)
        elif self.profile.ready:
            self.profile.apply_patch(estado)
        await self.tick()

    def pending(self) -> list[int]:
        """Protegidos firmes no Depot que ainda não pedimos (ou pedimos há mais de `retry_min`)."""
        if self.manual is None or not self.profile.ready:
            return []
        now = self.clock()
        wait = self.cfg.retry_min * 60
        todo = needs_mirror(self.profile.pokemons, self.manual, self.profile.collection_ids())
        return [pid for pid in todo if now - self._sent.get(pid, -1e9) >= wait]

    async def tick(self) -> None:
        if not self.cfg.mirror:
            return
        now = self.clock()
        if now - self._last_send < self.cfg.mirror_every_s:
            return
        todo = self.pending()
        if not todo:
            return
        pid = todo[0]
        mon = self.profile.pokemons.get(pid) or self.profile.pokemons.get(str(pid)) or {}
        self._last_send = now
        self._sent[pid] = now
        try:
            await self.ctx.actions.submit(
                CollectionMove(pokemon_id=pid, to="colecao"), source=self.name
            )
        except ActionBlocked as exc:
            self.ctx.log.info("protect: colecao.mover %s bloqueado (%s)", pid, exc.reason)
            return
        # vale já para quem manda a automation inteira (auto.set) e para a próxima conta da fila
        set_travado(self.ctx.state.automation, pid, True)
        self.profile.set_collection(pid, True)
        await self.ctx.actions.note("protect.mirrored", _about(pid, mon, self.manual or set()))


def _about(pid: int, mon: dict[str, Any], manual: set[int]) -> dict[str, Any]:
    return {
        "pokemon_id": pid,
        "species_id": mon.get("speciesId"),
        "name": mon.get("nome"),
        "reason": "shiny" if mon.get("shiny") else "manual" if pid in manual else None,
    }
