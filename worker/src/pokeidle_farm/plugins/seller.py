"""Plugin seller: vende no Mercado as pedras que passam da reserva (fase 9).

Ver docs/design/fase-9-venda-de-pedras.md. Decisões (15/11): só pedras; guarda `keep` (5) de
cada; anuncia 1 gema abaixo do menor anúncio dos outros vendedores (nunca menos que o mínimo do
Mercado, 2), mas não abaixo de `floor_ratio` (85%) do preço de referência: abaixo disso, guarda.
A referência é a mediana das vendas reais de 7 dias, sem outliers nem transferências (16/11,
docs/design/preco-de-referencia.md); com menos de `min_sales` vendas, a média de 7 dias do jogo.

A cada `interval_min`:
1. lê os próprios anúncios (`market.meus`);
2. para cada pedra: total = inventário + já anunciado; quer vender total − `keep`;
3. preço-alvo = max(2, menor anúncio − 1) (sem anúncio de ninguém: a referência); piso = 85% dela;
4. sem anúncio próprio → anuncia o excesso; com anúncio mais caro que o alvo → cancela e anuncia de
   novo no alvo; com `min_lot` ou mais unidades novas → anuncia um lote à parte; até 20 anúncios.

Com `dry_run` (padrão) grava `seller.would` em vez de mandar. Grava `seller.plan` a cada ciclo.
Também tem a sonda do protocolo (`probe_price`) e o cancelamento por id (`cancel_ids`).
"""

from __future__ import annotations

import asyncio
import contextlib
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..actions import (
    ActionBlocked,
    ActionSpec,
    MarketCancel,
    MarketCreate,
    MarketItemRequest,
    MarketMine,
)
from ..events import Event
from .base import Plugin, PluginContext

MIN_ORB_PRICE = 2  # PRECO_MIN_ORB do jogo: ceil(1 / (1 − 15%))
MAX_LISTINGS = 20  # regra do Mercado: até 20 anúncios abertos por conta


class SellerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    keep: int = Field(5, ge=0)  # unidades guardadas de cada pedra
    floor_ratio: float = Field(0.85, gt=0, le=1)  # piso: fração do preço de referência
    # referência do piso: a mediana das vendas reais (sem outliers nem transferências), se houver
    # `min_sales` vendas em 7 dias; senão a média de 7 dias do jogo (docs/design/preco-de-referencia.md)
    reference: Literal["median", "avg"] = "median"
    min_sales: int = Field(3, ge=1)
    # liquidez: só anuncia se a fila à frente + o lote vende em até `max_days`, pelo volume da semana
    # (docs/design/seller-liquidez.md)
    max_days: float = Field(3.0, gt=0)
    interval_min: float = Field(30.0, ge=5)
    min_lot: int = Field(5, ge=1)  # unidades novas para abrir outro anúncio do mesmo item
    probe_price: int | None = Field(None, ge=1)  # sonda: anuncia 1 unidade a esse preço
    probe_item_id: int = 142  # Water Stone
    cancel_ids: list[int] = Field(default_factory=list)  # anúncios próprios a cancelar
    cancel_retry_s: float = Field(300.0, ge=10)


