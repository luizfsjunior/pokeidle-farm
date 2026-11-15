"""Fase 7: preços do Mercado e valor dos drops (docs/design/fase-7-precos-do-mercado.md, casos 1 a 5)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from pokeidle_farm.actions import ActionGateway, ActionMode, MarketAverages, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import NOT_PERSISTED, Event, Translator
from pokeidle_farm.gamedata import ItemsSync, item_rows_from_json, item_rows_from_welcome
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.market_prices import MarketPricesConfig, MarketPricesPlugin
from pokeidle_farm.protocol import codec
from pokeidle_farm.store.memory import MemoryStore


def translate(frame: dict[str, Any]) -> list[Event]:
    tr = Translator(uuid4(), uuid4())
    return tr.translate(*codec.decode(json.dumps(frame)))


# --- 1. drops com quantidade ------------------------------------------------------------


def test_drop_quantity():
    (ev,) = translate(
        {
            "t": "batalha",
            "ev": [
                {
                    "k": "morte",
                    "nome": "Poliwag",
                    "drops": [{"qtd": 3, "nome": "Water Stone"}, {"nome": "Leaf Stone"}],
                }
            ],
        }
    )
    assert ev.type == "kill"
    assert ev.data["drops"] == [
        {"name": "Water Stone", "qty": 3},
        {"name": "Leaf Stone", "qty": 1},
    ]


# --- 2. médias do Mercado no tradutor ---------------------------------------------------


def test_market_averages_become_market_prices():
    (ev,) = translate(
        {
            "t": "market",
            "aba": "medias",
            "dias": 7,
            "medias": {
                "142": {
                    "orb": {"media": 12.5, "unidades": 340},
                    "gold": {"media": 4800, "unidades": 90},
                },
                "7": {"gold": {"media": 30, "unidades": 5}},
                "9": "lixo",
            },
        }
    )
    assert ev.type == "market.prices"
    assert ev.data == {
        "days": 7,
        "prices": {
            "142": {"orb": {"avg": 12.5, "units": 340}, "gold": {"avg": 4800, "units": 90}},
            "7": {"gold": {"avg": 30, "units": 5}},
        },
    }
    assert "market.prices" not in NOT_PERSISTED
    # outras abas do market não viram preços
    assert [e.type for e in translate({"t": "market", "aba": "meus", "linhas": []})] != [
        "market.prices"
    ]


# --- 3. ação ---------------------------------------------------------------------------


def test_market_averages_action():
    assert MarketAverages().to_wire() == {"t": "market.medias"}
    assert MarketAverages.min_interval_s == 300


# --- 4. plugin market_prices -----------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_owner():
    MarketPricesPlugin._owner = None
    yield
    MarketPricesPlugin._owner = None


class Rig:
    def __init__(self, account_id=None, clock: list[float] | None = None) -> None:
        self.clock = clock if clock is not None else [0.0]
        self.sent: list[dict[str, Any]] = []
        self.recorded: list[tuple[str, dict[str, Any]]] = []
        self.sleeps: list[float] = []
        self.release = asyncio.Event()

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.recorded.append((t, d))

        self.store = MemoryStore()
        self.plugin = MarketPricesPlugin()

        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            await self.release.wait()  # o teste decide quando "passa o tempo"
            self.release.clear()
            self.clock[0] += seconds

        self.plugin.sleep = sleep
        self.ctx = PluginContext(
            account_id=account_id or uuid4(),
            nick="farm1",
            config=MarketPricesConfig(),
            bus=EventBus(),
            actions=ActionGateway(
                "acc",
                ActionMode.ENABLED,
                send=send,
                record=record,
                limiter=RateLimiter(clock=lambda: self.clock[0]),
            ),
            state=AccountStateView(),
            store=self.store,
            settings=None,
            log=logging.getLogger("test"),
        )

    async def tick(self) -> None:
        for _ in range(5):
            await asyncio.sleep(0)


async def test_requests_on_start_and_every_interval():
    r = Rig()
    await r.plugin.start(r.ctx)
    await r.tick()
    assert r.sent == [{"t": "market.medias"}]
    assert r.sleeps == [3600]
    r.release.set()
    await r.tick()
    assert r.sent == [{"t": "market.medias"}] * 2
    await r.plugin.stop()


async def test_rate_limited_request_retries_when_allowed():
    r = Rig()
    await r.ctx.actions.submit(MarketAverages(), source="outro")  # alguém pediu agora
    await r.plugin.start(r.ctx)
    await r.tick()
    assert r.sent == [{"t": "market.medias"}]  # só o de antes
    assert r.sleeps == [pytest.approx(300)]
    r.release.set()
    await r.tick()
    assert len(r.sent) == 2
    await r.plugin.stop()


async def test_only_one_account_per_worker_requests():
    a, b = Rig(), Rig()
    await a.plugin.start(a.ctx)
    await b.plugin.start(b.ctx)
    await a.tick()
    assert len(a.sent) == 1 and b.sent == []
    await a.plugin.stop()
    assert MarketPricesPlugin._owner is None
    c = Rig(account_id=b.ctx.account_id)
    await c.plugin.start(c.ctx)
    await c.tick()
    assert len(c.sent) == 1
    await b.plugin.stop()
    await c.plugin.stop()


async def test_prices_are_saved():
    r = Rig()
    await r.plugin.start(r.ctx)
    at = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
    ev = Event(
        account_id=r.ctx.account_id,
        session_id=uuid4(),
        type="market.prices",
        received_at=at,
        data={
            "days": 7,
            "prices": {"142": {"orb": {"avg": 12.5, "units": 340}, "gold": {"avg": None}}},
        },
    )
    await r.plugin.on_event(ev)
    assert r.store.market_prices == [
        {
            "taken_at": at.isoformat(),
            "item_id": 142,
            "currency": "orb",
            "avg": 12.5,
            "units": 340,
            "days": 7,
        }
    ]
    await r.plugin.stop()


# --- 5. catálogo de itens --------------------------------------------------------------


ITEMS = {
    "items": [
        {"id": 142, "name": "Water Stone", "category": "stone", "rare": True, "npcPrice": 5000},
        {"id": 1, "name": "Air Tank", "category": "loot", "rare": True, "npcPrice": 1000},
        {"id": "x", "name": "inválido"},
    ]
}


def test_item_rows():
    assert item_rows_from_json(ITEMS) == [
        {"item_id": 1, "name": "Air Tank", "category": "loot", "rare": True, "npc_price": 1000},
        {
            "item_id": 142,
            "name": "Water Stone",
            "category": "stone",
            "rare": True,
            "npc_price": 5000,
        },
    ]
    welcome = {
        "itensNossos": [{"id": 70070, "nome": "Poção Nossa", "categoria": "pocao", "raro": False}]
    }
    assert item_rows_from_welcome(welcome) == [
        {
            "item_id": 70070,
            "name": "Poção Nossa",
            "category": "pocao",
            "rare": False,
            "npc_price": None,
        }
    ]


async def test_items_sync_by_etag():
    store = MemoryStore()
    responses = [
        (200, '"v1"', json.dumps(ITEMS).encode()),
        (304, '"v1"', b""),
        (200, '"v2"', json.dumps({"items": [*ITEMS["items"], {"id": 2, "name": "Bone"}]}).encode()),
    ]
    asked: list[str | None] = []

    async def http_get(url: str, etag: str | None):
        asked.append(etag)
        return responses.pop(0)

    sync = ItemsSync(store, http_get)
    assert await sync.run_once() == "saved"
    assert await sync.run_once() == "unchanged"
    assert await sync.run_once() == "saved"
    assert asked == [None, '"v1"', '"v1"']
    assert sorted(store.game_items) == [1, 2, 142]
    assert store.game_catalog["items_json"]["data"] == {"etag": '"v2"'}


async def test_ask_scan_only_priced_stones():
    r = Rig()
    r.store.game_items = {
        142: {"item_id": 142, "name": "Water Stone", "category": "stone", "source": "json"},
        900: {"item_id": 900, "name": "Gyaradosite", "category": "stone", "source": "json"},
        5: {"item_id": 5, "name": "Bone", "category": "loot", "source": "json"},
        7: {"item_id": 7, "name": "Key Fragment", "category": "key-item", "source": "json"},
    }
    r.store.market_prices = [
        {"taken_at": "t", "item_id": 142, "currency": "orb", "avg": 30, "units": 1000, "days": 7},
        {"taken_at": "t", "item_id": 7, "currency": "orb", "avg": 240, "units": 9410, "days": 7},
    ]
    r.plugin.ctx = r.ctx
    r.plugin.cfg = r.ctx.config

    async def advance(seconds: float) -> None:
        r.clock[0] += seconds

    r.plugin.sleep = advance
    await r.plugin._scan_asks()
    assert [p for p in r.sent if p["t"] == "market.item"] == [
        {"t": "market.item", "itemId": 7, "moeda": "orb"},
        {"t": "market.item", "itemId": 142, "moeda": "orb"},
    ]
    # a varredura do histórico global e dos pokémon roda na primeira vez
    hist = [p for p in r.sent if p["t"] == "market.historicoGlobal"]
    assert len(hist) == 10 and hist[0] == {
        "t": "market.historicoGlobal",
        "pagina": 0,
        "seq": 1,
        "tipo": "pokemon",
        "moeda": "orb",
    }
    listar = [p for p in r.sent if p["t"] == "market.listar"]
    assert len(listar) == 4 and listar[-1]["soShiny"] is True and listar[0]["ordem"] == "caros"
