"""Foco Outland: o plugin gems com objective "outland" (docs/design/foco-outland.md)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest

from pokeidle_farm.events import Event
from pokeidle_farm.gamedata import HuntCatalog
from pokeidle_farm.outland_model import outland_picks, outland_prices
from pokeidle_farm.store.base import HuntStats

from .test_commands import Rig, farm
from .test_gamedata import BOLAS, CAPTURA
from .test_gems import Harness
from .test_rank_queue import hunt

RULES = {
    "outlandTiers": [
        {"tier": 101, "numero": 1, "nivel": 150, "mult": 1},
        {"tier": 102, "numero": 2, "nivel": 500, "mult": 1.1},
    ]
}
CATALOG = HuntCatalog.from_welcome(
    {
        "t": "welcome",
        "hunts": [
            hunt("caterpie", 10, "Caterpie", 1),
            hunt("butterfree", 12, "Butterfree", 10),
            hunt("tauros", 128, "Tauros", 10),
            hunt("out_magikarp", 129, "Magikarp", 150, area="outland"),
            hunt("out_tauros", 128, "Tauros", 150, area="outland"),
            hunt("out_butterfree", 12, "Butterfree", 150, area="outland"),
        ],
        "captura": CAPTURA,
        "catalogoBolas": BOLAS,
        **RULES,
    }
)
# abates/h medidos por hunt (60 min cada): na Outland ganha a out_tauros
PACE = {
    "caterpie": 900,
    "butterfree": 1200,
    "tauros": 800,
    "out_magikarp": 700,
    "out_tauros": 1100,
    "out_butterfree": 1000,
}
REFERENCE = {
    "Key Fragment": {"median": 220},
    "Shiny Stone Fragment": {"median": 86},
    "Bicycle Fragment": {"median": 160},
    "Bronze Boss Token": {"median": 3},
    "Water Stone": {"median": 30},
}


def harness(level: int, hunt_slug: str = "caterpie", **cfg: Any) -> Harness:
    h = Harness(dry_run=False, objective="outland", hunt_slug=hunt_slug, level=level, **cfg)
    h.ctx.catalog = CATALOG
    h.store.reference = REFERENCE  # type: ignore[attr-defined]

    async def stats(account_id, since):  # type: ignore[no-untyped-def]
        return [HuntStats(s, k, 60) for s, k in PACE.items()]

    h.store.rank_hunt_stats = stats  # type: ignore[method-assign]
    return h


def test_outland_prices_take_only_the_drops():
    assert outland_prices(REFERENCE) == {
        "Key Fragment": 220.0,
        "Shiny Stone Fragment": 86.0,
        "Bicycle Fragment": 160.0,
        "Bronze Boss Token": 3.0,
    }


def test_outland_picks_rank_by_kill_pace_and_value_the_drops():
    rate = {s: (float(k), "measured") for s, k in PACE.items()}
    prices = outland_prices(REFERENCE)
    picks = outland_picks(CATALOG.hunts, 200, rate, prices, 1.0)
    assert [p.slug for p in picks] == ["out_tauros", "out_butterfree", "out_magikarp"]
    # 1.100 abates/h × [(220 + 86 + 160) / 250 mil + 3 / 10 mil] × 0,85
    per_kill = ((220 + 86 + 160) * 0.000004 + 3 * 0.0001) * 0.85
    assert picks[0].gems_per_hour == pytest.approx(1100 * per_kill)
    # o tier multiplica tudo
    top = outland_picks(CATALOG.hunts, 600, rate, prices, 1.1)[0]
    assert top.gems_per_hour == pytest.approx(1100 * per_kill * 1.1)
    assert outland_picks(CATALOG.hunts, 149, rate, prices, 1.0) == []  # Outland trancada
    skip = outland_picks(CATALOG.hunts, 200, rate, prices, 1.0, skip={"out_tauros"})
    assert skip[0].slug == "out_butterfree"


async def test_outland_focus_goes_to_the_fastest_outland_hunt():
    h = await harness(level=200, use_model=False).start()
    plan = h.events("gems.plan")[-1]
    assert plan["objective"] == "outland"
    assert plan["target"]["slug"] == "out_tauros"
    assert plan["outland_tier"] == 1 and plan["tier_mult"] == 1.0
    assert plan["target"]["gems_per_hour"] > 0 and plan["month_gems_24h"] > 0
    assert [o["slug"] for o in plan["options"]] == ["out_tauros", "out_butterfree", "out_magikarp"]
    assert h.selects() == ["out_tauros"]


async def test_outland_focus_uses_the_account_tier():
    h = harness(level=600, use_model=False)
    h.ctx.state.outland_tier = 102
    await h.start()
    plan = h.events("gems.plan")[-1]
    assert plan["outland_tier"] == 2 and plan["tier_mult"] == 1.1


async def test_outland_focus_keeps_a_close_hunt():
    """A out_butterfree faz 1.000/h e a melhor 1.100/h: 10% não passa a histerese de 15%."""
    h = await harness(level=200, hunt_slug="out_butterfree", use_model=False).start()
    plan = h.events("gems.plan")[-1]
    assert plan["target"]["slug"] == "out_butterfree"
    assert h.selects() == []


async def test_outland_focus_levels_up_like_xp_before_150():
    h = await harness(level=120, use_model=False).start()
    plan = h.events("gems.plan")[-1]
    assert plan["objective"] == "xp" and plan["outland_locked"] is True
    assert not plan["target"]["slug"].startswith("out_")
    # chegou ao 150: o próximo plano já é na Outland
    h.ctx.state.level = 150
    h.now += timedelta(minutes=1)
    await h.plugin.on_event(
        Event(account_id=uuid4(), session_id=uuid4(), type="state.patch", data={})
    )
    plan = h.events("gems.plan")[-1]
    assert plan["objective"] == "outland" and plan["target"]["slug"] == "out_tauros"


async def test_focus_set_accepts_outland():
    rig = Rig()
    try:
        acc = farm(rig.store, "farm1")
        await rig.boot()
        c = await rig.cmd(acc, "focus.set", focus="outland")
        assert c["status"] == "done", c["error"]
        cfg = rig.store.configs[acc.id]
        assert cfg["gems"][0] is True and cfg["gems"][1]["objective"] == "outland"
        assert cfg["restock"][1]["focus"] == "gold_xp_drop"
    finally:
        await rig.close()
