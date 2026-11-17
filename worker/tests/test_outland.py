"""Estimativa de gemas na Outland (docs/design/outland-potencial.md)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pokeidle_farm.actions import ActionGateway, ActionMode, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.outland_model import (
    COMMISSION,
    FRAGMENT_CHANCE,
    TOKEN_CHANCE,
    final_form,
    item_value,
    outland_options,
    tier_mults,
)
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.market_prices import compute_outland
from pokeidle_farm.store.memory import MemoryStore

from .test_progression import NOW, RAW, RULES, STATS

PROFILE = {
    "speciesId": 1,
    "level": 30,
    "ivs": {s: 27 for s in STATS},
    "quality": 1.6,
    "potencia": 1,
}
PRICES = {
    "Key Fragment": 222.0,
    "Shiny Stone Fragment": 89.0,
    "Bicycle Fragment": 178.0,
    "Bronze Boss Token": 3.0,
}
HUNTS = [("out_water", "Goldeen", 150, 116), ("out_fire", "Vulpix", 150, 4)]


def test_final_form_evolves_up_to_the_level():
    assert final_form(PROFILE, RAW, 150)["speciesId"] == 2
    assert final_form(PROFILE, RAW, 11)["speciesId"] == 1  # evolui no 12
    assert final_form(PROFILE, RAW, 150)["level"] == 150


def test_item_value_per_kill():
    gems, items = item_value(PRICES, 1.0)
    frag = FRAGMENT_CHANCE * (222 + 89 + 178)
    assert gems == pytest.approx((frag + TOKEN_CHANCE * 3) * (1 - COMMISSION))
    assert items == pytest.approx(3 * FRAGMENT_CHANCE + TOKEN_CHANCE)
    top, _ = item_value(PRICES, 8.0)  # só os fragmentos escalam com o tier
    assert top == pytest.approx((8 * frag + TOKEN_CHANCE * 3) * (1 - COMMISSION))
    assert item_value({}, 1.0)[0] == 0  # sem preço não conta


def test_tier_mults_from_rules_or_default():
    assert tier_mults({}) == (1.0, 8.0)
    assert tier_mults({"outlandTiers": [{"n": 1, "multDrop": 1}, {"n": 8, "multDrop": 8}]}) == (
        1.0,
        8.0,
    )
    assert tier_mults({"outlandTiers": [1, 1.25, 3]}) == (1.0, 3.0)
    assert tier_mults({"outlandTiers": "?"}) == (1.0, 8.0)


def test_outland_options_rank_by_gems():
    proj, opts = outland_options(HUNTS, PROFILE, RAW, RULES, PRICES, n_kills=20)
    assert proj["speciesId"] == 2 and opts
    assert opts[0].slug == "out_water"  # Grama contra Água: mais abates por hora
    o = opts[0]
    assert o.gems_per_hour == pytest.approx(o.kills_per_hour * item_value(PRICES, 1.0)[0])
    assert o.gems_per_hour_top > o.gems_per_hour


async def test_compute_outland_uses_real_sale_medians():
    store = MemoryStore()
    store.reference = {
        "Key Fragment": {"median": 222.0},
        "shiny stone fragment": {"median": 89.0},  # o nome casa sem diferenciar maiúsculas
        "Water Stone": {"median": 2.0},
    }
    hunts = {
        "out_water": SimpleNamespace(
            slug="out_water",
            name=None,
            species_name="Goldeen",
            level=150,
            species_id=116,
            area="outland",
        ),
        "kanto_water": SimpleNamespace(
            slug="kanto_water",
            name=None,
            species_name="Goldeen",
            level=10,
            species_id=116,
            area="kanto",
        ),
    }
    state = AccountStateView(level=40)
    state.active_pokemon = PROFILE

    async def send(_p):
        return None

    async def record(_t, _d):
        return None

    ctx = PluginContext(
        account_id=uuid4(),
        nick="farm1",
        config=None,
        bus=EventBus(),
        actions=ActionGateway(
            "a",
            ActionMode.ENABLED,
            send=send,
            record=record,
            limiter=RateLimiter(clock=lambda: NOW.timestamp()),
        ),
        state=state,
        store=store,
        settings=None,
        log=logging.getLogger("t"),
        catalog=SimpleNamespace(hunts=hunts, rules=RULES),
        species=SimpleNamespace(raw=RAW),
    )
    pot = await compute_outland(ctx, NOW)
    assert pot["hunts"] == 1 and [o["slug"] for o in pot["options"]] == ["out_water"]
    assert pot["prices"]["Key Fragment"]["gems"] == 222.0
    assert pot["prices"]["Shiny Stone Fragment"]["gems"] == 89.0
    assert pot["prices"]["Bicycle Fragment"]["gems"] is None
    assert pot["active_species_id"] == 2 and pot["top_tier_mult"] == 8.0
