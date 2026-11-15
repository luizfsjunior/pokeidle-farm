"""Plugin seller: vende no Mercado as pedras que passam da reserva (fase 9, em construção).

Ver docs/design/fase-9-venda-de-pedras.md. Por enquanto, só o que serve para conferir o protocolo:

- **sonda** (`probe_price`): na subida lê os anúncios abertos do item e anuncia 1 unidade a esse
  preço (alto, para não vender). A resposta `market` aba `criado` traz o anúncio com
  `editavelEm` (30 min depois de criado: antes disso não dá para mexer); o cancelamento é
  agendado para depois disso;
- **cancelar** (`cancel_ids`): tenta `market.cancelar` de cada id a cada `cancel_retry_s` até o
  anúncio não aparecer mais em `market.meus` (ou aparecer com estado diferente de "aberto").

Tudo vira `seller.probe`, e as respostas do jogo ficam em `market.reply` (com o `raw`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, MarketCancel, MarketCreate, MarketItemRequest, MarketMine
from ..events import Event
from .base import Plugin, PluginContext


class SellerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    keep: int = Field(5, ge=0)  # unidades guardadas de cada pedra
    floor_ratio: float = Field(0.85, gt=0, le=1)  # piso: fração da média de 7 dias
    probe_price: int | None = Field(None, ge=1)  # sonda: anuncia 1 unidade a esse preço
    probe_item_id: int = 142  # Water Stone
    cancel_ids: list[int] = Field(default_factory=list)  # anúncios próprios a cancelar
    cancel_retry_s: float = Field(300.0, ge=10)


class SellerPlugin(Plugin):
    name: ClassVar[str] = "seller"
    description: ClassVar[str] = "Vende no Mercado as pedras acima da reserva (por enquanto, sonda)"
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
        if self._to_cancel:
            self._tasks.append(asyncio.get_running_loop().create_task(self._cancel_loop()))
        if self.cfg.probe_price is not None:
            await self._probe()

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t

    async def _send(self, action: Any, step: str) -> bool:
        try:
            await self.ctx.actions.submit(action, source=self.name)
        except ActionBlocked as exc:
            await self.ctx.actions.note("seller.probe", {"step": step, "blocked": exc.reason})
            return False
        await self.ctx.actions.note("seller.probe", {"step": step, "sent": action.to_wire()})
        return True

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
