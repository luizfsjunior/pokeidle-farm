"""Plugin seller: sonda do protocolo do Mercado (docs/design/fase-9-venda-de-pedras.md)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode, MarketCreate, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event, Translator
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.seller import SellerConfig, SellerPlugin
from pokeidle_farm.protocol import codec
from pokeidle_farm.store.memory import MemoryStore


class Rig:
    def __init__(self, items: dict[str, int], **cfg: Any) -> None:
        self.sent: list[dict[str, Any]] = []
        self.recorded: list[tuple[str, dict[str, Any]]] = []
        self.slept: list[float] = []

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.recorded.append((t, d))

        self.plugin = SellerPlugin()

        async def sleep(s: float) -> None:
            self.slept.append(s)

        self.plugin.sleep = sleep
        self.ctx = PluginContext(
            account_id=uuid4(),
            nick="farm1",
            config=SellerConfig.model_validate(cfg),
            bus=EventBus(),
            actions=ActionGateway(
                "acc",
                ActionMode.ENABLED,
                send=send,
                record=record,
                limiter=RateLimiter(clock=lambda: sum(self.slept)),
            ),
            state=AccountStateView(items=items),
            store=MemoryStore(),
            settings=None,
            log=logging.getLogger("test"),
        )

    def probes(self) -> list[dict[str, Any]]:
        return [d for t, d in self.recorded if t == "seller.probe"]


def test_market_create_wire():
    assert MarketCreate(itemId=142, qtd=1, preco=999).to_wire() == {
        "t": "market.criar",
        "tipo": "item",
        "itemId": 142,
        "pokemonId": None,
        "casaId": None,
        "bicicletaId": None,
        "qtd": 1,
        "preco": 999,
        "moeda": "orb",
        "dias": None,
    }


def test_other_market_tabs_become_market_reply():
    tr = Translator(uuid4(), uuid4())
    (ev,) = tr.translate(*codec.decode('{"t":"market","aba":"meus","linhas":[]}'))
    assert ev.type == "market.reply" and ev.data == {"aba": "meus"} and ev.raw["linhas"] == []


async def test_probe_lists_one_and_cancels_after_retention():
    r = Rig({"142": 15}, probe_price=999)
    await r.plugin.start(r.ctx)
    assert [p["t"] for p in r.sent] == ["market.item", "market.criar", "market.meus"]
    assert r.sent[1]["qtd"] == 1 and r.sent[1]["preco"] == 999
    raw = {
        "t": "market",
        "aba": "meus",
        "linhas": [{"id": 77, "itemId": 142, "preco": 999, "qtd": 1}],
    }
    await r.plugin.on_event(
        Event(
            account_id=uuid4(),
            session_id=uuid4(),
            type="market.reply",
            data={"aba": "meus"},
            raw=raw,
        )
    )
    await r.plugin._cancel_task
    assert r.slept[0] >= 120
    assert r.sent[3] == {"t": "market.cancelar", "id": 77}
    assert r.sent[4] == {"t": "market.meus"}
    steps = [p["step"] for p in r.probes()]
    assert steps == ["item", "criar", "meus", "meus", "cancelar", "meus_depois"]


async def test_probe_without_stock_does_nothing():
    r = Rig({"142": 0}, probe_price=999)
    await r.plugin.start(r.ctx)
    assert r.sent == []
    assert r.probes()[0]["step"] == "skip"


async def test_no_probe_no_messages():
    r = Rig({"142": 15})
    await r.plugin.start(r.ctx)
    await asyncio.sleep(0)
    assert r.sent == []
