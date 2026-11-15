"""Plugin market_prices: guarda as médias de preço do Mercado (fase 7).

Ver docs/design/fase-7-precos-do-mercado.md. Resumo:
- pede `market.medias` (só leitura) na subida e a cada `interval_min`; se o rate limiter
  barrar, tenta de novo quando ele deixar;
- a resposta chega como `market.prices` e vira linhas em `market_prices` (uma por item
  e moeda), que as métricas de valor dos drops usam;
- os preços são do jogo inteiro, não da conta: só a primeira conta do worker pede.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, MarketAverages
from ..events import Event
from .base import Plugin, PluginContext


class MarketPricesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_min: float = Field(60.0, ge=5)
    retry_s: float = Field(60.0, gt=0)  # depois de uma recusa que não é de rate limit


class MarketPricesPlugin(Plugin):
    name: ClassVar[str] = "market_prices"
    description: ClassVar[str] = "Guarda as médias de preço do Mercado (uma conta por worker)"
    config_model: ClassVar[type[BaseModel]] = MarketPricesConfig
    subscribes: ClassVar[set[str]] = {"market.prices"}
    always_on: ClassVar[bool] = True

    # conta que pede pelo worker inteiro (os preços são os mesmos para todas)
    _owner: ClassVar[UUID | None] = None

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)
        self.sleep = asyncio.sleep  # trocado nos testes

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: MarketPricesConfig = ctx.config  # type: ignore[assignment]
        self._task: asyncio.Task[None] | None = None
        cls = type(self)
        if cls._owner not in (None, ctx.account_id):
            self.active = False
            return
        cls._owner = ctx.account_id
        self.active = True
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self.active and type(self)._owner == self.ctx.account_id:
            type(self)._owner = None

    async def _loop(self) -> None:
        while True:
            await self.sleep(await self._request())

    async def _request(self) -> float:
        """Manda o pedido; devolve quantos segundos esperar até o próximo."""
        try:
            await self.ctx.actions.submit(MarketAverages(), source=self.name)
        except ActionBlocked as exc:
            return exc.wait_s if exc.wait_s is not None else self.cfg.retry_s
        return self.cfg.interval_min * 60

    async def on_event(self, event: Event) -> None:
        if not self.active or event.type != "market.prices":
            return
        d = event.data
        rows = price_rows(event.received_at or self.now(), d.get("days"), d.get("prices"))
        if not rows:
            return
        try:
            await self.ctx.store.save_market_prices(rows)
        except Exception as exc:
            self.ctx.log.warning("market_prices: não consegui gravar os preços (%s)", exc)


def price_rows(taken_at: datetime, days: Any, prices: Any) -> list[dict[str, Any]]:
    """Linhas de market_prices a partir do `market.prices` (uma por item e moeda)."""
    out: list[dict[str, Any]] = []
    for key, by_currency in (prices or {}).items():
        try:
            item_id = int(key)
        except (TypeError, ValueError):
            continue
        for currency in ("orb", "gold"):
            p = (by_currency or {}).get(currency)
            if not isinstance(p, dict) or p.get("avg") is None:
                continue
            out.append(
                {
                    "taken_at": taken_at.isoformat(),
                    "item_id": item_id,
                    "currency": currency,
                    "avg": p["avg"],
                    "units": p.get("units"),
                    "days": days if isinstance(days, int) else None,
                }
            )
    return out
