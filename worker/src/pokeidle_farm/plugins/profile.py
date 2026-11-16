"""Plugin profile: mantém o perfil da conta em `account_profile`, para o painel.

Ver docs/design/painel-perfil.md. Junta o welcome e os patches (`profile.ProfileState`) e grava
uma linha por conta a cada `interval_s`, só se algo mudou. Não manda nada ao jogo.
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
            self.profile.apply_patch(estado)
            self.dirty = True

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

    async def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer
        await self.flush()

    async def _loop(self) -> None:
        while True:
            await self.sleep(self.cfg.interval_s)
            await self.flush()
