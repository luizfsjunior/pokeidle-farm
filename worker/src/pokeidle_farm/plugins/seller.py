"""Plugin seller: vende no Mercado as pedras que passam da reserva (fase 9, em construção).

Ver docs/design/fase-9-venda-de-pedras.md. Por enquanto só a **sonda** do protocolo: com
`probe_price`, na subida ele lê os anúncios abertos do item, anuncia 1 unidade a esse preço
(alto, para não vender), lê os próprios anúncios e cancela esse anúncio depois da retenção de
2 min do Mercado. Tudo vira `seller.probe` e as respostas do jogo ficam em `market.reply` (com o
`raw`), para conferir o formato antes de vender de verdade.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, MarketCancel, MarketCreate, MarketItemRequest, MarketMine
from ..events import Event
from .base import Plugin, PluginContext

RETENTION_S = 125  # retenção de 2 min do Mercado depois de anunciar, com folga


class SellerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    keep: int = Field(5, ge=0)  # unidades guardadas de cada pedra
    floor_ratio: float = Field(0.85, gt=0, le=1)  # piso: fração da média de 7 dias
    probe_price: int | None = Field(None, ge=1)  # sonda: anuncia 1 unidade a esse preço e cancela
    probe_item_id: int = 142  # Water Stone


class SellerPlugin(Plugin):
    name: ClassVar[str] = "seller"
    description: ClassVar[str] = "Vende no Mercado as pedras acima da reserva (sonda do protocolo)"
    config_model: ClassVar[type[BaseModel]] = SellerConfig
    subscribes: ClassVar[set[str]] = {"market.reply", "game.error"}

    def __init__(self) -> None:
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: SellerConfig = ctx.config  # type: ignore[assignment]
        self._probe_listing: Any = None
        self._cancel_task: asyncio.Task[None] | None = None
        self._probe_done = False
        if self.cfg.probe_price is not None:
            await self._probe()

    async def stop(self) -> None:
        if self._cancel_task is not None:
            self._cancel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cancel_task

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
        ok = await self._send(
            MarketCreate(tipo="item", itemId=item, qtd=1, preco=self.cfg.probe_price, moeda="orb"),
            "criar",
        )
        if ok:
            await self._send(MarketMine(), "meus")

    async def on_event(self, event: Event) -> None:
        d = event.data
        if event.type == "game.error":
            await self.ctx.actions.note("seller.probe", {"step": "erro", "key": d.get("key")})
            return
        if event.type != "market.reply" or self.cfg.probe_price is None or self._probe_done:
            return
        if d.get("aba") != "meus" or self._cancel_task is not None:
            return
        listing = _find_listing(event.raw, self.cfg.probe_item_id, self.cfg.probe_price)
        if listing is None:
            await self.ctx.actions.note("seller.probe", {"step": "meus", "found": False})
            return
        self._probe_listing = listing
        await self.ctx.actions.note(
            "seller.probe", {"step": "meus", "found": True, "listing": listing}
        )
        self._cancel_task = asyncio.get_running_loop().create_task(self._cancel_later(listing))

    async def _cancel_later(self, listing: dict[str, Any]) -> None:
        await self.sleep(RETENTION_S)
        await self._send(MarketCancel(id=listing["id"]), "cancelar")
        self._probe_done = True
        await self.sleep(3)
        await self._send(MarketMine(), "meus_depois")


def _find_listing(raw: dict[str, Any], item_id: int, price: int) -> dict[str, Any] | None:
    """O anúncio da sonda em `market` aba `meus` (procura nas listas da mensagem)."""
    for key in ("linhas", "anuncios", "meus", "itens"):
        for a in raw.get(key) or []:
            if not isinstance(a, dict) or a.get("id") is None:
                continue
            ids = {
                a.get("itemId"),
                a.get("item_id"),
                (a.get("item") or {}).get("id") if isinstance(a.get("item"), dict) else None,
            }
            if item_id in ids and a.get("preco") == price:
                return a
    return None
