"""Simulador, camada 1 (docs/design/simulador-1-combate.md)."""

import random

from pokeidle_farm.model.combat import (
    STATS,
    Fighter,
    Move,
    Rules,
    SpeciesData,
    WaveModel,
    cooldown_of_power,
    effectiveness,
    hit_damage,
    kills_per_hour,
    random_wild,
    speed_discount_pct,
)

TABLE = {
    "GRASS": {"WATER": 2, "GROUND": 2, "ROCK": 2, "FIRE": 0.5, "POISON": 0.5, "FLYING": 0.5},
    "WATER": {"FIRE": 2, "GRASS": 0.5},
    "NORMAL": {"ROCK": 0.5, "GHOST": 0},
}
RULES = Rules(table=TABLE, potencies=((0.0, 100.0),))


def _species(pid, types, base, moves=()):
    keys = dict(zip(STATS, base, strict=True))
    return SpeciesData(id=pid, name=str(pid), types=types, base=keys, moves=tuple(moves))


BULBA = _species(
    1,
    ("GRASS", "POISON"),
    (45, 49, 49, 65, 65, 45),
    [
        Move("Razor Leaf", 56, "GRASS", "SPECIAL", 19600),
        Move("Bullet Seed", 120, "GRASS", "SPECIAL", 31200, 16),
    ],
)
WATER_MON = _species(116, ("WATER",), (30, 40, 70, 70, 25, 60))
FIRE_MON = _species(4, ("FIRE",), (39, 52, 43, 60, 50, 65))


def test_stats_match_the_game():
    # o Bulbasaur da conta: nível 23, IV 27, qualidade 1,6 (inicial), potência P2 (+5%)
    st = Fighter(BULBA, 23, {s: 27 for s in STATS}, 1.6, 1.05).stats()
    assert st["atk"] == 36 and st["spAtk"] == 42


def test_cooldown_curve():
    assert cooldown_of_power(15) == 10_000
    assert cooldown_of_power(100) == 30_000
    assert cooldown_of_power(600) == 60_000
    assert cooldown_of_power(1) == 10_000  # poder mínimo 15


def test_speed_discount():
    assert speed_discount_pct(200, 32) == 7.0  # teto
    assert speed_discount_pct(60, 32) == 3.0
    assert speed_discount_pct(60, 16) == 1.5


def test_damage_formula_and_hunt_effectiveness():
    # ((2*10/5+2)*50*1)/50+2 = 8; × STAB 1,5 × aleatório médio 0,925
    assert abs(hit_damage(10, 50, 20, 20, True, 1.0) - 8 * 1.5 * 0.925) < 1e-9
    assert effectiveness("GRASS", ("WATER",), TABLE, 1.5) == 2.5  # 1 + (2-1)·1,5
    assert effectiveness("GRASS", ("FIRE",), TABLE, 1.5) == 0.5 / 1.5
    assert effectiveness("GRASS", ("GRASS",), TABLE, 1.5) == 0.5 / 1.5  # diagonal
    assert effectiveness("NORMAL", ("GHOST",), TABLE, 1.5) == 0


def test_wild_follows_game_distribution():
    rng = random.Random(1)
    wilds = [random_wild(WATER_MON, 10, RULES, rng) for _ in range(2000)]
    qs = [w.quality for w in wilds]
    assert 0.8 <= min(qs) and max(qs) <= 1.8
    assert all(not (1.6 < q < 1.7) for q in qs)  # buraco intencional da tabela
    assert all(1 <= w.ivs["atk"] <= 32 for w in wilds)


def test_type_advantage_orders_hunts():
    me = Fighter(BULBA, 23, {s: 27 for s in STATS}, 1.6, 1.05)
    water = kills_per_hour(me, WATER_MON, 10, RULES)
    fire = kills_per_hour(me, FIRE_MON, 10, RULES)
    assert water > 3 * fire


def test_ceiling_is_the_wave_rhythm():
    me = Fighter(BULBA, 100, {s: 32 for s in STATS}, 1.8, 2.0)
    waves = WaveModel(size=8, walk_s=2.0, gap_s=11.0)
    kph = kills_per_hour(me, WATER_MON, 1, RULES, waves)
    # um golpe por selvagem: 8 × (2 s de caminhada) + 11 s de espera por onda
    assert abs(kph - 8 * 3600 / (8 * 2.0 + 11.0)) < 1


def test_higher_level_is_faster():
    lo = kills_per_hour(Fighter(BULBA, 16, {s: 27 for s in STATS}, 1.6), FIRE_MON, 20, RULES)
    hi = kills_per_hour(Fighter(BULBA, 30, {s: 27 for s in STATS}, 1.6), FIRE_MON, 20, RULES)
    assert hi > lo


def test_species_from_raw_reads_moves():
    sp = SpeciesData.from_raw(
        {
            "pokeId": 1,
            "name": "Bulbasaur",
            "type1": "grass",
            "type2": "poison",
            "baseHp": 45,
            "attacks": [
                {
                    "name": "Tackle",
                    "power": 56,
                    "type": "NORMAL",
                    "category": "PHYSICAL",
                    "cooldownMs": 19600,
                    "learnLevel": 1,
                },
                {"name": "Growl", "power": 0},
            ],
        }
    )
    assert sp.types == ("GRASS", "POISON") and sp.base["hp"] == 45
    assert [m.name for m in sp.moves] == ["Tackle"]
