"""Simulador, camada 2 (docs/design/simulador-2-progressao.md) e o Progress do foco XP."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode, PokemonEvolve, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.model.progression import (
    Account,
    Bonus,
    HuntRef,
    gold_per_kill,
    plan_to,
)
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.progress import Progress, bonuses_from_state, farm_pct_from_event
from pokeidle_farm.store.memory import MemoryStore
from pokeidle_farm.xp_model import total_xp

STATS = ("hp", "atk", "def", "spAtk", "spDef", "speed")
KEYS = ("baseHp", "baseAtk", "baseDef", "baseSpAtk", "baseSpDef", "baseSpeed")
NOW = datetime(2026, 11, 16, tzinfo=UTC)


def _raw(pid, t1, base, attacks=(), to=None, evo=None):
    return {
        "pokeId": pid,
        "type1": t1,
        **dict(zip(KEYS, base, strict=True)),
        "attacks": list(attacks),
        "evolvesToId": to,
        "evolveLevel": evo,
    }


LEAF = {
    "name": "Razor Leaf",
    "power": 56,
    "type": "GRASS",
    "category": "SPECIAL",
    "cooldownMs": 19600,
    "learnLevel": 1,
}
BIG = {
    "name": "Solar Beam",
    "power": 160,
    "type": "GRASS",
    "category": "SPECIAL",
    "cooldownMs": 33600,
    "learnLevel": 1,
}
RAW = {
    1: _raw(1, "GRASS", (45, 49, 49, 65, 65, 45), [LEAF], to=2, evo=12),
    2: _raw(2, "GRASS", (80, 82, 83, 100, 100, 80), [LEAF, BIG]),
    116: _raw(116, "WATER", (30, 40, 70, 70, 25, 60)),
    4: _raw(4, "FIRE", (39, 52, 43, 60, 50, 65)),
}
RULES = {
    "tabelaTipos": {
        "GRASS": {"WATER": 2, "FIRE": 0.5},
        "WATER": {"FIRE": 2, "GRASS": 0.5},
        "FIRE": {"GRASS": 2, "WATER": 0.5},
    },
    "ampliacaoHunt": 1.5,
    "multHpSelvagem": 5,
    "multDanoSelvagem": 1.8,
    "potencias": [{"n": 1, "bonus": 0, "chance": 100}],
}
HUNTS = [
    HuntRef("water1", 1, 116),
    HuntRef("fire1", 1, 4),
    HuntRef("water10", 10, 116),
    HuntRef("fire10", 10, 4),
]


def _account(level=5, stones=None, bonuses=()):
    prof = {
        "speciesId": 1,
        "level": level,
        "ivs": {s: 27 for s in STATS},
        "quality": 1.6,
        "potencia": 1,
    }
    return Account(level, total_xp(level), prof, total_xp(level), stones or {}, bonuses)


def test_gold_per_kill_matches_the_game_curve():
    assert round(gold_per_kill(1)) == round(36 * 1.15)
    assert 240 < gold_per_kill(20) < 260  # medido na Kabuto: ~250 por abate


def test_plan_reaches_goal_on_type_advantage_and_evolves():
    plan = plan_to(20, _account(stones={"Leaf Stone": 1}), HUNTS, RAW, RULES, NOW, n_kills=30)
    assert plan.stuck_at is None and plan.hours > 0
    assert {p.hunt for p in plan.phases} <= {"water1", "water10"}  # vantagem de tipo
    assert plan.evolutions == [{"level": 12, "from": 1, "to": 2, "stone": "Leaf Stone"}]
    assert plan.phases[-1].to_level == 20 and plan.phases[0].from_level == 5
    d = plan.as_dict(NOW)
    assert datetime.fromisoformat(d["eta"]) > NOW


def test_without_stone_there_is_no_evolution_and_it_is_slower():
    with_stone = plan_to(20, _account(stones={"Leaf Stone": 1}), HUNTS, RAW, RULES, NOW, n_kills=30)
    without = plan_to(20, _account(), HUNTS, RAW, RULES, NOW, n_kills=30)
    assert without.evolutions == [] and without.hours > with_stone.hours


def test_bonus_counts_until_it_expires():
    forever = plan_to(15, _account(bonuses=(Bonus(2.0, None),)), HUNTS, RAW, RULES, NOW, n_kills=30)
    none = plan_to(15, _account(), HUNTS, RAW, RULES, NOW, n_kills=30)
    assert abs(none.hours / forever.hours - 2.0) < 0.01
    soon = Bonus(2.0, NOW + timedelta(minutes=1))
    expiring = plan_to(15, _account(bonuses=(soon,)), HUNTS, RAW, RULES, NOW, n_kills=30)
    assert forever.hours < expiring.hours <= none.hours


def test_hunts_that_lose_gold_are_skipped():
    # só a hunt de fogo (desvantagem): ou se paga, ou o plano trava ali
    plan = plan_to(12, _account(), [HuntRef("fire1", 1, 4)], RAW, RULES, NOW, n_kills=30)
    for p in plan.phases:
        assert p.net_gold_per_hour >= 0


def test_bonuses_and_event_from_state():
    b = bonuses_from_state(
        {
            "tr": 2.1,
            "partes": [
                {"id": "vip", "tr": 1.5, "ate": 1797118357218},
                {"id": "evento", "tr": 1.4, "ate": None},
            ],
        }
    )
    assert [x.mult for x in b] == [1.5, 1.4] and b[0].until.year == 2026 and b[1].until is None
    ev = {"farmPct": 5, "terminaEm": int((NOW + timedelta(hours=1)).timestamp() * 1000)}
    assert farm_pct_from_event(ev, NOW) == 5
    assert farm_pct_from_event(ev, NOW + timedelta(hours=2)) == 0
    assert farm_pct_from_event(None, NOW) == 0


def test_evolve_wire():
    assert PokemonEvolve(pokemon_id=7, target_id=2).to_wire() == {
        "t": "pokemon.evoluir",
        "pokemonId": 7,
        "alvoId": 2,
    }


class _Species:
    raw = RAW


class _Store(MemoryStore):
    async def stone_items(self) -> dict[int, str]:
        return {76: "Leaf Stone"}


def _ctx(level: int, items: dict[str, int], sent: list[dict[str, Any]]) -> PluginContext:
    async def send(payload: dict[str, Any]) -> None:
        sent.append(payload)

    async def record(_t: str, _d: dict[str, Any]) -> None:
        return None

    state = AccountStateView(level=level, items=items)
    state.active_pokemon = {"id": 7, "speciesId": 1, "level": level}
    return PluginContext(
        account_id=uuid4(),
        nick="farm1",
        config=None,
        bus=EventBus(),
        actions=ActionGateway(
            "acc",
            ActionMode.ENABLED,
            send=send,
            record=record,
            limiter=RateLimiter(clock=lambda: NOW.timestamp()),
        ),
        state=state,
        store=_Store(),
        settings=None,
        log=logging.getLogger("t"),
        species=_Species(),
    )


async def test_evolves_when_level_and_stone_are_there_once():
    sent: list[dict[str, Any]] = []
    p = Progress(_ctx(12, {"76": 1}, sent), source="gems", now=lambda: NOW)
    await p.maybe_evolve()
    await p.maybe_evolve()  # não repete antes de evolve_retry_min
    assert sent == [{"t": "pokemon.evoluir", "pokemonId": 7, "alvoId": 2}]


async def test_does_not_evolve_without_stone_or_level():
    sent: list[dict[str, Any]] = []
    await Progress(_ctx(12, {}, sent), source="gems", now=lambda: NOW).maybe_evolve()
    await Progress(_ctx(11, {"76": 1}, sent), source="gems", now=lambda: NOW).maybe_evolve()
    assert sent == []
