"""Plugin profile: mantém o perfil da conta em `account_profile`, para o painel.

Ver docs/design/painel-perfil.md. Junta o welcome e os patches (`profile.ProfileState`) e grava
uma linha por conta a cada `interval_s`, só se algo mudou. Não manda nada ao jogo.

O que o painel muda (pokémon ativo, equipe, hunt) vai para o banco em `quick_s`, sem esperar o
intervalo: o painel recebe a mudança pelo Realtime e a tela acompanha em segundos.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..events import Event
from ..profile import ProfileState
from .base import Plugin, PluginContext


class ProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_s: float = Field(120.0, ge=10)
    quick_s: float = Field(2.0, ge=0.5, le=30)


def quick_view(profile: ProfileState) -> tuple[object, ...]:
    """O que o painel pede para ver logo (docs/design/tela-na-hora.md): o ativo, a hunt e a equipe.

    Compara-se o antes e o depois do patch, não a presença das chaves: o jogo manda a cada abate um
    patch com o pokémon ativo completo no `pkMud` (com `slot`), e gravar em `quick_s` a cada abate
    era ~1 gravação a cada 3 s por conta em account_profile e account_pokemon (23/11).
    """
    team = frozenset(
        (pid, p["slot"]) for pid, p in profile.pokemons.items() if p.get("slot") is not None
    )
    return (profile.estado.get("activeId"), profile.estado.get("huntSlug"), team)


class ProfilePlugin(Plugin):
    name: ClassVar[str] = "profile"
    description: ClassVar[str] = (
        "Grava o perfil da conta (nível, moedas, equipe, coleção) para o painel"
    )
    config_model: ClassVar[type[BaseModel]] = ProfileConfig
    subscribes: ClassVar[set[str]] = {"state.snapshot", "state.patch"}
    queue_size: ClassVar[int] = 5000
    always_on: ClassVar[bool] = True

    def __init__(self) -> None:
        self.profile = ProfileState()
        self.dirty = False
        self.sleep = asyncio.sleep  # trocado nos testes
        self._timer: asyncio.Task[None] | None = None
        self._soon: asyncio.Task[None] | None = None

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: ProfileConfig = ctx.config  # type: ignore[assignment]
        self._timer = asyncio.create_task(self._loop())

    async def on_event(self, event: Event) -> None:
        estado = event.raw.get("estado")
        if not isinstance(estado, dict):
            return
        if event.type == "state.snapshot":
            first = not self.profile.ready
            self.profile.apply_snapshot(estado)
            self.dirty = True
            if first:
                await self.flush()  # o painel não espera o primeiro intervalo
            return
        if self.profile.ready:
            before = quick_view(self.profile)
            self.profile.apply_patch(estado)
            self.dirty = True
            quick = "pkFora" in estado or quick_view(self.profile) != before
            if quick and (self._soon is None or self._soon.done()):
                self._soon = asyncio.create_task(self._flush_soon())

    async def _flush_soon(self) -> None:
        # junta os patches de uma mesma troca (o jogo manda vários em sequência)
        await self.sleep(self.cfg.quick_s)
        await self.flush()

    async def flush(self) -> None:
        if not self.dirty or not self.profile.ready:
            return
        self.dirty = False
        row = {"account_id": str(self.ctx.account_id), **self.profile.summary()}
        try:
            await self.ctx.store.upsert_account_profile(row)
        except Exception as exc:
            self.dirty = True  # tenta de novo no próximo intervalo
            self.ctx.log.warning("profile: falha ao gravar o perfil (%r)", exc)
        await self._sync_collection()

    async def _sync_collection(self) -> None:
        """Só os pokémons que mudaram (ou tudo, depois do welcome) em account_pokemon."""
        rows, removed, full = self.profile.collection_rows(str(self.ctx.account_id))
        if not rows and not removed and not full:
            return
        sync = getattr(self.ctx.store, "sync_account_pokemon", None)
        if sync is None:
            return
        try:
            await sync(self.ctx.account_id, rows, removed, full=full)
        except Exception as exc:
            self.profile.requeue(rows, removed, full)
            self.dirty = True
            self.ctx.log.warning("profile: falha ao gravar a coleção (%r)", exc)

    async def stop(self) -> None:
        for task in (self._timer, self._soon):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await self.flush()

    async def _loop(self) -> None:
        while True:
            await self.sleep(self.cfg.interval_s)
            await self.flush()
