"""Plugin rank: ensaio (docs/design/fase-3b-plugin-rank.md, casos 1 a 20) e agindo de verdade
(docs/design/fase-3b-rank-ligado.md, casos 22 a 38)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pokeidle_farm.actions import (
    ActionGateway,
    ActionMode,
    HuntSelect,
    RankingRequest,
    RateLimiter,
)
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.gamedata import HuntCatalog, SpeciesCatalog
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.rank import RankConfig, RankPlugin, week_start
from pokeidle_farm.store.base import HuntStats
from pokeidle_farm.store.memory import MemoryStore

from .test_gamedata import BOLAS, CAPTURA, KANTO, creature
from .test_rank_queue import hunt

CATALOG = HuntCatalog.from_welcome(
    {
        "t": "welcome",
        "hunts": [
            hunt("caterpie", 10, "Caterpie", 1),
            hunt("metapod", 11, "Metapod", 5),
            hunt("magikarp", 129, "Magikarp", 10),
            hunt("treecko_hoenn", 13252, "Treecko", 500, area="orre"),
        ],
        "captura": CAPTURA,
        "catalogoBolas": BOLAS,
    }
)
SPECIES = SpeciesCatalog.from_creatures(
    [{"creatures": [*KANTO, creature(13252, "Treecko", 13253)]}]
)
AUTOMATION = {
    "autoBallAteCapturar": False,
    "autoBallSemParar": True,
    "ballIds": [1, 4, 3, 5],
    "autoPotion": True,
    "potionIds": [200, 201],
    "hpLimiar": 0.3,
}
WEEK = "2026-11-08"
NOW = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)  # quinta-feira


def ev(type_: str, **data: Any) -> Event:
    return Event(account_id=uuid4(), session_id=uuid4(), type=type_, data=data)


class StatsStore(MemoryStore):
    def __init__(self, stats: list[HuntStats] | None = None) -> None:
        super().__init__()
        self.stats = stats or []

    async def rank_hunt_stats(self, account_id, since):  # type: ignore[override]
        return self.stats


class BrokenStore(MemoryStore):
    async def recent_events(self, *a, **k):  # type: ignore[override]
        raise ConnectionError("fora do ar")

    async def rank_hunt_stats(self, *a, **k):  # type: ignore[override]
        raise ConnectionError("fora do ar")


class Harness:
    def __init__(
        self,
        mode: ActionMode = ActionMode.ENABLED,
        store: MemoryStore | None = None,
        catalog: HuntCatalog | None = CATALOG,
        hunt_slug: str = "gyarados",  # fora do catálogo: nenhuma hunt da fila
        level: int = 150,
        restock_focus: str | None = None,
        **cfg: Any,
    ) -> None:
        self.now = NOW
        self.sent: list[dict[str, Any]] = []
        self.recorded: list[tuple[str, dict[str, Any]]] = []
        self.state = AccountStateView(
            level=level,
            hunt_slug=hunt_slug,
            balls={"1": 500, "4": 100},
            gold=100_000,
            automation=dict(AUTOMATION),
        )

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.recorded.append((t, d))

        self.gateway = ActionGateway(
            "acc",
            mode,
            send=send,
            record=record,
            limiter=RateLimiter(clock=lambda: self.now.timestamp()),
        )
        self.store = store if store is not None else StatsStore()
        self.account_id = uuid4()
        if restock_focus is not None:
            self.store.configs[self.account_id] = {"restock": (True, {"focus": restock_focus})}
        self.plugin = RankPlugin()
        self.plugin.now = lambda: self.now
        self.ctx = PluginContext(
            account_id=self.account_id,
            nick="farm1",
            config=RankConfig.model_validate(cfg),
            bus=EventBus(),
            actions=self.gateway,
            state=self.state,
            store=self.store,
            settings=None,
            log=logging.getLogger("test"),
            catalog=catalog,
            species=SPECIES,
        )

    def stored(self, type_: str, at: datetime, **data: Any) -> None:
        self.store.events.append(
            {"account_id": self.account_id, "type": type_, "received_at": at, "data": data}
        )

    async def start(self) -> Harness:
        await self.plugin.start(self.ctx)
        return self

    async def send_ev(self, event: Event) -> None:
        await self.plugin.on_event(event)

    async def kills(self, n: int, gold: int = 41, minutes: float = 0) -> None:
        for _ in range(n):
            self.now += timedelta(minutes=minutes)
            await self.send_ev(ev("kill", gold=gold, gold_autosell=0, hunt_slug="magikarp"))

    def events(self, t: str) -> list[dict[str, Any]]:
        return [d for typ, d in self.recorded if typ == t]

    def plans(self) -> list[dict[str, Any]]:
        return self.events("rank.plan")

    def would(self, action: str | None = None) -> list[dict[str, Any]]:
        return [w for w in self.events("rank.would") if action is None or w["action"] == action]


def slugs(plan: dict[str, Any]) -> list[str]:
    return [q["slug"] for q in plan["queue"]]


# --- 1. sem catálogo -------------------------------------------------------------------


async def test_without_catalog_waits_for_snapshot():
    h = await Harness(catalog=None).start()
    assert h.plans() == [{"reason": "sem_catalogo", "dry_run": True, "target": None}]
    assert h.would() == []
    await h.send_ev(ev("kill", gold=41))
    assert len(h.plans()) == 1
    h.ctx.catalog = CATALOG
    await h.send_ev(ev("state.snapshot"))
    assert h.plans()[-1]["reason"] == "start"


# --- 2. subida normal ------------------------------------------------------------------


async def test_start_plans_and_records_what_it_would_do():
    h = await Harness().start()
    assert h.sent == [{"t": "topcatch.pedir"}, {"t": "ranking.pedir", "aba": "capturas"}]
    plan = h.plans()[-1]
    assert plan["reason"] == "start"
    assert plan["dry_run"] is True
    assert plan["week_start"] == WEEK
    assert plan["target"]["slug"] == "caterpie"
    assert plan["target"]["chance_source"] == "stage"
    assert "treecko_hoenn" not in slugs(plan)
    assert plan["ball_id"] == 4
    assert plan["current_hunt"] == "gyarados"
    sel = h.would("hunt.select")
    assert [w["input"] for w in sel] == [{"slug": "caterpie"}]
    (auto,) = h.would("auto.set")
    a = auto["input"]["automation"]
    assert a["autoBallAteCapturar"] is True
    assert a["autoBallSemParar"] is False
    assert a["ballIds"][0] == 4
    # nada que mude a conta foi mandado
    assert all(p["t"] in ("topcatch.pedir", "ranking.pedir") for p in h.sent)


# --- 3. pontuadas na subida ------------------------------------------------------------


async def test_scored_species_at_start():
    h = Harness()
    h.stored("rank.week", NOW - timedelta(days=5), week_start="2026-11-01", species={"11": 1})
    h.stored("rank.week", NOW - timedelta(hours=2), week_start=WEEK, species={"10": 9502})
    h.stored("rank.catch", NOW - timedelta(hours=1), week_start=WEEK, species_id=129, scores=True)
    h.stored("rank.catch", NOW - timedelta(hours=1), week_start=WEEK, species_id=11, scores=False)
    await h.start()
    plan = h.plans()[-1]
    assert plan["scored"] == 2
    assert "caterpie" not in slugs(plan) and "magikarp" not in slugs(plan)
    assert plan["target"]["slug"] == "metapod"


# --- 4. semana em Brasília -------------------------------------------------------------


def test_week_start_in_brasilia():
    # sábado 14/11 23:30 em Brasília = domingo 02:30 UTC
    assert week_start(datetime(2026, 11, 15, 2, 30, tzinfo=UTC)) == "2026-11-08"
    # domingo 15/11 00:10 em Brasília
    assert week_start(datetime(2026, 11, 15, 3, 10, tzinfo=UTC)) == "2026-11-15"
    assert week_start(NOW) == WEEK


# --- 5 e 6. ritmo medido e chance observada --------------------------------------------


async def test_measured_rate_and_default():
    store = StatsStore([HuntStats("magikarp", 2000, 60), HuntStats("metapod", 100, 20)])
    h = await Harness(store=store, queue_preview=10, min_active_minutes=30).start()
    q = {i["slug"]: i for i in h.plans()[-1]["queue"]}
    assert q["magikarp"]["kills_per_hour"] == pytest.approx(2000)
    assert q["magikarp"]["kph_known"] is True
    assert q["metapod"]["kph_known"] is False
    assert q["metapod"]["kills_per_hour"] == pytest.approx(2100 / 80 * 60)


async def test_hunts_outside_catalog_are_ignored():
    # eventos do simulador gravados na mesma conta (hunts "sim-*")
    store = StatsStore(
        [
            HuntStats("magikarp", 1000, 60),
            HuntStats("sim-caverna", 14283, 2378, last_chance=0.35, last_ball_id=2),
        ]
    )
    h = await Harness(store=store).start()
    plan = h.plans()[-1]
    q = {i["slug"]: i for i in plan["queue"]}
    assert "sim-caverna" not in q
    assert q["metapod"]["kills_per_hour"] == pytest.approx(1000)  # padrão sem o simulador


async def test_observed_chance_wins():
    store = StatsStore([HuntStats("metapod", 0, 0, last_chance=0.02, last_ball_id=4)])
    h = await Harness(store=store).start()
    q = {i["slug"]: i for i in h.plans()[-1]["queue"]}
    assert q["metapod"]["chance_source"] == "observed"
    assert q["metapod"]["chance"] == pytest.approx(0.02)


# --- 7. banco fora do ar ---------------------------------------------------------------


async def test_store_failure_degrades_without_raising():
    h = await Harness(store=BrokenStore()).start()
    plan = h.plans()[-1]
    assert plan["degraded"] == ["week", "stats"]
    assert plan["target"]["slug"] == "caterpie"


# --- 8 a 13. gatilhos ------------------------------------------------------------------


async def test_capture_of_target_moves_on():
    h = await Harness().start()
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=True))
    plan = h.plans()[-1]
    assert plan["reason"] == "captured"
    assert plan["target"]["slug"] == "metapod"
    assert [w["input"]["slug"] for w in h.would("hunt.select")] == ["caterpie", "metapod"]


async def test_capture_without_scoring_changes_nothing():
    h = await Harness().start()
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=False))
    assert len(h.plans()) == 1


async def test_capture_of_other_species_in_queue():
    h = await Harness().start()
    n_would = len(h.would())
    await h.send_ev(ev("rank.catch", species_id=129, week_start=WEEK, scores=True))
    plan = h.plans()[-1]
    assert plan["reason"] == "captured_other"
    assert plan["target"]["slug"] == "caterpie"
    assert len(h.would()) == n_would


async def test_week_list_after_start():
    h = await Harness().start()
    await h.send_ev(ev("rank.week", week_start=WEEK, week_species=1, species={"10": 1}))
    plan = h.plans()[-1]
    assert plan["reason"] == "week"
    assert plan["scored"] == 1
    assert plan["target"]["slug"] == "metapod"


async def test_week_rollover_by_catch():
    h = await Harness().start()
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=True))
    await h.send_ev(ev("rank.catch", species_id=11, week_start="2026-11-15", scores=True))
    plan = h.plans()[-1]
    assert plan["reason"] == "week_rollover"
    assert plan["week_start"] == "2026-11-15"
    assert plan["scored"] == 1
    assert plan["skipped"] == []
    assert plan["target"]["slug"] == "caterpie"


async def test_level_up_opens_hunts():
    h = await Harness().start()
    h.state.level = 600
    await h.send_ev(ev("state.patch"))
    plan = h.plans()[-1]
    assert plan["reason"] == "level_up"
    assert "treecko_hoenn" in slugs(plan)


# --- 14. tempo máximo no alvo ----------------------------------------------------------


async def test_timeout_skips_target():
    # Caterpie: 1.000 abates/h e chance observada 1% -> 0,1 h; limite 3 x 6 min = 18 min
    store = StatsStore([HuntStats("caterpie", 1000, 60, last_chance=0.01, last_ball_id=4)])
    h = Harness(store=store)
    h.stored("rank.week", NOW - timedelta(hours=1), week_start=WEEK, species={"11": 1, "129": 2})
    await h.start()
    assert h.plans()[-1]["target"]["hours"] == pytest.approx(0.1)
    h.now = NOW + timedelta(minutes=17)
    await h.kills(1)
    assert len(h.plans()) == 1
    h.now = NOW + timedelta(minutes=19)
    await h.kills(1)
    plan = h.plans()[-1]
    assert plan["reason"] == "timeout"
    assert plan["skipped"] == [10]
    # única da fila: continua alvo, no fim da fila, e o tempo recomeça
    assert plan["target"]["slug"] == "caterpie"
    await h.kills(1)
    assert len(h.plans()) == 2


async def test_timeout_moves_species_to_end():
    store = StatsStore([HuntStats("caterpie", 1000, 60, last_chance=0.01, last_ball_id=4)])
    h = await Harness(store=store).start()
    first = h.plans()[-1]["target"]
    h.now = NOW + timedelta(hours=first["hours"] * 3, minutes=11)
    await h.kills(1)
    plan = h.plans()[-1]
    assert plan["reason"] == "timeout"
    assert plan["target"]["slug"] != first["slug"]
    assert slugs(plan)[-1] == first["slug"]


# --- 15. histerese ---------------------------------------------------------------------


def _caterpie_chance() -> float:
    return CATALOG.capture.chance(4, "first_of_three")  # type: ignore[union-attr]


@pytest.mark.parametrize(("ratio", "expected"), [(0.95, "metapod"), (0.85, "caterpie")])
async def test_hysteresis(ratio, expected):
    # Metapod com chance observada tal que a Caterpie fica (1 - ratio) mais rápida
    stats = [HuntStats("metapod", 0, 0, last_chance=_caterpie_chance() * ratio, last_ball_id=4)]
    h = await Harness(store=StatsStore(stats), hunt_slug="metapod").start()
    assert h.plans()[-1]["target"]["slug"] == expected
    sel = h.would("hunt.select")
    assert [w["input"]["slug"] for w in sel] == ([] if expected == "metapod" else ["caterpie"])


# --- 16. sem repetição -----------------------------------------------------------------


async def test_no_repeated_would():
    h = await Harness().start()
    await h.kills(100, gold=200, minutes=0.05)
    assert len(h.would("hunt.select")) == 1
    assert len(h.would("auto.set")) == 1
    assert len(h.plans()) == 1


# --- 17. bola se_paga ------------------------------------------------------------------


async def test_ball_rule_se_paga():
    h = await Harness(min_kills=50, window_kills=50).start()
    assert h.plans()[-1]["ball_id"] == 4  # sem janela: a primeira com estoque
    await h.kills(49, gold=100)
    assert len(h.plans()) == 1
    await h.kills(1, gold=100)
    assert h.plans()[-1]["reason"] == "ball_changed"
    assert h.plans()[-1]["ball_id"] == 3  # Super: 50 <= 100 < 130
    await h.kills(49, gold=30)
    assert len(h.plans()) == 2  # uma troca só por janela
    await h.kills(1, gold=30)
    assert h.plans()[-1]["ball_id"] == 2  # Great
    await h.kills(50, gold=200)
    assert h.plans()[-1]["ball_id"] == 4
    assert [p["reason"] for p in h.plans()].count("ball_changed") == 3
    # a bola nova vira um auto.set novo
    assert h.would("auto.set")[-1]["input"]["automation"]["ballIds"][0] == 4


async def test_ball_rule_fixa_uses_stock():
    h = Harness(rank_ball_rule="fixa", rank_balls=[2, 1])
    await h.start()
    assert h.plans()[-1]["ball_id"] == 1  # sem Great em estoque


# --- 18. sem dry_run, em observe_only ---------------------------------------------------


async def test_without_dry_run_goes_through_gateway():
    h = Harness(mode=ActionMode.OBSERVE_ONLY, dry_run=False, restock_focus="rank")
    await h.start()
    blocked = [d["action"] for d in h.events("action.blocked")]
    assert blocked == ["topcatch.pedir", "ranking.pedir", "hunt.select", "auto.set"]
    assert h.would() == []
    assert h.sent == []


# --- 19. config inválida ---------------------------------------------------------------


def test_invalid_config():
    with pytest.raises(ValidationError):
        RankConfig.model_validate({"foo": 1})
    with pytest.raises(ValidationError):
        RankConfig.model_validate({"rank_balls": []})
    assert RankConfig().rank_balls == [4, 3, 2, 1]
    assert RankConfig().dry_run is True


# --- 20. ação HuntSelect ---------------------------------------------------------------


def test_hunt_select_wire():
    assert HuntSelect(slug="caterpie").to_wire() == {"t": "hunt.select", "slug": "caterpie"}
    assert HuntSelect.min_interval_s == 20  # caso 38 (D-E)


# --- MemoryStore.rank_hunt_stats ------------------------------------------------------


async def test_memory_store_hunt_stats():
    store = MemoryStore()
    acc = uuid4()
    base = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

    def add(t, at, **data):
        store.events.append({"account_id": acc, "type": t, "received_at": at, "data": data})

    add("kill", base, hunt_slug="magikarp")
    add("kill", base + timedelta(seconds=30), hunt_slug="magikarp")
    add("kill", base + timedelta(minutes=1), hunt_slug="magikarp")
    add("kill", base - timedelta(days=30), hunt_slug="magikarp")  # antes do since
    add("capture_attempt", base, hunt_slug="magikarp", chance=0.01, ball_id=1)
    add(
        "capture_attempt", base + timedelta(minutes=2), hunt_slug="magikarp", chance=0.04, ball_id=4
    )
    add("capture_attempt", base + timedelta(minutes=3), hunt_slug="magikarp", chance=None)
    (s,) = await store.rank_hunt_stats(acc, base - timedelta(days=1))
    assert s == HuntStats("magikarp", 3, 2, 0.04, 4)


# === passo 5: agindo de verdade (docs/design/fase-3b-rank-ligado.md) ===================

S = timedelta(seconds=1)
ARMED = {
    **AUTOMATION,
    "autoBallAteCapturar": True,
    "autoBallSemParar": False,
    "ballIds": [4, 1, 3, 5],
}


def acting(**kw: Any) -> Harness:
    kw.setdefault("dry_run", False)
    kw.setdefault("restock_focus", "rank")
    return Harness(**kw)


def selects(h: Harness) -> list[str]:
    return [p["slug"] for p in h.sent if p["t"] == "hunt.select"]


def autos(h: Harness) -> list[dict[str, Any]]:
    return [p for p in h.sent if p["t"] == "auto.set"]


async def tick(h: Harness, seconds: float = 0) -> None:
    """Avança o relógio e manda um abate (é o evento que mais chega). Com 200 de ouro
    por abate a regra se_paga continua na Ultra Ball, a bola do começo."""
    h.now += timedelta(seconds=seconds)
    await h.send_ev(ev("kill", gold=200, gold_autosell=0, hunt_slug=h.plugin._current))


# --- 22 a 25. trava e relógio do servidor ----------------------------------------------


async def test_switch_when_locks_are_open():
    h = acting()
    h.state.combat_free_at = NOW - 5 * S
    h.state.switch_free_at = NOW - 5 * S
    await h.start()
    assert selects(h) == ["caterpie"]
    assert h.would() == []


async def test_combat_lock_delays_switch():
    h = acting()
    h.state.combat_free_at = NOW + 3 * S
    await h.start()
    assert selects(h) == []
    await tick(h, 4)
    assert selects(h) == ["caterpie"]


async def wake(h: Harness) -> None:
    """Roda os timers do plugin; o sleep falso só avança o relógio."""
    while h.plugin._timer is not None:
        await h.plugin._timer


def fake_sleep(h: Harness):
    async def sleep(seconds: float) -> None:
        h.now += timedelta(seconds=seconds)

    return sleep


async def test_timer_switches_when_lock_ends_without_events():
    # caso 23b: o golpe que fecha a janela chega no mesmo frame que a renova, então
    # nenhum evento enxerga a trava aberta; o timer acorda quando ela acaba
    h = acting()
    h.plugin.sleep = fake_sleep(h)
    h.state.combat_free_at = NOW + 3 * S
    await h.start()
    assert selects(h) == []
    h.now += 1 * S
    h.state.combat_free_at = NOW + 4 * S  # golpe novo renovou a trava
    await h.send_ev(ev("state.patch"))
    assert selects(h) == []
    await wake(h)
    assert selects(h) == ["caterpie"]
    assert h.now >= NOW + 4.5 * S


async def test_stop_cancels_timer():
    h = acting()
    h.state.combat_free_at = NOW + 30 * S
    await h.start()
    assert h.plugin._timer is not None
    await h.plugin.stop()
    assert h.plugin._timer is None
    assert selects(h) == []


async def test_switch_free_at_delays_switch():
    h = acting()
    h.state.switch_free_at = NOW + 8 * S
    await h.start()
    await tick(h, 5)
    assert selects(h) == []
    await tick(h, 4)
    assert selects(h) == ["caterpie"]


async def test_server_clock_is_used():
    h = acting()
    h.state.server_offset = 5 * S
    h.state.combat_free_at = NOW + 3 * S  # no servidor já são NOW + 5 s
    await h.start()
    assert selects(h) == ["caterpie"]


# --- 26 a 29. confirmação, erro, nova tentativa e teto -----------------------------------


async def test_hunt_changed_confirms_switch():
    h = await acting().start()
    await h.send_ev(ev("hunt.changed", slug="caterpie"))
    assert h.plugin._current == "caterpie"
    assert h.plugin._target_since == h.now
    await tick(h, 30)
    assert selects(h) == ["caterpie"]
    assert h.events("rank.failed") == []


async def test_game_error_retries_after_wait():
    h = await acting().start()
    await h.send_ev(ev("game.error", key="hunt.emCombate"))
    assert h.events("rank.failed") == [
        {"action": "hunt.select", "slug": "caterpie", "reason": "hunt.emCombate"}
    ]
    await tick(h, 30)
    assert selects(h) == ["caterpie"]
    await tick(h, 31)
    assert selects(h) == ["caterpie", "caterpie"]


async def test_unconfirmed_switch_times_out_and_skips_after_three():
    h = await acting().start()
    for n in (1, 2):
        await tick(h, 16)
        assert [f["reason"] for f in h.events("rank.failed")] == ["timeout"] * n
        await tick(h, 61)
        assert selects(h) == ["caterpie"] * (n + 1)
    await tick(h, 16)
    plan = h.plans()[-1]
    assert plan["reason"] == "switch_failed"
    assert plan["skipped"] == [10]
    assert plan["target"]["slug"] == "metapod"
    await tick(h, 5)  # o rate limiter (20 s) segurou a troca seguinte
    assert selects(h)[-1] == "metapod"


async def test_hourly_switch_cap():
    h = await acting(max_switches_per_hour=2).start()
    await h.send_ev(ev("hunt.changed", slug="caterpie"))
    h.now += 21 * S
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=True))
    await h.send_ev(ev("hunt.changed", slug="metapod"))
    h.now += 21 * S
    await h.send_ev(ev("rank.catch", species_id=11, week_start=WEEK, scores=True))
    assert selects(h) == ["caterpie", "metapod"]
    assert [p["reason"] for p in h.plans()].count("switch_cap") == 1
    await tick(h, 60)
    assert [p["reason"] for p in h.plans()].count("switch_cap") == 1
    h.now = NOW + timedelta(hours=1, seconds=1)
    await tick(h)
    assert selects(h) == ["caterpie", "metapod", "magikarp"]


# --- 30 a 33. Lançar até Capturar --------------------------------------------------------


async def test_auto_set_goes_with_hunt_select():
    h = await acting(hunt_slug="magikarp").start()
    assert [p["t"] for p in h.sent] == [
        "topcatch.pedir",
        "ranking.pedir",
        "hunt.select",
        "auto.set",
    ]
    assert selects(h) == ["caterpie"]
    (a,) = autos(h)
    assert a["autoBallAteCapturar"] is True
    assert a["autoBallSemParar"] is False
    assert a["ballIds"][0] == 4


async def test_capture_moves_on_and_rearms():
    h = await acting().start()
    await h.send_ev(ev("hunt.changed", slug="caterpie"))
    h.state.automation = dict(ARMED)  # o servidor refletiu o auto.set
    await h.send_ev(ev("state.patch"))
    h.now += 31 * S
    h.state.automation = {**ARMED, "autoBallAteCapturar": False}  # desligou na captura
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=True))
    assert h.plans()[-1]["reason"] == "captured"
    assert selects(h) == ["caterpie", "metapod"]
    assert len(autos(h)) == 2
    assert autos(h)[-1]["autoBallAteCapturar"] is True


async def test_rearm_when_flag_drops_without_scoring():
    h = await acting().start()
    await h.send_ev(ev("hunt.changed", slug="caterpie"))
    h.state.automation = dict(ARMED)
    await tick(h, 31)
    assert len(autos(h)) == 1
    h.state.automation = {**ARMED, "autoBallAteCapturar": False}
    await h.send_ev(ev("state.patch"))
    assert len(autos(h)) == 2
    assert autos(h)[-1]["autoBallAteCapturar"] is True


async def test_auto_set_not_repeated_while_waiting():
    h = await acting().start()
    await h.send_ev(ev("hunt.changed", slug="caterpie"))
    for _ in range(100):
        await tick(h, 0.5)
    assert len(autos(h)) == 1
    h.now = NOW + 61 * S
    await tick(h)
    assert len(autos(h)) == 2


# --- 34 a 37. dono do auto.set e fallback ------------------------------------------------


@pytest.mark.parametrize("focus", ["capture", None])
async def test_restock_in_other_focus_only_records(focus):
    h = await Harness(dry_run=False, restock_focus=focus).start()
    plan = h.plans()[-1]
    assert plan["degraded"] == ["restock_focus"]
    assert [w["action"] for w in h.would()] == ["hunt.select", "auto.set"]
    assert [p["t"] for p in h.sent] == ["topcatch.pedir", "ranking.pedir"]
    assert h.events("rank.mode") == []


async def test_rank_mode_active_then_fallback():
    h = await acting().start()
    assert h.events("rank.mode") == [{"mode": "active", "ball_id": 4}]
    await tick(h, 1)
    await h.send_ev(ev("hunt.changed", slug="caterpie"))
    assert len(h.events("rank.mode")) == 1
    n_auto = len(autos(h))
    await h.send_ev(
        ev("rank.week", week_start=WEEK, week_species=3, species={"10": 1, "11": 2, "129": 3})
    )
    assert h.plans()[-1]["target"] is None
    assert h.events("rank.mode")[-1] == {"mode": "fallback", "reason": "queue_empty"}
    assert len(h.events("rank.mode")) == 2
    await tick(h, 61)
    assert len(autos(h)) == n_auto


def _all_scored(h: Harness) -> None:
    h.stored(
        "rank.week",
        NOW - timedelta(hours=1),
        week_start=WEEK,
        species={"10": 1, "11": 2, "129": 3},
    )


@pytest.mark.parametrize(("fallback", "expected"), [("magikarp", ["magikarp"]), (None, [])])
async def test_queue_empty_goes_to_fallback_hunt(fallback, expected):
    h = acting(hunt_slug="caterpie", fallback_hunt=fallback)
    _all_scored(h)
    await h.start()
    assert h.plans()[-1]["target"] is None
    assert selects(h) == expected
    assert autos(h) == []


async def test_back_from_fallback_on_level_up():
    h = acting()
    _all_scored(h)
    await h.start()
    assert h.events("rank.mode") == [{"mode": "fallback", "reason": "queue_empty"}]
    h.state.level = 600
    await h.send_ev(ev("state.patch"))
    assert h.plans()[-1]["reason"] == "level_up"
    assert h.events("rank.mode")[-1]["mode"] == "active"
    assert selects(h) == ["treecko_hoenn"]
    assert len(autos(h)) == 1


# === passo 6: posição no ranking (docs/design/fase-3b-metricas-e-card.md) ==============


async def test_min_active_minutes_default_is_five():
    # caso 5 do passo 6 (D-M)
    assert RankConfig().min_active_minutes == 5
    store = StatsStore([HuntStats("magikarp", 100, 6), HuntStats("metapod", 100, 4)])
    h = await Harness(store=store).start()
    q = {i["slug"]: i for i in h.plans()[-1]["queue"]}
    assert q["magikarp"]["kph_known"] is True
    assert q["metapod"]["kph_known"] is False


def boards(h: Harness) -> list[dict[str, Any]]:
    return [p for p in h.sent if p["t"] == "ranking.pedir"]


async def test_ranking_request_on_start_and_after_scoring():
    # caso 9
    assert RankingRequest().to_wire() == {"t": "ranking.pedir", "aba": "capturas"}
    assert RankingRequest.min_interval_s == 300
    h = await Harness().start()  # dry_run: vai mesmo assim
    assert len(boards(h)) == 1
    h.now += timedelta(minutes=6)
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=True, week_species=1))
    assert len(boards(h)) == 2
    h.now += timedelta(minutes=1)  # o rate limiter segura
    await h.send_ev(ev("rank.catch", species_id=11, week_start=WEEK, scores=True, week_species=2))
    assert len(boards(h)) == 2


def row(nick: str, valor: int, level: int = 100) -> dict[str, Any]:
    return {"nick": nick, "level": level, "valor": valor}


async def started_with_n(n: int) -> Harness:
    h = Harness()
    h.stored("rank.week", NOW - timedelta(hours=1), week_start=WEEK, week_species=n, species={})
    return await h.start()


async def test_position_when_in_list():
    # caso 11
    h = await started_with_n(5)
    await h.send_ev(ev("rank.board", week_start=WEEK, rows=[row("a", 9), row("farm1", 5, 150)]))
    (p,) = h.events("rank.position")
    assert p["position"] == 2
    assert p["inside"] is True and p["missing"] == 0
    assert p["species"] == 5 and p["week_start"] == WEEK
    assert p["above"] == {"nick": "a", "valor": 9}


async def test_position_tie_by_level():
    # caso 12: farm1 tem nível 150
    h = await started_with_n(5)
    rows = [row("a", 9), row("b", 5, level=200), row("c", 5, level=100)]
    await h.send_ev(ev("rank.board", week_start=WEEK, rows=rows))
    (p,) = h.events("rank.position")
    assert p["position"] == 3
    assert p["above"] == {"nick": "b", "valor": 5}


async def test_position_outside_top():
    # caso 13
    h = await started_with_n(4)
    rows = [row(f"j{i}", 200 - i) for i in range(99)] + [row("ultimo", 41)]
    await h.send_ev(ev("rank.board", week_start=WEEK, rows=rows))
    (p,) = h.events("rank.position")
    assert p["position"] is None
    assert p["inside"] is False
    assert p["list_size"] == 100
    assert p["cutoff"] == 41
    assert p["missing"] == 38


async def test_position_ignores_other_week_and_repeats():
    # caso 14
    h = await started_with_n(5)
    await h.send_ev(ev("rank.board", week_start="2026-11-01", rows=[row("a", 9)]))
    assert h.events("rank.position") == []
    for _ in range(2):
        await h.send_ev(ev("rank.board", week_start=WEEK, rows=[row("a", 9)]))
    assert len(h.events("rank.position")) == 1
    # espécie nova muda a posição gravada
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=True, week_species=6))
    await h.send_ev(ev("rank.board", week_start=WEEK, rows=[row("a", 9)]))
    assert [p["species"] for p in h.events("rank.position")] == [5, 6]


async def test_blocked_ranking_request_goes_out_when_limit_allows():
    # o ranking.pedir barrado pelo limite de 5 min sai sozinho depois (a posição não fica velha)
    h = Harness()  # dry_run: o timer não pode mandar auto.set nem hunt.select
    h.plugin.sleep = fake_sleep(h)
    h.stored("rank.week", NOW - timedelta(hours=1), week_start=WEEK, week_species=4, species={})
    await h.start()
    assert len(boards(h)) == 1
    h.now += timedelta(seconds=43)
    await h.send_ev(ev("rank.catch", species_id=10, week_start=WEEK, scores=True, week_species=5))
    assert len(boards(h)) == 1
    await wake(h)
    assert len(boards(h)) == 2
    assert h.now >= NOW + timedelta(seconds=300)
    assert [p["t"] for p in h.sent] == ["topcatch.pedir", "ranking.pedir", "ranking.pedir"]
    await h.send_ev(ev("rank.board", week_start=WEEK, rows=[row("a", 24)]))
    assert h.events("rank.position")[-1]["species"] == 5
