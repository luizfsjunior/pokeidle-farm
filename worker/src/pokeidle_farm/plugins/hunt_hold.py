"""Plugin hunt_hold: a hunt escolhida pelo painel, travada por um tempo.

Ver docs/design/painel-fase-3.md. Ligado pelo comando `hunt.select` (config `slug` e `until`):
- trava o `hunt.select` dos outros plugins no ActionGateway até `until` (gems e rank recebem
  ActionBlocked com wait_s e tentam de novo quando a trava acaba);
- troca para a hunt pelo HuntSwitcher (trava de combate, trocaLivreEm, confirmação, nova tentativa);
- no fim do prazo, solta a trava e grava `hunt_hold.ended`; os outros plugins voltam a escolher.

O comando `hunt.release` desliga o plugin, o que solta a trava na hora.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..events import Event
from ..hunt_switch import HuntSwitcher
from .base import Plugin, PluginContext


class HuntHoldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=64)
    until: datetime


class HuntHoldPlugin(Plugin):
    name: ClassVar[str] = "hunt_hold"
    description: ClassVar[str] = (
        "Fica na hunt escolhida pelo painel até o prazo (os outros não trocam)"
    )
    config_model: ClassVar[type[BaseModel]] = HuntHoldConfig
    subscribes: ClassVar[set[str]] = {"hunt.changed", "game.error", "kill"}

    def __init__(self) -> None:
        self.now: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
        self._lock = asyncio.Lock()
        self._timer: asyncio.Task[None] | None = None
        self.active = False

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: HuntHoldConfig = ctx.config  # type: ignore[assignment]
        until = self.cfg.until if self.cfg.until.tzinfo else self.cfg.until.replace(tzinfo=UTC)
        self.until = until
        if until <= self.now():
            await ctx.actions.note("hunt_hold.ended", {"slug": self.cfg.slug, "reason": "expired"})
            return
        self.active = True
        ctx.actions.hold_hunt(self.cfg.slug, until, self.name)
        self.switch = HuntSwitcher(
            ctx,
            source=self.name,
            now=lambda: self.now(),
            sleep=lambda s: self.sleep(s),
            locked=self._locked,
        )
        await ctx.actions.note(
            "hunt_hold.started", {"slug": self.cfg.slug, "until": until.isoformat()}
        )
        self._timer = asyncio.create_task(self._expire())
        await self._locked(lambda: self.switch.go(self.cfg.slug))

    async def _locked(self, fn: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            await fn()

    async def on_event(self, event: Event) -> None:
        if not self.active:
            return
        d = event.data
        if event.type == "hunt.changed":
            await self._locked(lambda: self.switch.on_hunt_changed(d.get("slug")))
        elif event.type == "game.error":
            await self._locked(lambda: self.switch.on_error(str(d.get("key") or "erro")))
        else:
            await self._locked(self.switch.pump)

    async def _expire(self) -> None:
        await self.sleep(max(0.0, (self.until - self.now()).total_seconds()))
        await self._release("expired")

    async def _release(self, reason: str) -> None:
        if not self.active:
            return
        self.active = False
        self.ctx.actions.release_hunt(self.name)
        await self.ctx.actions.note("hunt_hold.ended", {"slug": self.cfg.slug, "reason": reason})

    async def stop(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer
        await self._release("stopped")
