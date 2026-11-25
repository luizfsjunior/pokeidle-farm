"""Plugin ball_thrower: o worker joga a bola ele mesmo (`ball.throw`) (docs/design/captura-manual.md).

A bola automática do jogo exige VIP. O arremesso manual não exige, e vale para todas as contas:
- shiny: em qualquer hunt, sempre, a melhor bola em estoque, até a Beast;
- captura ativa (`state.capture`, do capture_target): todo corpo da espécie-alvo, com a bola escolhida
  ou com a que vale a pena (`state.worth_ball`, do restock; Poké sem dados). Sem estoque dela, a melhor
  abaixo;
- bola em tudo (`state.catch_all`, restock no foco capture): todo corpo, com a `worth_ball`. Sem ela (poucos
  abates ou nenhuma bola se paga), não joga. É o único jeito de ter shiny: o brilho é sorteado no
  arremesso, não dá para saber antes (wiki do jogo, `pokepedia.mjs`), então o ramo "shiny" acima só pega o
  caso raro de o jogo marcar o corpo.
Um corpo fica 30 s no chão e aceita uma bola só; entre arremessos, 1,2 s.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from ..actions import ActionBlocked, BallThrow
from ..catalog import BALL_ORDER
from ..events import Event
from .base import Plugin

BODY_S = 30.0  # TEMPO_CHAO_MS do app.js
GAP_S = 1.25  # 1,2 s entre arremessos, com folga para o rate limit do gateway


def _same(a: Any, b: Any) -> bool:
    return (
        isinstance(a, str) and isinstance(b, str) and a.strip().casefold() == b.strip().casefold()
    )


class BallThrowerPlugin(Plugin):
    name: ClassVar[str] = "ball_thrower"
    description: ClassVar[str] = (
        "Joga bola nos shinies, na captura ativa e em todo corpo (bola em tudo)"
    )
    subscribes: ClassVar[set[str]] = {"kill"}
    always_on: ClassVar[bool] = True

    def __init__(self) -> None:
        self.now: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.clock: Callable[[], float] = time.monotonic
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
        self._last: float | None = None

    def _best_up_to(self, top: int) -> int | None:
        balls = self.ctx.state.balls or {}
        return next((b for b in BALL_ORDER if b <= top and int(balls.get(str(b)) or 0) > 0), None)

    async def on_event(self, event: Event) -> None:
        d = event.data
        slot = d.get("slot")
        if not isinstance(slot, int):
            return
        if d.get("shiny"):
            ball = self._best_up_to(BALL_ORDER[0])
            if ball is None:
                await self.ctx.actions.note(
                    "ball_thrower.shiny_missed",
                    {
                        "slot": slot,
                        "wild_name": d.get("wild_name"),
                        "hunt_slug": d.get("hunt_slug"),
                    },
                )
                return
        else:
            cap = self.ctx.state.capture
            worth = self.ctx.state.worth_ball
            if cap and _same(d.get("wild_name"), cap.get("species_name")):
                ball = self._best_up_to(cap.get("ball_id") or worth or 1)
            elif self.ctx.state.catch_all and worth:
                # bola em tudo: só com uma bola que se paga (sem dados ou sem nenhuma, não joga)
                ball = self._best_up_to(worth)
            else:
                return
            if ball is None:
                return
        await self._throw(ball, slot, event.received_at + timedelta(seconds=BODY_S))

    async def _throw(self, ball: int, slot: int, deadline: datetime) -> None:
        if self._last is not None:
            wait = GAP_S - (self.clock() - self._last)
            if wait > 0:
                await self.sleep(wait)
        if self.now() >= deadline:
            return  # o corpo já sumiu
        self._last = self.clock()
        try:
            await self.ctx.actions.submit(BallThrow(ball_id=ball, slot=slot), source=self.name)
        except ActionBlocked:
            pass  # o gateway já gravou o motivo; o corpo não espera
