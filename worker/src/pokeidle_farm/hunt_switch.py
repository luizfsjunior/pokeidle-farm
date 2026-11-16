"""Troca de hunt segura: trava de combate, trocaLivreEm, confirmação e nova tentativa.

Mesmas regras do plugin rank (docs/design/fase-3b-rank-ligado.md, seções 1 e 2, e o timer da
trava): o `hunt.select` só sai quando o relógio do servidor passa de `centroLivreEm` e do
`trocaLivreEm`; durante a trava o jogo ignora o pedido em silêncio, então a troca só conta com
o `hunt.changed` e, sem ele em `confirm_s`, tenta de novo depois de `retry_s`. Um timer acorda
quando a trava acaba, porque o golpe que fecha a janela livre chega no mesmo frame que a renova.

Pedido engolido (16/11): no meio da onda o pokémon já engata o próximo selvagem logo que a trava
acaba, e o pedido perde a corrida. Se a trava se renova depois do envio e o `hunt.changed` não veio
em `swallow_s`, o pedido foi ignorado: tenta de novo na próxima janela livre (muitas vezes só no
intervalo entre ondas), sem esperar `retry_s`. `max_per_hour` conta trocas confirmadas;
`max_attempts_per_hour` limita os envios.

Usado pelo foco gemas; o rank tem a sua própria versão (anterior a este módulo).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from .actions import ActionBlocked, HuntSelect
from .plugins.base import PluginContext


class HuntSwitcher:
    def __init__(
        self,
        ctx: PluginContext,
        *,
        source: str,
        now: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]],
        locked: Callable[[Callable[[], Awaitable[None]]], Awaitable[None]],
        margin_s: float = 0.5,
        confirm_s: float = 15.0,
        retry_s: float = 60.0,
        max_per_hour: int = 6,
        swallow_s: float = 1.5,
        max_attempts_per_hour: int = 60,
    ) -> None:
        self.ctx = ctx
        self.source = source
        self.now = now
        self.sleep = sleep
        self.locked = locked  # roda uma corrotina com o lock do plugin
        self.margin_s = margin_s
        self.confirm_s = confirm_s
        self.retry_s = retry_s
        self.max_per_hour = max_per_hour
        self.swallow_s = swallow_s
        self.max_attempts_per_hour = max_attempts_per_hour
        self.attempts: list[datetime] = []
        self.swallowed = 0
        self._lock_at_send: datetime | None = None
        self.want: str | None = None
        self.current: str | None = ctx.state.hunt_slug
        self.pending: tuple[str, datetime] | None = None
        self.retry_at: datetime | None = None
        self.sent: list[datetime] = []
        self.failures: list[dict[str, str]] = []
        self._timer: asyncio.Task[None] | None = None
        self._timer_at: datetime | None = None

    async def go(self, slug: str | None) -> None:
        if slug != self.want:
            self.retry_at = None
        self.want = slug
        await self.pump()

    async def on_hunt_changed(self, slug: str | None) -> None:
        if slug:
            self.current = slug
        if self.pending is not None and self.current == self.pending[0]:
            self.pending = None
            self.sent.append(self.now())  # troca confirmada (teto por hora)
        await self.pump()

    async def on_error(self, key: str) -> None:
        if self.pending is not None:
            await self._failed(key)

    async def pump(self) -> None:
        now = self.now()
        if self.pending is not None:
            slug, at = self.pending
            lock = self.ctx.state.combat_free_at
            if self.current == slug:
                self.pending = None
            elif (
                lock is not None
                and (self._lock_at_send is None or lock > self._lock_at_send)
                and now - at >= timedelta(seconds=self.swallow_s)
            ):
                self.pending = None  # a trava se renovou depois do envio: pedido engolido
                self.swallowed += 1
            elif now - at > timedelta(seconds=self.confirm_s):
                await self._failed("timeout")
                return
            else:
                return
        slug = self.want
        if slug is None or slug == self.current:
            return
        if self.retry_at is not None and now < self.retry_at:
            self._schedule(self.retry_at)
            return
        hour_ago = now - timedelta(hours=1)
        self.sent = [t for t in self.sent if t > hour_ago]
        self.attempts = [t for t in self.attempts if t > hour_ago]
        if len(self.sent) >= self.max_per_hour:
            self._schedule(self.sent[0] + timedelta(hours=1, seconds=1))
            return
        if len(self.attempts) >= self.max_attempts_per_hour:
            self._schedule(self.attempts[0] + timedelta(hours=1, seconds=1))
            return
        st = self.ctx.state
        locks = [t for t in (st.combat_free_at, st.switch_free_at) if t is not None]
        if locks:
            free_at = max(locks) + timedelta(seconds=self.margin_s)
            server_now = st.server_now(now)
            if server_now < free_at:
                self._schedule(now + (free_at - server_now))
                return
        try:
            await self.ctx.actions.submit(HuntSelect(slug=slug), source=self.source)
        except ActionBlocked as exc:
            wait = exc.wait_s if exc.wait_s is not None else self.retry_s
            self.retry_at = now + timedelta(seconds=wait)
            self._schedule(self.retry_at)
            return
        self.pending = (slug, now)
        self.attempts.append(now)
        self._lock_at_send = st.combat_free_at
        self._schedule(now + timedelta(seconds=self.confirm_s + 0.5))

    async def _failed(self, reason: str) -> None:
        assert self.pending is not None
        slug = self.pending[0]
        self.pending = None
        self.retry_at = self.now() + timedelta(seconds=self.retry_s)
        self.failures.append({"slug": slug, "reason": reason})
        await self.ctx.actions.note(
            "gems.failed", {"action": "hunt.select", "slug": slug, "reason": reason}
        )
        self._schedule(self.retry_at)

    def _schedule(self, at: datetime) -> None:
        if self._timer is not None and not self._timer.done():
            if self._timer_at is not None and self._timer_at <= at:
                return
            self._timer.cancel()
        self._timer_at = at
        delay = max(0.0, (at - self.now()).total_seconds())
        self._timer = asyncio.get_running_loop().create_task(self._wake(delay))

    async def _wake(self, delay: float) -> None:
        await self.sleep(delay)
        self._timer = None
        self._timer_at = None
        await self.locked(self.pump)

    async def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer
            self._timer = None
