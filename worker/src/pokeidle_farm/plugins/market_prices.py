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

from ..actions import (
    ActionBlocked,
    ActionSpec,
    MarketAverages,
    MarketHistoryGlobal,
    MarketItemRequest,
    MarketListPokemon,
)
from ..events import Event
from ..outland_model import (
    DROPS,
    GOAL_LEVEL,
    outland_dict,
    outland_options,
    outland_prices,
    tier_mult_at,
)
from .base import Plugin, PluginContext


class MarketPricesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_min: float = Field(60.0, ge=5)
    survey_every_h: float = Field(6.0, ge=1)  # varredura do histórico global e dos pokémon
    survey_pages: int = Field(5, ge=0, le=50)
    retry_s: float = Field(60.0, gt=0)  # depois de uma recusa que não é de rate limit


class MarketPricesPlugin(Plugin):
    name: ClassVar[str] = "market_prices"
    description: ClassVar[str] = "Guarda as médias de preço do Mercado (uma conta por worker)"
    config_model: ClassVar[type[BaseModel]] = MarketPricesConfig
    subscribes: ClassVar[set[str]] = {"market.prices", "market.reply"}
    always_on: ClassVar[bool] = True

    # conta que pede pelo worker inteiro (os preços são os mesmos para todas)
    _owner: ClassVar[UUID | None] = None

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)
        self.sleep = asyncio.sleep  # trocado nos testes
        self._scan: asyncio.Task[None] | None = None
        self._last_survey: datetime | None = None

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: MarketPricesConfig = ctx.config  # type: ignore[assignment]
        self._task: asyncio.Task[None] | None = None
        self._scan: asyncio.Task[None] | None = None
        self._last_survey: datetime | None = None
        cls = type(self)
        if cls._owner not in (None, ctx.account_id):
            self.active = False
            return
        cls._owner = ctx.account_id
        self.active = True
        self._task = asyncio.get_running_loop().create_task(self._loop())

    async def stop(self) -> None:
        if self._scan is not None:
            self._scan.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scan
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
        if not self.active:
            return
        if event.type == "market.reply":
            await self._on_asks(event)
            return
        if event.type != "market.prices":
            return
        d = event.data
        rows = price_rows(event.received_at or self.now(), d.get("days"), d.get("prices"))
        if not rows:
            return
        try:
            await self.ctx.store.save_market_prices(rows)
        except Exception as exc:
            self.ctx.log.warning("market_prices: não consegui gravar os preços (%s)", exc)
            return
        if self._scan is None or self._scan.done():
            self._scan = asyncio.get_running_loop().create_task(self._scan_asks())

    async def _scan_asks(self) -> None:
        """Lê os anúncios abertos de cada pedra (o preço de venda real) e depois o potencial."""
        try:
            stones = await self.ctx.store.stone_items()
            priced = await self.ctx.store.latest_item_prices()
        except Exception as exc:
            self.ctx.log.warning("market_prices: não consegui ler as pedras (%s)", exc)
            stones, priced = {}, {}
        # a categoria "stone" tem ~200 itens (mega stones etc.); só as que negociam em gemas.
        # Além delas, todos os outros itens com preço em gemas (fragmentos, tickets, casas...)
        by_name = (
            {n: i for i, n in (await self.ctx.store.item_ids_by_name(list(priced))).items()}
            if priced
            else {}
        )
        stones = {i: n for i, n in stones.items() if (priced.get(n) or {}).get("orb") is not None}
        for name, p in priced.items():
            if p.get("orb") is not None and name in by_name:
                stones.setdefault(by_name[name], name)
        for n, item_id in enumerate(sorted(stones)):
            if n:
                await self.sleep(MarketItemRequest.min_interval_s + 1)
            try:
                await self.ctx.actions.submit(
                    MarketItemRequest(itemId=item_id, moeda="orb"), source=self.name
                )
            except ActionBlocked:
                continue
        if stones:
            await self.sleep(5)  # a última resposta chegar
        await self._potential()
        if self._survey_due():
            await self._survey()

    def _survey_due(self) -> bool:
        last = self._last_survey
        return last is None or (self.now() - last).total_seconds() >= self.cfg.survey_every_h * 3600

    async def _survey(self) -> None:
        """Histórico global de vendas (pokémon e itens, em gemas) e os pokémon anunciados mais caros.

        As respostas viram `market.reply` (gravadas com o raw) para a análise do que dá dinheiro.
        """
        self._last_survey = self.now()
        actions: list[ActionSpec] = []
        for tipo in ("pokemon", "item"):
            for page in range(self.cfg.survey_pages):
                actions.append(
                    MarketHistoryGlobal(pagina=page, tipo=tipo, moeda="orb", seq=page + 1)
                )
        for page in range(min(3, self.cfg.survey_pages)):
            actions.append(MarketListPokemon(ordem="caros", pagina=page))
        actions.append(MarketListPokemon(ordem="caros", soShiny=True))
        for n, action in enumerate(actions):
            if n:
                await self.sleep(type(action).min_interval_s + 1)
            try:
                await self.ctx.actions.submit(action, source=self.name)
            except ActionBlocked:
                continue

    async def _on_asks(self, event: Event) -> None:
        if event.data.get("aba") != "item":
            return
        row = ask_row(event.received_at or self.now(), event.raw, self.ctx.nick)
        if row is None:
            return
        try:
            await self.ctx.store.save_market_asks([row])
        except Exception as exc:
            self.ctx.log.warning("market_prices: não consegui gravar os anúncios (%s)", exc)

    async def _potential(self) -> None:
        # estimativa de gemas na Outland com os preços novos (docs/design/outland-potencial.md);
        # substituiu o potencial em pedras (2 gemas, filas de semanas)
        try:
            potential = await compute_outland(self.ctx, self.now())
        except Exception as exc:
            self.ctx.log.warning("market_prices: não consegui calcular a Outland (%s)", exc)
            return
        if potential is not None:
            await self.ctx.actions.note("outland.potential", potential)


