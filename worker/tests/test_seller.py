"""Plugin seller: sonda do protocolo do Mercado (docs/design/fase-9-venda-de-pedras.md)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
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
            if s == 300:  # intervalo entre tentativas de cancelar: fica parado até o teste parar
                await asyncio.Event().wait()
            await asyncio.sleep(0)

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


def reply(aba: str, **raw: Any) -> Event:
    return Event(
        account_id=uuid4(),
        session_id=uuid4(),
        type="market.reply",
        data={"aba": aba},
        raw={"t": "market", "aba": aba, **raw},
    )


async def test_probe_lists_one_and_cancels_after_editable():
    r = Rig({"142": 15}, probe_price=999)
    r.plugin.now = lambda: datetime.fromtimestamp(1_000, UTC)
    await r.plugin.start(r.ctx)
    assert [p["t"] for p in r.sent] == ["market.item", "market.criar"]
    assert r.sent[1]["qtd"] == 1 and r.sent[1]["preco"] == 999
    # editável 30 min depois de criado
    anuncio = {"id": 77, "itemId": 142, "preco": 999, "qtd": 1, "editavelEm": (1_000 + 1800) * 1000}
    await r.plugin.on_event(reply("criado", anuncio=anuncio))
    assert r.probes()[-1] == {"step": "criado", "id": 77, "cancel_in_s": 1810}
    await r.plugin.on_event(reply("meus", linhas=[{"id": 77, "estado": "aberto"}]))
    task = r.plugin._tasks[-1]
    for _ in range(20):
        await asyncio.sleep(0)
    assert r.slept[0] == 1810
    assert {"t": "market.cancelar", "id": 77} in r.sent
    await r.plugin.on_event(reply("meus", linhas=[]))
    assert r.probes()[-1] == {"step": "cancelado", "ids": [77]}
    await r.plugin.stop()
    assert task.done()


async def test_cancel_ids_retry_until_gone():
    r = Rig({}, cancel_ids=[5, 6])
    await r.plugin.start(r.ctx)
    for _ in range(20):
        await asyncio.sleep(0)
    assert [p for p in r.sent if p["t"] == "market.cancelar"] == [
        {"t": "market.cancelar", "id": 5},
        {"t": "market.cancelar", "id": 6},
    ]
    await r.plugin.on_event(reply("meus", linhas=[{"id": 6, "estado": "aberto"}]))
    assert r.plugin._to_cancel == {6}
    await r.plugin.stop()


async def test_probe_without_stock_does_nothing():
    r = Rig({"142": 0}, probe_price=999)
    await r.plugin.start(r.ctx)
    assert r.sent == []
    assert r.probes()[0]["step"] == "skip"


async def test_without_probe_the_sell_loop_reads_own_listings():
    r = Rig({"142": 15})
    await r.plugin.start(r.ctx)
    for _ in range(5):
        await asyncio.sleep(0)
    assert r.sent == [{"t": "market.meus"}]
    await r.plugin.stop()


# --- ciclo de venda (docs/design/fase-9-venda-de-pedras.md) ---------------------------------

WATER, THUNDER, SUN, LEAF = 142, 900, 901, 76


def market(r: Rig, asks: dict[int, float | None]) -> None:
    st = r.ctx.store
    st.game_items = {
        WATER: {"item_id": WATER, "name": "Water Stone", "category": "stone", "source": "json"},
        THUNDER: {
            "item_id": THUNDER,
            "name": "Thunder Stone",
            "category": "stone",
            "source": "json",
        },
        SUN: {"item_id": SUN, "name": "Sun Stone", "category": "stone", "source": "json"},
        LEAF: {"item_id": LEAF, "name": "Leaf Stone", "category": "stone", "source": "json"},
    }
    avg = {WATER: 30, THUNDER: 142, SUN: 60, LEAF: 8}
    st.market_prices = [
        {"taken_at": "t1", "item_id": i, "currency": "orb", "avg": v, "units": 100, "days": 7}
        for i, v in avg.items()
    ]
    st.market_asks = [
        {"taken_at": "t2", "item_id": i, "currency": "orb", "min_price": p, "total_units": 10}
        for i, p in asks.items()
    ]


async def run_cycle(r: Rig, mine: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async def read_mine():
        return mine

    r.plugin._read_mine = read_mine  # type: ignore[method-assign]
    await r.plugin.cycle()
    return [d for t, d in r.recorded if t == "seller.would"]


async def started(items: dict[str, int], **cfg: Any) -> Rig:
    """Plugin pronto para chamar `cycle()` direto, sem o laço de venda rodando."""
    r = Rig(items, **cfg)
    r.plugin.ctx = r.ctx
    r.plugin.cfg = r.ctx.config  # type: ignore[assignment]
    r.plugin._mine_event = asyncio.Event()
    return r


async def test_cycle_decisions():
    r = await started({str(WATER): 15, str(THUNDER): 8, str(SUN): 12, str(LEAF): 3})
    market(r, {WATER: 2, THUNDER: 140, SUN: None})
    would = await run_cycle(r, [])
    plan = [d for t, d in r.recorded if t == "seller.plan"][-1]
    by = {s["name"]: s for s in plan["stones"]}
    # Water: o mercado está a 2, abaixo do piso (85% de 30 = 26): guarda
    assert by["Water Stone"]["decision"] == "guarda_abaixo_do_piso"
    # Thunder: 1 abaixo do menor anúncio (139), vende 8 − 5 = 3
    # Sun: ninguém anunciando, vende 12 − 5 = 7 pela média
    assert [w["input"] for w in would] == [
        {**MarketCreate(itemId=THUNDER, qtd=3, preco=139).to_wire()},
        {**MarketCreate(itemId=SUN, qtd=7, preco=60).to_wire()},
    ]
    # Leaf: 3, abaixo da reserva de 5: nem entra no plano
    assert "Leaf Stone" not in by
    assert plan["dry_run"] is True


async def test_cycle_reprices_when_undercut():
    r = await started({str(THUNDER): 5})
    market(r, {THUNDER: 140})
    mine = [{"id": 9, "itemId": THUNDER, "qtd": 3, "preco": 145, "estado": "aberto"}]
    would = await run_cycle(r, mine)
    assert [w["action"] for w in would] == ["market.cancelar", "market.criar"]
    assert would[0]["input"] == {"t": "market.cancelar", "id": 9}
    assert would[1]["input"]["qtd"] == 3 and would[1]["input"]["preco"] == 139


async def test_cycle_new_lot_and_ok():
    r = await started({str(THUNDER): 11})
    market(r, {THUNDER: 140})
    mine = [{"id": 9, "itemId": THUNDER, "qtd": 3, "preco": 139, "estado": "aberto"}]
    would = await run_cycle(r, mine)
    # total 14, quer vender 9, já anunciou 3: lote novo de 6
    assert [(w["action"], w["input"].get("qtd")) for w in would] == [("market.criar", 6)]
    r2 = await started({str(THUNDER): 4})
    market(r2, {THUNDER: 140})
    assert await run_cycle(r2, mine) == []  # total 7, quer 2, já tem 3 anunciados: ok


async def test_cycle_acts_without_dry_run():
    r = await started({str(SUN): 6}, dry_run=False)
    market(r, {SUN: 59})
    await run_cycle(r, [])
    assert r.sent[-1] == MarketCreate(itemId=SUN, qtd=1, preco=58).to_wire()


def test_ask_row_ignores_own_listings():
    from datetime import UTC, datetime

    from pokeidle_farm.plugins.market_prices import ask_row

    raw = {
        "itemId": 142,
        "moeda": "orb",
        "linhas": [
            {"preco": 1, "qtd": 5, "vendedor": "farm1", "estado": "aberto"},
            {"preco": 2, "qtd": 311, "vendedor": "x", "estado": "aberto"},
            {"preco": 2, "qtd": 26, "vendedor": "y", "estado": "aberto"},
            {"preco": 5, "qtd": 4, "vendedor": "z", "estado": "aberto"},
        ],
    }
    row = ask_row(datetime(2026, 11, 15, tzinfo=UTC), raw, "farm1")
    assert row["min_price"] == 2 and row["units_at_min"] == 337
    assert row["total_units"] == 341 and row["listings"] == 3
    empty = ask_row(
        datetime(2026, 11, 15, tzinfo=UTC), {"itemId": 1, "moeda": "orb", "linhas": []}, "f"
    )
    assert empty["min_price"] is None and empty["listings"] == 0


def test_stone_price_uses_market_ask():
    from pokeidle_farm.gems_model import StonePrice

    assert StonePrice(gems=30, sold_week=1000, min_ask=2).sell == 2
    assert StonePrice(gems=30, sold_week=1000).sell == 30
    assert StonePrice(gems=30, sold_week=1000, min_ask=45).sell == 30
