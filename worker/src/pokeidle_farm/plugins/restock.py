"""Plugin restock: escolhe a bola e repõe bolas, poções e revives na loja do NPC.

Ver docs/design/fase-3-reposicao.md. Resumo:
- foco "capture": a bola de maior chance cujo preço cabe no ouro líquido por abate
  (ouro − poções e revives), numa janela dos últimos abates da hunt atual; se nenhuma
  se paga, desliga a bola. Foco "gold_xp_drop": desliga a bola e não compra bola.
- compra uma coisa por vez e espera o estoque subir no `estado` antes da próxima,
  respeitando a reserva de ouro e o teto de gasto por hora.
- o teto por hora sobrevive a reinícios: ao subir, lê os `restock.bought` da última hora.
- compra que passa do prazo de confirmação continua sendo observada por `late_confirm_s`;
  se o estoque subir depois, o gasto entra no teto (e o mesmo item não é recomprado nesse meio-tempo).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, AutoSet, ShopBuy
from ..catalog import BALLS, ITEM_PRICES
from ..events import Event
from .base import Plugin, PluginContext

HOUR_S = 3600.0


class ItemRule(BaseModel):
    id: int
    min: int = Field(ge=0)
    target: int = Field(ge=1)


class RestockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: Literal["capture", "gold_xp_drop"] = "capture"
    items: list[ItemRule] = Field(default_factory=list)  # poções e revives
    ball_min: int = 100
    ball_target: int = 1_000
    gold_reserve: int = 5_000
    max_gold_per_hour: int = 50_000
    window_kills: int = 200
    min_kills: int = 50
    confirm_timeout_s: float = 15.0
    late_confirm_s: float = 300.0
    retry_after_s: float = 60.0


@dataclass
class _Pending:
    kind: str
    id: int
    qty: int
    price: int
    before: int
    deadline: float


class RestockPlugin(Plugin):
    name: ClassVar[str] = "restock"
    description: ClassVar[str] = "Escolhe a bola e repõe bolas, poções e revives"
    config_model: ClassVar[type[BaseModel]] = RestockConfig
    subscribes: ClassVar[set[str]] = {"kill", "item.consumed", "state.snapshot", "state.patch"}

    def __init__(self) -> None:
        self.clock = time.monotonic

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: RestockConfig = ctx.config  # type: ignore[assignment]
        # [ouro do abate, custo de poções e revives gastos depois dele]
        self._window: deque[list[float]] = deque(maxlen=self.cfg.window_kills)
        self._hunt: str | None = None
        self._pending: _Pending | None = None
        self._spent: deque[tuple[float, int]] = deque()
        self._cooldown: dict[tuple[str, int], float] = {}
        self._auto_sent: dict[str, Any] | None = None
        self._auto_sent_at = 0.0
        self._late: list[_Pending] = []  # passaram do prazo, mas ainda podem confirmar
        await self._load_spent()

    async def _load_spent(self) -> None:
        """Recupera o gasto da última hora, para o teto valer mesmo depois de reiniciar."""
        now_wall = datetime.now(UTC)
        try:
            rows = await self.ctx.store.recent_events(
                self.ctx.account_id, "restock.bought", now_wall - timedelta(seconds=HOUR_S)
            )
        except Exception as exc:  # sem o histórico, segue com o teto zerado (e avisa)
            self.ctx.log.warning("restock: não consegui ler o gasto da última hora (%s)", exc)
            return
        now = self.clock()
        for at, data in rows:
            age = (now_wall - at).total_seconds()
            self._spent.append((now - age, int(data.get("gold_spent") or 0)))

    async def on_event(self, event: Event) -> None:
        d = event.data
        if event.type == "kill":
            hunt = d.get("hunt_slug")
            if hunt != self._hunt:
                self._window.clear()
                self._hunt = hunt
            self._window.append([(d.get("gold") or 0) + (d.get("gold_autosell") or 0), 0.0])
        elif event.type == "item.consumed" and self._window:
            self._window[-1][1] += (d.get("qty") or 0) * (d.get("unit_price") or 0)
        await self._check_pending()
        await self._sync_automation()
        await self._restock()

    # --- escolha da bola ----------------------------------------------------

    def _ball_choice(self) -> tuple[bool, int | None]:
        """(tem dados suficientes, bola escolhida ou None se nenhuma se paga)."""
        if len(self._window) < self.cfg.min_kills:
            return False, None
        net = sum(g - c for g, c in self._window) / len(self._window)
        fits = [b for b in BALLS.values() if b.price <= net]
        best = max(fits, key=lambda b: b.catch_rate, default=None)
        return True, best.id if best else None

    def _desired_automation(self) -> dict[str, Any] | None:
        auto = self.ctx.state.automation
        if auto is None:
            return None
        off = {**auto, "autoBallSemParar": False, "autoBallAteCapturar": False}
        if self.cfg.focus == "gold_xp_drop":
            return off
        ready, ball = self._ball_choice()
        if not ready:
            return None
        if ball is None:
            return off
        ids = [b for b in auto.get("ballIds") or [] if b != ball]
        return {
            **auto,
            "ballIds": [ball, *ids],
            "autoBallSemParar": True,
            "autoBallAteCapturar": False,
        }

    async def _sync_automation(self) -> None:
        want = self._desired_automation()
        if want is None or want == self.ctx.state.automation:
            return
        now = self.clock()
        # ainda esperando o servidor refletir o último auto.set
        if want == self._auto_sent and now - self._auto_sent_at < self.cfg.retry_after_s:
            return
        self._auto_sent, self._auto_sent_at = want, now
        try:
            await self.ctx.actions.submit(AutoSet(automation=want), source=self.name)
        except ActionBlocked as exc:
            await self.ctx.actions.note(
                "restock.failed", {"kind": "automation", "id": None, "reason": exc.reason}
            )

    # --- compras ------------------------------------------------------------

    def _stock(self, kind: str, id_: int) -> int:
        src = self.ctx.state.balls if kind == "ball" else self.ctx.state.items
        return int((src or {}).get(str(id_), 0))

    def _spent_last_hour(self, now: float) -> int:
        while self._spent and now - self._spent[0][0] >= HOUR_S:
            self._spent.popleft()
        return sum(cost for _, cost in self._spent)

    async def _fail(
        self, kind: str, id_: int, reason: str, cooldown_s: float | None = None
    ) -> None:
        self._cooldown[(kind, id_)] = self.clock() + (cooldown_s or self.cfg.retry_after_s)
        await self.ctx.actions.note("restock.failed", {"kind": kind, "id": id_, "reason": reason})

    async def _confirm(self, p: _Pending, late: bool) -> None:
        cost = p.qty * p.price
        self._spent.append((self.clock(), cost))
        data: dict[str, Any] = {"kind": p.kind, "id": p.id, "qty": p.qty, "gold_spent": cost}
        if late:
            data["late"] = True
        await self.ctx.actions.note("restock.bought", data)

    async def _check_pending(self) -> None:
        now = self.clock()
        p = self._pending
        if p is not None:
            if self._stock(p.kind, p.id) > p.before:
                self._pending = None
                await self._confirm(p, late=False)
            elif now > p.deadline:
                self._pending = None
                self._late.append(replace(p, deadline=now + self.cfg.late_confirm_s))
                # não recompra o mesmo item enquanto a confirmação ainda pode chegar
                await self._fail(
                    p.kind, p.id, "timeout", max(self.cfg.retry_after_s, self.cfg.late_confirm_s)
                )
        for q in list(self._late):
            if now > q.deadline:
                self._late.remove(q)
            elif self._stock(q.kind, q.id) > q.before:
                self._late.remove(q)
                await self._confirm(q, late=True)

    def _rules(self) -> list[tuple[str, int, int, int, int]]:
        cfg = self.cfg
        rules = [
            ("item", r.id, r.min, r.target, ITEM_PRICES[r.id])
            for r in cfg.items
            if r.id in ITEM_PRICES
        ]
        if cfg.focus == "capture":
            ready, ball = self._ball_choice()
            if ready and ball is not None:
                rules.append(("ball", ball, cfg.ball_min, cfg.ball_target, BALLS[ball].price))
        return rules

    async def _restock(self) -> None:
        if self._pending is not None:
            return
        now = self.clock()
        gold = self.ctx.state.gold or 0
        for kind, id_, min_, target, price in self._rules():
            if now < self._cooldown.get((kind, id_), 0.0):
                continue
            stock = self._stock(kind, id_)
            if stock >= min_:
                continue
            budget = min(
                gold - self.cfg.gold_reserve,
                self.cfg.max_gold_per_hour - self._spent_last_hour(now),
            )
            qty = min(target - stock, budget // price) if budget > 0 else 0
            if qty < 1:
                await self._fail(kind, id_, "sem_ouro")
                continue
            try:
                await self.ctx.actions.submit(ShopBuy(kind=kind, id=id_, qty=qty), source=self.name)
            except ActionBlocked as exc:
                if exc.reason.startswith("rate_limit"):
                    return  # tenta de novo no próximo evento
                await self._fail(kind, id_, exc.reason)
                continue
            self._pending = _Pending(kind, id_, qty, price, stock, now + self.cfg.confirm_timeout_s)
            return  # uma compra por vez