async def compute_outland(
    ctx: PluginContext, now: datetime, *, preview: int = 5
) -> dict[str, Any] | None:
    """Gemas/h previstas nas melhores hunts da Outland para o ativo no 150 (`outland.potential`)."""
    cat, species = ctx.catalog, ctx.species
    prof = ctx.state.active_pokemon
    if cat is None or species is None or not prof or not getattr(cat, "rules", None):
        return None
    hunts = [
        (h.slug, h.species_name or h.name, h.level, h.species_id)
        for h in cat.hunts.values()
        if str(h.area or "").lower() == "outland"
    ]
    if not hunts:
        return None
    prices = outland_prices(await ctx.store.market_reference())
    raw = getattr(species, "raw", {}) or {}
    trainer = ctx.state.level
    proj, options = await asyncio.to_thread(
        lambda: outland_options(hunts, prof, raw, cat.rules, prices, top_level=trainer)
    )
    top, top_label = tier_mult_at(cat.rules, max(GOAL_LEVEL, trainer or 0))
    return {
        "trainer_level": ctx.state.level,
        "goal_level": GOAL_LEVEL,
        "active_species_id": proj.get("speciesId"),
        "active_name": (raw.get(proj.get("speciesId")) or {}).get("name"),
        "top_tier_mult": top,
        "top_tier_label": top_label,
        "prices": {
            name: {"gems": prices.get(name), "chance": chance, "tier_scaled": scaled}
            for name, chance, scaled in DROPS
        },
        "hunts": len(hunts),
        "options": [outland_dict(o) for o in options[:preview]],
    }


def ask_row(taken_at: datetime, raw: dict[str, Any], own_nick: str) -> dict[str, Any] | None:
    """Resumo de `market` aba `item`: menor preço, unidades nele e a fila (sem a própria conta)."""
    item_id, moeda = raw.get("itemId"), raw.get("moeda") or "orb"
    if not isinstance(item_id, int) or moeda not in ("orb", "gold"):
        return None
    lines = [
        a
        for a in raw.get("linhas") or []
        if isinstance(a, dict)
        and a.get("estado", "aberto") == "aberto"
        and a.get("vendedor") != own_nick
        and isinstance(a.get("preco"), int | float)
    ]
    prices = [a["preco"] for a in lines]
    low = min(prices) if prices else None
    return {
        "taken_at": taken_at.isoformat(),
        "item_id": item_id,
        "currency": moeda,
        "min_price": low,
        "units_at_min": sum(int(a.get("qtd") or 0) for a in lines if a["preco"] == low),
        "total_units": sum(int(a.get("qtd") or 0) for a in lines),
        "listings": len(lines),
    }


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
