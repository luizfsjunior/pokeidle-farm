"""Foco gemas, ritmo aprendido e arquivos do jogo (docs/design/foco-gemas-e-ritmo.md)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from pokeidle_farm.actions import ActionGateway, ActionMode, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.gamedata import (
    GameFilesSync,
    HuntCatalog,
    SpeciesCatalog,
    parse_loot_stones,
)
from pokeidle_farm.gems_model import StonePrice, chain_position, rank_options, stones_of
from pokeidle_farm.pace import PaceBook, rates_for
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.gems import GemsConfig, GemsPlugin, compute_potential
from pokeidle_farm.store.base import HuntStats
from pokeidle_farm.store.memory import MemoryStore

from .test_gamedata import BOLAS, CAPTURA, KANTO
from .test_rank_queue import hunt

CATALOG = HuntCatalog.from_welcome(
    {
        "t": "welcome",
        "hunts": [
            hunt("caterpie", 10, "Caterpie", 1),
            hunt("metapod", 11, "Metapod", 5),
            hunt("butterfree", 12, "Butterfree", 10),
            hunt("tauros", 128, "Tauros", 10),
            hunt("magikarp", 129, "Magikarp", 1),
        ],
        "captura": CAPTURA,
        "catalogoBolas": BOLAS,
    }
)
SPECIES = SpeciesCatalog.from_creatures([{"creatures": KANTO}])
PRICES = {
    "Cocoon Stone": StonePrice(gems=14, sold_week=9393),
    "Feather Stone": StonePrice(gems=15, sold_week=2482),
    "Sun Stone": StonePrice(gems=60, sold_week=438),
    "Water Stone": StonePrice(gems=30, sold_week=1012),
}
NOW = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)


# --- modelo das pedras --------------------------------------------------------------


def test_chain_position_like_the_game():
    assert chain_position(SPECIES, 10) == 0  # Caterpie
    assert chain_position(SPECIES, 11) == 1  # Metapod
    assert chain_position(SPECIES, 12) == 2  # Butterfree
    assert chain_position(SPECIES, 128) == 2  # Tauros, sem evolução
    assert chain_position(SPECIES, 129) == 0  # Magikarp
    assert stones_of(SPECIES, 12) == ["Cocoon Stone", "Feather Stone"]


def test_rank_options_with_liquidity_cap():
    rate = {s: (1000.0, "measured") for s in CATALOG.hunts}
    opts = {o.slug: o for o in rank_options(CATALOG, SPECIES, 10, rate, PRICES)}
    # Magikarp: 1000 × 0,2% × 30 = 60 gemas/h; 336/semana contra o teto de 101,2
    assert opts["magikarp"].gems_per_hour == pytest.approx(60)
    assert opts["magikarp"].capped_gems_per_hour == pytest.approx(101.2 / 168 * 30)
    # Butterfree: Cocoon cabe inteira (840 < 939,3) e Feather esbarra no teto (248,2)
    assert opts["butterfree"].gems_per_hour == pytest.approx(70 + 75)
    assert opts["butterfree"].capped_gems_per_hour == pytest.approx(70 + 248.2 / 168 * 15)
    best = rank_options(CATALOG, SPECIES, 10, rate, PRICES)
    assert best[0].slug == "butterfree"
    # nível 5: Butterfree e Tauros fora
    assert {o.slug for o in rank_options(CATALOG, SPECIES, 5, rate, PRICES)} == {
        "caterpie",
        "metapod",
        "magikarp",
    }
    # outra conta já tira 900 Cocoon por semana: sobra 39,3
    taken = rank_options(CATALOG, SPECIES, 10, rate, PRICES, taken_week={"Cocoon Stone": 900})
    bf = next(o for o in taken if o.slug == "butterfree")
    assert bf.capped_gems_per_hour == pytest.approx(39.3 / 168 * 14 + 248.2 / 168 * 15)


# --- ritmo aprendido ---------------------------------------------------------------


def test_pace_book():
    pace = PaceBook(5)
    pace.load("magikarp", 1000, 60)
    pace.load("zubat", 10, 3)  # 3 min: ainda não conta
    assert pace.measured("magikarp") == pytest.approx(1000)
    assert pace.measured("zubat") is None
    for minute in range(3):
        pace.add_kill("zubat", NOW + timedelta(minutes=minute))
    assert pace.measured("zubat") == pytest.approx(13 / 6 * 60)
    levels = {"magikarp": 1, "zubat": 10, "nidoran": 10, "charmander": 20, "caterpie": 1}
    rates = rates_for(levels, pace, 900)
    assert rates["magikarp"] == (pytest.approx(1000), "measured")
    assert rates["nidoran"] == (pytest.approx(130), "level")
    assert rates["charmander"] == (pytest.approx(130), "near_level")  # o nível medido abaixo
    assert rates_for({"x": 5}, PaceBook(5), 900) == {"x": (900, "default")}


# --- arquivos do jogo ----------------------------------------------------------------


LOOT_JS = "export const CHANCE_PEDRA_POR_ESTAGIO = [0.2, 0.35, 0.5];"
STONES_JS = "export const PEDRA_POR_TIPO = {\n  NORMAL: 'Sun Stone',\n  WATER: 'Water Stone',\n};"


def test_parse_loot_stones():
    assert parse_loot_stones(LOOT_JS, STONES_JS) == {
        "chance_by_position": [0.002, 0.0035, 0.005],
        "stone_by_type": {"NORMAL": "Sun Stone", "WATER": "Water Stone"},
    }
    assert parse_loot_stones("mudou", STONES_JS) is None


async def test_game_files_sync():
    store = MemoryStore()
    files = {
        "pokepedia.mjs": "wiki",
        "shared/loot-pedras.mjs": LOOT_JS,
        "shared/pedras-evolucao.mjs": STONES_JS,
    }
    calls: list[tuple[str, str | None]] = []

    async def http_get(url: str, etag: str | None):
        path = url.removeprefix("https://pokeidle.io/")
        calls.append((path, etag))
        if etag:
            return 304, etag, b""
        return 200, f'"{path}"', files[path].encode()

    sync = GameFilesSync(store, http_get, files=tuple(files))
    assert await sync.run_once() == "saved"
    assert store.game_files["pokepedia.mjs"]["content"] == "wiki"
    assert store.game_catalog["loot_stones"]["data"]["chance_by_position"] == [0.002, 0.0035, 0.005]
    assert await sync.run_once() == "unchanged"
    assert calls[-1] == ("shared/pedras-evolucao.mjs", '"shared/pedras-evolucao.mjs"')


# --- plugin gems -----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_claims():
    GemsPlugin._claims.clear()
    yield
    GemsPlugin._claims.clear()


class Harness:
    def __init__(
        self, *, hunt_slug: str = "caterpie", level: int = 10, rank_acting: bool = False, **cfg: Any
    ):
        self.now = NOW
        self.sent: list[dict[str, Any]] = []
        self.recorded: list[tuple[str, dict[str, Any]]] = []
        self.store = MemoryStore()
        self.account_id = uuid4()
        if rank_acting:
            self.store.configs[self.account_id] = {"rank": (True, {"dry_run": False})}
        # preços no store: itens e um snapshot
        self.store.game_items = {
            i: {"item_id": i, "name": n, "source": "json"} for i, n in enumerate(PRICES, start=900)
        }
        self.store.market_prices = [
            {
                "taken_at": "t1",
                "item_id": i,
                "currency": "orb",
                "avg": PRICES[n].gems,
                "units": PRICES[n].sold_week,
                "days": 7,
            }
            for i, n in enumerate(PRICES, start=900)
        ]

        async def stats(account_id, since):
            return [HuntStats(s, 1000, 60) for s in CATALOG.hunts]

        self.store.rank_hunt_stats = stats  # type: ignore[method-assign]

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.recorded.append((t, d))

        self.plugin = GemsPlugin()
        self.plugin.now = lambda: self.now

        async def no_sleep(_s: float) -> None:
            return None

        self.plugin.sleep = no_sleep
        self.ctx = PluginContext(
            account_id=self.account_id,
            nick="farm1",
            config=GemsConfig.model_validate(cfg),
            bus=EventBus(),
            actions=ActionGateway(
                "acc",
                ActionMode.ENABLED,
                send=send,
                record=record,
                limiter=RateLimiter(clock=lambda: self.now.timestamp()),
            ),
            state=AccountStateView(level=level, hunt_slug=hunt_slug),
            store=self.store,
            settings=None,
            log=logging.getLogger("test"),
            catalog=CATALOG,
            species=SPECIES,
        )

    async def start(self) -> Harness:
        await self.plugin.start(self.ctx)
        return self

    def events(self, t: str) -> list[dict[str, Any]]:
        return [d for typ, d in self.recorded if typ == t]

    def selects(self) -> list[str]:
        return [p["slug"] for p in self.sent if p["t"] == "hunt.select"]


async def test_dry_run_records_what_it_would_do():
    h = await Harness().start()
    (plan,) = h.events("gems.plan")
    assert plan["reason"] == "start"
    assert plan["target"]["slug"] == "butterfree"
    assert plan["options"][0]["slug"] == "butterfree"
    assert plan["month_gems_24h"] > 0
    assert h.events("gems.would") == [
        {"action": "hunt.select", "input": {"slug": "butterfree"}, "reason": "start"}
    ]
    assert h.selects() == []


async def test_acting_switches_hunt():
    h = await Harness(dry_run=False).start()
    assert h.selects() == ["butterfree"]
    await h.plugin.on_event(
        Event(
            account_id=uuid4(), session_id=uuid4(), type="hunt.changed", data={"slug": "butterfree"}
        )
    )
    assert h.plugin.switch.current == "butterfree" and h.plugin.switch.pending is None


async def test_hysteresis_keeps_a_close_hunt():
    # Tauros (Sun Stone, teto 43,8/semana) rende ~15,6 gemas/h; Butterfree ~92: troca.
    # Com 15% de folga, só fica na atual se ela estiver perto da melhor.
    h = await Harness(dry_run=False, hunt_slug="tauros", hysteresis=10.0).start()
    assert h.events("gems.plan")[0]["target"]["slug"] == "tauros"
    assert h.selects() == []


async def test_rank_acting_blocks_gems():
    h = await Harness(dry_run=False, rank_acting=True).start()
    plan = h.events("gems.plan")[0]
    assert plan["degraded"] == ["rank_acting"] and plan["acting"] is False
    assert h.selects() == []
    assert len(h.events("gems.would")) == 1


async def test_two_accounts_split_liquidity():
    a = await Harness(dry_run=False).start()
    b = await Harness(dry_run=False).start()
    assert a.selects() == ["butterfree"]
    # a primeira já tira toda a Feather que cabe e 840 Cocoon; para a segunda o Butterfree rende menos
    plan_b = b.events("gems.plan")[0]
    bf = next(o for o in plan_b["options"] if o["slug"] == "butterfree")
    assert bf["capped_gems_per_hour"] < a.events("gems.plan")[0]["target"]["capped_gems_per_hour"]


async def test_replans_on_interval_and_prices():
    h = await Harness().start()
    kill = Event(
        account_id=uuid4(), session_id=uuid4(), type="kill", data={"hunt_slug": "caterpie"}
    )
    await h.plugin.on_event(kill)
    assert len(h.events("gems.plan")) == 1
    h.now += timedelta(minutes=16)
    await h.plugin.on_event(kill)
    assert [p["reason"] for p in h.events("gems.plan")] == ["start", "interval"]
    await h.plugin.on_event(
        Event(account_id=uuid4(), session_id=uuid4(), type="market.prices", data={})
    )
    assert h.events("gems.plan")[-1]["reason"] == "prices"


async def test_compute_potential():
    h = Harness()
    pot = await compute_potential(h.ctx, NOW)
    assert pot is not None
    assert pot["options"][0]["slug"] == "butterfree"
    assert pot["prices"] == 4 and pot["trainer_level"] == 10


# --- ritmo projetado pelo nível do ativo -------------------------------------------------


def test_pace_projects_rate_to_active_level():
    from pokeidle_farm.pace import damage_factor

    pace = PaceBook(5)
    pace.load("geodude", 1100, 60, 23)  # perto do teto: não escala
    pace.load("nidoran", 100, 60, 20)  # longe do teto
    assert damage_factor(30) / damage_factor(20) == pytest.approx(420 / 200)
    assert pace.projected("nidoran", 30) == pytest.approx(210)
    assert pace.projected("nidoran", None) == pytest.approx(100)
    assert pace.projected("geodude", 40) == pytest.approx(1100)
    assert pace.projected("nidoran", 200) == pytest.approx(1100)  # limitado ao teto
    # abates da sessão entram no nível médio
    for minute in range(3):
        pace.add_kill("nidoran", NOW + timedelta(minutes=minute), 30)
    assert 20 < pace.level_of("nidoran") < 21
    rates = rates_for({"nidoran": 10, "zubat": 10}, pace, 900, active_level=30)
    assert rates["zubat"][1] == "level"
    assert rates["zubat"][0] == pytest.approx(rates["nidoran"][0])


async def test_memory_store_avg_active_level():
    from uuid import uuid4 as u

    store = MemoryStore()
    acc = u()
    for lvl in (20, 22, None):
        store.events.append(
            {
                "account_id": acc,
                "type": "kill",
                "received_at": NOW,
                "data": {"hunt_slug": "x", "active_level": lvl},
            }
        )
    (st,) = await store.rank_hunt_stats(acc, NOW - timedelta(days=1))
    assert st.avg_active_level == pytest.approx(21)


# --- foco XP (docs/design/foco-xp.md) ----------------------------------------------------


def test_xp_formulas():
    from pokeidle_farm.xp_model import base_xp, total_xp

    assert base_xp(1) == 8 and base_xp(10) == 68 and base_xp(20) == 248
    assert total_xp(21) == 116000 and total_xp(150) == 54042300


def test_xp_options_prefer_measured_and_bonus():
    from pokeidle_farm.xp_model import xp_options

    rate = {
        "caterpie": (1000.0, "measured"),
        "butterfree": (100.0, "measured"),
        "tauros": (500.0, "level"),
    }
    # caterpie (nível 1) medida: 100 abates com 1.300 XP -> 13/abate, bônus 13/8 = 1,625
    book = {"caterpie": (1300.0, 100.0)}
    opts = {o.slug: o for o in xp_options(CATALOG, 10, rate, book)}
    assert (
        opts["caterpie"].xp_per_kill == pytest.approx(13)
        and opts["caterpie"].xp_source == "measured"
    )
    assert opts["tauros"].xp_per_kill == pytest.approx(68 * 1.625)  # fórmula × bônus
    assert opts["tauros"].xp_per_hour == pytest.approx(500 * 68 * 1.625)
    assert xp_options(CATALOG, 10, rate, book)[0].slug == "tauros"


async def test_gems_plugin_with_xp_objective():
    h = await Harness(dry_run=False, objective="xp", hunt_slug="caterpie").start()
    plan = h.events("gems.plan")[-1]
    assert plan["objective"] == "xp"
    # mesmo ritmo medido em todas (1000/h): ganha a de maior nível (mais XP por abate)
    assert plan["target"]["level"] == 10
    assert h.selects() == [plan["target"]["slug"]]


async def test_swallowed_select_is_retried_at_next_free_window():
    """A trava se renova depois do envio e o hunt.changed não vem: pedido engolido, tenta de novo."""
    h = await Harness(dry_run=False).start()
    sw = h.plugin.switch
    assert h.selects() == ["butterfree"] and sw.pending is not None
    # um golpe renova a trava logo depois do envio
    h.ctx.state.combat_free_at = h.now + timedelta(seconds=3)
    h.now += timedelta(seconds=2)
    await sw.pump()
    assert sw.pending is None and sw.swallowed == 1
    assert h.events("gems.failed") == []  # não é falha: só perdeu a corrida
    # a trava acaba e o limitador (20 s) libera: reenvia
    h.now += timedelta(seconds=20)
    await sw.pump()
    assert h.selects() == ["butterfree", "butterfree"]
    assert len(sw.attempts) == 2 and sw.sent == []  # o teto por hora conta trocas confirmadas
    await h.plugin.on_event(
        Event(
            account_id=uuid4(), session_id=uuid4(), type="hunt.changed", data={"slug": "butterfree"}
        )
    )
    assert sw.current == "butterfree" and len(sw.sent) == 1
