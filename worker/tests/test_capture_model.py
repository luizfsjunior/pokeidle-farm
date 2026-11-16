"""Simulador, camada 3: sorte da captura (docs/design/simulador-3-captura.md)."""

from __future__ import annotations

import random
import statistics

from pokeidle_farm.gamedata import CaptureTable
from pokeidle_farm.model.capture import (
    Birth,
    CaptureOdds,
    CaptureOption,
    fighter_from_birth,
    form_at_level,
    outcome,
    roll_birth,
)
from pokeidle_farm.model.combat import SpeciesData

KEYS = ("baseHp", "baseAtk", "baseDef", "baseSpAtk", "baseSpDef", "baseSpeed")
LEAF = {
    "name": "Razor Leaf",
    "power": 56,
    "type": "GRASS",
    "category": "SPECIAL",
    "cooldownMs": 19600,
    "learnLevel": 1,
}


def _raw(pid, t1, base, attacks=(), to=None, evo=None):
    return {
        "pokeId": pid,
        "type1": t1,
        **dict(zip(KEYS, base, strict=True)),
        "attacks": list(attacks),
        "evolvesToId": to,
        "evolveLevel": evo,
    }


RAW = {
    43: _raw(43, "GRASS", (45, 50, 55, 75, 65, 30), [LEAF], to=44, evo=20),
    44: _raw(44, "GRASS", (60, 65, 70, 85, 75, 40), [LEAF], to=45, evo=40),
    45: _raw(45, "GRASS", (75, 80, 85, 110, 90, 50), [LEAF]),
    116: _raw(116, "WATER", (30, 40, 70, 70, 25, 60)),
}
RULES = {
    "tabelaTipos": {"GRASS": {"WATER": 2}},
    "potencias": [
        {"n": 1, "bonus": 0, "chance": 74.495},
        {"n": 2, "bonus": 0.05, "chance": 20},
        {"n": 3, "bonus": 0.1, "chance": 5},
        {"n": 4, "bonus": 0.25, "chance": 0.5},
        {"n": 5, "bonus": 1, "chance": 0.005},
    ],
    "chanceShiny": 1 / 24000,
    "multShinyStats": 3,
}


def test_chance_matches_what_the_server_shows():
    # registrado nas tentativas da conta: Great Ball 0,7% e Super Ball 1,1% em cadeias de 3
    table = CaptureTable(base=0.0075, floor=0.003, ceiling=0.1, by_step=(2.8669, 3.5745, 4.4681))
    assert round(table.chance(2, "first_of_three"), 3) == 0.007
    assert round(table.chance(3, "first_of_three"), 3) == 0.011
    assert table.chance(0.01, "last") == 0.003  # piso


def test_births_follow_the_game_tables():
    rng = random.Random(3)
    births = [roll_birth(rng, RULES) for _ in range(20_000)]
    assert 1.15 < statistics.mean(b.quality for b in births) < 1.20
    assert 16.2 < statistics.mean(statistics.mean(b.ivs.values()) for b in births) < 16.8
    p1 = sum(b.potency == 1 for b in births) / len(births)
    assert 0.72 < p1 < 0.77
    assert all(not (1.6 < b.quality < 1.7) for b in births)  # buraco intencional


def test_birth_multiplier_potency_and_shiny():
    bonus = {1: 0.0, 2: 0.05, 5: 1.0}
    assert Birth({}, 1.0, 2, False).multiplier(bonus) == 1.05
    assert Birth({}, 1.0, 5, True).multiplier(bonus) == 6.0  # P5 (×2) e shiny (×3)


def test_form_at_level_follows_the_chain():
    assert form_at_level(43, 10, RAW) == 43
    assert form_at_level(43, 25, RAW) == 44
    assert form_at_level(43, 60, RAW) == 45
    birth = Birth({s: 16 for s in ("hp", "atk", "def", "spAtk", "spDef", "speed")}, 1.0, 1, False)
    assert fighter_from_birth(43, 60, birth, RAW, RULES).species.id == 45
    assert fighter_from_birth(43, 60, birth, RAW, RULES, evolve=False).species.id == 43


def test_odds_and_option_costs():
    odds = CaptureOdds(chance=0.01, ball_price=20)
    assert odds.kills_per_capture == 100 and odds.gold_per_capture == 2000
    assert odds.hours_per_capture(500) == 0.2
    wild = SpeciesData.from_raw(RAW[116])
    out = outcome(
        43,
        60,
        wild,
        10,
        baseline_kph=1.0,
        raw_species=RAW,
        rules_raw=RULES,
        n_births=20,
        n_kills=20,
    )
    assert out.p_beats == 1.0 and out.form_id == 45  # qualquer nascimento vence 1 abate/h
    opt = CaptureOption("oddish", 43, 1, odds, odds.hours_per_capture(500), out)
    assert opt.captures_to_beat == 1 and opt.hours_to_beat == 0.2
    hard = outcome(
        43,
        60,
        wild,
        10,
        baseline_kph=1e9,
        raw_species=RAW,
        rules_raw=RULES,
        n_births=10,
        n_kills=10,
    )
    d = CaptureOption("oddish", 43, 1, odds, 0.2, hard).as_dict()
    assert d["p_beats"] == 0 and d["hours_to_beat"] is None  # impossível: sem número
