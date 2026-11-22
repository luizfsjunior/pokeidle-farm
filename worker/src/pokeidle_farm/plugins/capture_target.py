"""Plugin capture_target: capturar uma espécie escolhida no painel (docs/design/captura-alvo.md).

Cada hunt tem uma espécie principal, então "capturar o X" é:
- ir para a hunt do X e travar a troca de hunt (os plugins gems e rank esperam);
- publicar o alvo em `state.capture`: o ball_thrower joga a bola em todo corpo do X. A bola automática do
  jogo exige VIP e fica desligada (docs/design/captura-manual.md);
- repor a bola escolhida com ouro, sem passar da reserva;
- contar as capturas da espécie (`pokemon.captured`) desde o início.

Termina no que vier primeiro entre `count` capturas e o prazo `until`; sem os dois, só pelo comando
`capture.stop`. No fim, tira o alvo, solta as travas, grava `capture_target.ended` e desliga a própria
config (os outros plugins voltam a decidir).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, AutoSet, ShopBuy
from ..catalog import BALL_ORDER, BALLS
from ..events import Event
from ..hunt_switch import HuntSwitcher
from .base import Plugin, PluginContext

FOREVER = timedelta(days=365)


class CaptureTargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    species_id: int
    species_name: str | None = None
    hunt_slug: str = Field(min_length=1, max_length=64)
    ball_id: int | None = None  # None: a que vale a pena (state.worth_ball)
    count: int | None = Field(None, ge=1, le=10_000)  # para depois de N capturas da espécie
    until: datetime | None = None  # ou no prazo; sem os dois, só pelo capture.stop
    started_at: datetime
    ball_min: int = Field(30, ge=0)
    ball_buy: int = Field(200, ge=1)
    gold_reserve: int = Field(5_000, ge=0)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class CaptureTargetPlugin(Plugin):
    name: ClassVar[str] = "capture_target"
    description: ClassVar[str] = (
        "Captura a espécie escolhida no painel (hunt dela + bola até capturar)"
    )
    config_model: ClassVar[type[BaseModel]] = CaptureTargetConfig
    subscribes: ClassVar[set[str]] = {
        "kill",
        "hunt.changed",
        "game.error",
        "pokemon.captured",
        "state.patch",
    }

    def __init__(self) -> None:
        self.now: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
        self._lock = asyncio.Lock()
        self._timer: asyncio.Task[None] | None = None
        self.active = False
        self.captured = 0
        self._auto_sent_at: datetime | None = None
        self._buy_at: datetime | None = None

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: CaptureTargetConfig = ctx.config  # type: ignore[assignment]
        if self.cfg.ball_id is not None and self.cfg.ball_id not in BALL_ORDER:
            await self._end("bola_invalida", disable=True)
            return
        started = _utc(self.cfg.started_at)
        self.until = _utc(self.cfg.until) if self.cfg.until else None
        self.captured = await self._count_since(started)
        if self._done_reason():
            await self._end(self._done_reason() or "", disable=True)
            return
        self.active = True
        hold_until = self.until or self.now() + FOREVER
        ctx.actions.hold("hunt.select", hold_until, self.name, self.cfg.hunt_slug)
        name = self.cfg.species_name
        if name is None and ctx.species is not None and self.cfg.species_id in ctx.species.species:
            name = ctx.species.species[self.cfg.species_id].name
        ctx.state.capture = {
            "species_id": self.cfg.species_id,
            "species_name": name,
            "ball_id": self.cfg.ball_id,
        }
        self.switch = HuntSwitcher(
            ctx,
            source=self.name,
            now=lambda: self.now(),
            sleep=lambda s: self.sleep(s),
            locked=self._locked,
        )
        await ctx.actions.note("capture_target.started", self._info())
        if self.until:
            self._timer = asyncio.create_task(self._expire())
        await self._locked(lambda: self.switch.go(self.cfg.hunt_slug))
        await self._locked(self._tick)

    def _info(self) -> dict[str, Any]:
        return {
            "species_id": self.cfg.species_id,
            "species_name": self.cfg.species_name,
            "hunt_slug": self.cfg.hunt_slug,
            "ball_id": self.cfg.ball_id,
            "count": self.cfg.count,
            "until": self.until.isoformat() if self.until else None,
            "captured": self.captured,
        }

    async def _count_since(self, since: datetime) -> int:
        try:
            rows = await self.ctx.store.recent_events(
                self.ctx.account_id, "pokemon.captured", since
            )
        except Exception as exc:
            self.ctx.log.warning("capture_target: não consegui contar as capturas (%r)", exc)
            return 0
        return sum(1 for _, d in rows if d.get("species_id") == self.cfg.species_id)

    def _done_reason(self) -> str | None:
        if self.cfg.count is not None and self.captured >= self.cfg.count:
            return "count"
        if self.until is not None and self.now() >= self.until:
            return "expired"
        return None

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
        elif event.type == "pokemon.captured" and d.get("species_id") == self.cfg.species_id:
            self.captured += 1
            await self.ctx.actions.note("capture_target.progress", self._info())
            reason = self._done_reason()
            if reason:
                await self._end(reason, disable=True)
                return
        await self._locked(self._tick)

    async def _tick(self) -> None:
        await self.switch.pump()
        await self._sync_automation()
        await self._restock_ball()

    def _wanted_automation(self) -> dict[str, Any] | None:
        """A bola automática desligada: quem joga é o ball_thrower (e numa conta VIP não sai bola dupla)."""
        auto = self.ctx.state.automation
        if auto is None:
            return None
        return {**auto, "autoBallSemParar": False, "autoBallAteCapturar": False}

    async def _sync_automation(self) -> None:
        want = self._wanted_automation()
        if want is None or want == self.ctx.state.automation:
            self._auto_sent_at = None
            return
        now = self.now()
        if self._auto_sent_at is not None and now - self._auto_sent_at < timedelta(seconds=5):
            return  # esperando o estado refletir o último auto.set
        self._auto_sent_at = now
        try:
            await self.ctx.actions.submit(AutoSet(automation=want), source=self.name)
        except ActionBlocked as exc:
            self._auto_sent_at = now + timedelta(seconds=(exc.wait_s or 5) - 5)

    async def _restock_ball(self) -> None:
        st = self.ctx.state
        if self.cfg.ball_id not in BALLS:
            return  # a que vale a pena ou a Beast: quem repõe é o restock (a Beast não se compra)
        ball = BALLS[self.cfg.ball_id]
        stock = int((st.balls or {}).get(str(ball.id), 0))
        if stock >= self.cfg.ball_min or st.gold is None:
            return
        now = self.now()
        if self._buy_at is not None and now - self._buy_at < timedelta(seconds=30):
            return
        qty = min(self.cfg.ball_buy, (int(st.gold) - self.cfg.gold_reserve) // ball.price)
        if qty < 1:
            return
        self._buy_at = now
        try:
            await self.ctx.actions.submit(
                ShopBuy(kind="ball", id=ball.id, qty=qty), source=self.name
            )
            await self.ctx.actions.note(
                "capture_target.bought",
                {"ball_id": ball.id, "qty": qty, "gold_spent": qty * ball.price},
            )
        except ActionBlocked:
            pass

    async def _expire(self) -> None:
        assert self.until is not None
        await self.sleep(max(0.0, (self.until - self.now()).total_seconds()))
        await self._end("expired", disable=True)

    async def _end(self, reason: str, *, disable: bool) -> None:
        was_active = self.active
        self.active = False
        if was_active:
            self.ctx.actions.release(self.name)
            self.ctx.state.capture = None
        if disable:
            await self.ctx.actions.note("capture_target.ended", {**self._info(), "reason": reason})
            try:
                await self.ctx.store.set_plugin_config(
                    self.ctx.account_id, self.name, False, self.cfg.model_dump(mode="json")
                )
            except Exception as exc:
                self.ctx.log.warning("capture_target: não consegui desligar a config (%r)", exc)

    async def stop(self) -> None:
        if (
            self._timer is not None
            and not self._timer.done()
            and asyncio.current_task() is not self._timer
        ):
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer
        # parada pelo capture.stop ou pelo fim da sessão: devolve as bolas e solta as travas
        if self.active:
            await self.ctx.actions.note(
                "capture_target.ended", {**self._info(), "reason": "stopped"}
            )
        await self._end("stopped", disable=False)