class SellerPlugin(Plugin):
    name: ClassVar[str] = "seller"
    description: ClassVar[str] = "Vende no Mercado as pedras acima da reserva"
    config_model: ClassVar[type[BaseModel]] = SellerConfig
    subscribes: ClassVar[set[str]] = {"market.reply", "game.error"}

    def __init__(self) -> None:
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
        self.now = lambda: datetime.now(UTC)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: SellerConfig = ctx.config  # type: ignore[assignment]
        self._to_cancel: set[int] = set(self.cfg.cancel_ids)
        self._tasks: list[asyncio.Task[None]] = []
        self._mine: list[dict[str, Any]] | None = None
        self._mine_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        if self._to_cancel:
            self._tasks.append(loop.create_task(self._cancel_loop()))
        if self.cfg.probe_price is not None:
            await self._probe()
        else:
            self._tasks.append(loop.create_task(self._sell_loop()))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

    # --- envio --------------------------------------------------------------------

    async def _send(self, action: ActionSpec, step: str) -> bool:
        try:
            await self.ctx.actions.submit(action, source=self.name)
        except ActionBlocked as exc:
            await self.ctx.actions.note("seller.probe", {"step": step, "blocked": exc.reason})
            return False
        await self.ctx.actions.note("seller.probe", {"step": step, "sent": action.to_wire()})
        return True

    async def _do(self, action: ActionSpec, why: dict[str, Any]) -> None:
        """Ação de venda: grava `seller.would` em dry_run, senão manda (com espaço entre envios)."""
        if self.cfg.dry_run:
            await self.ctx.actions.note(
                "seller.would", {"action": action.name, "input": action.to_wire(), **why}
            )
            return
        await self.sleep(type(action).min_interval_s + 1)
        try:
            await self.ctx.actions.submit(action, source=self.name)
        except ActionBlocked as exc:
            await self.ctx.actions.note(
                "seller.failed", {"action": action.name, "reason": exc.reason, **why}
            )

    # --- ciclo de venda -------------------------------------------------------------

    async def _sell_loop(self) -> None:
        while True:
            try:
                await self.cycle()
            except Exception as exc:  # um ciclo com erro não derruba o plugin
                self.ctx.log.warning("seller: ciclo falhou (%s)", exc)
            await self.sleep(self.cfg.interval_min * 60)

    async def _read_mine(self) -> list[dict[str, Any]] | None:
        self._mine_event.clear()
        try:
            await self.ctx.actions.submit(MarketMine(), source=self.name)
        except ActionBlocked:
            return None
        try:
            await asyncio.wait_for(self._mine_event.wait(), timeout=10)
        except TimeoutError:
            return None
        return self._mine

    async def cycle(self) -> None:
        store = self.ctx.store
        stones = await store.stone_items()
        prices = await store.latest_item_prices()
        asks = await store.latest_asks()
        try:
            reference = await store.market_reference()
        except Exception as exc:  # sem a função (migration pendente) ou o banco fora: usa a média
            self.ctx.log.warning("seller: sem preço de referência (%r); uso a média", exc)
            reference = {}
        mine = await self._read_mine()
        if mine is None:
            await self.ctx.actions.note("seller.plan", {"skipped": "sem market.meus"})
            return
        open_mine = [a for a in mine if a.get("estado", "aberto") == "aberto"]
        n_listings = len(open_mine)
        items = self.ctx.state.items or {}
        decisions: list[dict[str, Any]] = []
        for item_id, name in sorted(stones.items()):
            stock = int(items.get(str(item_id), 0))
            listed = [a for a in open_mine if a.get("itemId") == item_id]
            listed_qty = sum(int(a.get("qtd") or 0) for a in listed)
            total = stock + listed_qty
            if total <= self.cfg.keep:
                continue
            avg = (prices.get(name) or {}).get("orb")
            ref_row = reference.get(name) or {}
            ask_row = asks.get(item_id)
            ask = (ask_row or {}).get("min_price")
            ref, ref_source = avg, "avg"
            median = ref_row.get("median")
            if (
                self.cfg.reference == "median"
                and median is not None
                and (ref_row.get("sales") or 0) >= self.cfg.min_sales
                and (avg is None or median < avg)
            ):
                # a menor das duas: as duas podem estar infladas por vendas fora da curva
                ref, ref_source = median, "median"
            week = (prices.get(name) or {}).get("orb_units_week")
            d: dict[str, Any] = {
                "item_id": item_id,
                "name": name,
                "stock": stock,
                "listed": listed_qty,
                "avg": avg,
                "median": ref_row.get("median"),
                "sales": ref_row.get("sales", 0),
                "ref": ref,
                "ref_source": ref_source,
                "min_ask": ask,
            }
            decisions.append(d)
            if ref is None:
                d["decision"] = "sem_media"
                continue
            if ask_row is None:
                # sem leitura recente dos anúncios não dá para saber se o mercado está lotado
                d["decision"] = "sem_leitura_de_anuncios"
                continue
            if ask is not None:
                target = max(MIN_ORB_PRICE, int(ask) - 1)
            else:
                target = max(MIN_ORB_PRICE, round(ref))
            floor = max(MIN_ORB_PRICE, math.ceil(self.cfg.floor_ratio * ref))
            want = total - self.cfg.keep
            # fila à frente: no menor preço não dá para furar (é o mínimo do Mercado ou o alvo empata)
            ahead = (
                int((ask_row or {}).get("units_at_min") or 0)
                if ask is not None and target >= ask
                else 0
            )
            per_day = float(week) / 7 if isinstance(week, int | float) and week > 0 else 0.0
            new_units = max(0, want - listed_qty)
            days = (ahead + new_units) / per_day if per_day > 0 else None
            d.update(
                target=target,
                floor=floor,
                ahead=ahead,
                per_day=round(per_day, 1),
                days_to_sell=round(days, 1) if days is not None else None,
            )
            if new_units > 0 and (days is None or days > self.cfg.max_days):
                d["decision"] = "guarda_fila_longa"
                continue
            if target < floor:
                d["decision"] = "guarda_abaixo_do_piso"
                continue
            pricier = [a for a in listed if (a.get("preco") or 0) > target]
            if pricier:
                # outro vendedor passou na frente: cancela e anuncia de novo no alvo
                for a in pricier:
                    await self._do(
                        MarketCancel(id=a["id"]), {"reason": "reprecificar", "item_id": item_id}
                    )
                    n_listings -= 1
                kept = sum(int(a.get("qtd") or 0) for a in listed if a not in pricier)
                qty = want - kept
                if qty > 0 and n_listings < MAX_LISTINGS:
                    await self._do(
                        MarketCreate(itemId=item_id, qtd=qty, preco=target),
                        {"reason": "reprecificar", "item_id": item_id},
                    )
                    n_listings += 1
                d["decision"] = "reprecificado"
                continue
            extra = want - listed_qty
            if not listed and extra > 0:
                if n_listings >= MAX_LISTINGS:
                    d["decision"] = "limite_de_anuncios"
                    continue
                await self._do(
                    MarketCreate(itemId=item_id, qtd=extra, preco=target),
                    {"reason": "anunciar", "item_id": item_id},
                )
                n_listings += 1
                d["decision"] = "anunciado"
            elif extra >= self.cfg.min_lot and n_listings < MAX_LISTINGS:
                await self._do(
                    MarketCreate(itemId=item_id, qtd=extra, preco=target),
                    {"reason": "lote_novo", "item_id": item_id},
                )
                n_listings += 1
                d["decision"] = "lote_novo"
            else:
                d["decision"] = "ok"
        await self.ctx.actions.note(
            "seller.plan",
            {"dry_run": self.cfg.dry_run, "listings": n_listings, "stones": decisions},
        )

    # --- sonda e cancelamento ----------------------------------------------------------

    async def _probe(self) -> None:
        item = self.cfg.probe_item_id
        stock = int((self.ctx.state.items or {}).get(str(item), 0))
        if stock < 1:
            await self.ctx.actions.note(
                "seller.probe", {"step": "skip", "reason": "sem estoque", "item": item}
            )
            return
        await self._send(MarketItemRequest(itemId=item, moeda="orb"), "item")
        await self._send(
            MarketCreate(tipo="item", itemId=item, qtd=1, preco=self.cfg.probe_price, moeda="orb"),
            "criar",
        )

    async def _cancel_loop(self, first_delay: float = 0.0) -> None:
        await self.sleep(first_delay)
        while self._to_cancel:
            for n, lid in enumerate(sorted(self._to_cancel)):
                if n:
                    await self.sleep(MarketCancel.min_interval_s + 1)  # o rate limiter é por ação
                await self._send(MarketCancel(id=lid), "cancelar")
            await self.sleep(3)
            await self._send(MarketMine(), "meus")
            await self.sleep(self.cfg.cancel_retry_s)

    async def on_event(self, event: Event) -> None:
        d, raw = event.data, event.raw
        if event.type == "game.error":
            await self.ctx.actions.note("seller.probe", {"step": "erro", "key": d.get("key")})
            return
        if event.type != "market.reply":
            return
        aba = d.get("aba")
        if aba == "meus":
            self._mine = [a for a in raw.get("linhas") or [] if isinstance(a, dict)]
            self._mine_event.set()
        if aba == "criado" and self.cfg.probe_price is not None:
            a = raw.get("anuncio") or {}
            if a.get("itemId") == self.cfg.probe_item_id and a.get("preco") == self.cfg.probe_price:
                lid = int(a["id"])
                wait = _seconds_until(a.get("editavelEm"), self.now()) + 10
                await self.ctx.actions.note(
                    "seller.probe", {"step": "criado", "id": lid, "cancel_in_s": round(wait)}
                )
                self._to_cancel.add(lid)
                self._tasks.append(asyncio.get_running_loop().create_task(self._cancel_loop(wait)))
        elif aba == "meus" and self._to_cancel:
            open_ids = {
                int(a["id"])
                for a in raw.get("linhas") or []
                if isinstance(a, dict) and a.get("id") is not None and a.get("estado") == "aberto"
            }
            gone = {i for i in self._to_cancel if i not in open_ids}
            if gone:
                self._to_cancel -= gone
                await self.ctx.actions.note(
                    "seller.probe", {"step": "cancelado", "ids": sorted(gone)}
                )


def _seconds_until(ms: Any, now: datetime) -> float:
    if not isinstance(ms, int | float):
        return 0.0
    return max(0.0, ms / 1000 - now.timestamp())
