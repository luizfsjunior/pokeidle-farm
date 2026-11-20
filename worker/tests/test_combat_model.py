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


def test_rates_for_prefers_model_over_level_guess():
    from pokeidle_farm.pace import PaceBook, rates_for

    pace = PaceBook(5.0)
    pace.load("horsea", 600, 60, 23)
    levels = {"horsea": 10, "krabby": 10, "kabuto": 20}
    out = rates_for(levels, pace, 300.0, 23, {"kabuto": 406.0, "horsea": 1.0})
    assert out["horsea"][1] == "measured"  # o medido continua valendo
    assert out["kabuto"] == (406.0, "model")
    assert out["krabby"][1] == "level"  # sem previsão: cai no ritmo do mesmo nível


def _raw(pid, t1, t2, base, attacks=()):
    keys = ("baseHp", "baseAtk", "baseDef", "baseSpAtk", "baseSpDef", "baseSpeed")
    return {
        "pokeId": pid,
        "type1": t1,
        "type2": t2,
        **dict(zip(keys, base, strict=True)),
        "attacks": list(attacks),
    }


RAW = {
    1: _raw(
        1,
        "GRASS",
        "POISON",
        (45, 49, 49, 65, 65, 45),
        [
            {
                "name": "Razor Leaf",
                "power": 56,
                "type": "GRASS",
                "category": "SPECIAL",
                "cooldownMs": 19600,
                "learnLevel": 1,
            }
        ],
    ),
    116: _raw(116, "WATER", None, (30, 40, 70, 70, 25, 60)),
    4: _raw(4, "FIRE", None, (39, 52, 43, 60, 50, 65)),
}
WELCOME_RULES = {
    "tabelaTipos": TABLE,
    "ampliacaoHunt": 1.5,
    "multHpSelvagem": 5,
    "potencias": [{"n": 1, "bonus": 0, "chance": 100}, {"n": 2, "bonus": 0.05}],
}
PROFILE = {
    "speciesId": 1,
    "level": 23,
    "ivs": {s: 27 for s in STATS},
    "quality": 1.6,
    "potencia": 2,
}


def test_fighter_from_profile_matches_game_stats():
    from pokeidle_farm.model.predict import fighter_from_profile

    f = fighter_from_profile(PROFILE, RAW, WELCOME_RULES)
    assert f is not None and f.multiplier == 1.05
    assert f.stats()["atk"] == 36 and f.stats()["spAtk"] == 42
    assert fighter_from_profile({"speciesId": 999, "level": 5}, RAW, WELCOME_RULES) is None


def test_model_rates_orders_by_type_and_caches():
    from pokeidle_farm.model.predict import ModelRates

    m = ModelRates(n_kills=60)
    hunts = {"horsea": (10, 116), "charmander": (10, 4), "alto": (90, 4)}
    out = m.rates(hunts, PROFILE, RAW, WELCOME_RULES, max_level=24)
    assert set(out) == {"horsea", "charmander"}  # acima do treinador fica de fora
    assert out["horsea"] > 3 * out["charmander"]
    m._cache["horsea"] = 1.0
    assert m.rates(hunts, PROFILE, RAW, WELCOME_RULES, max_level=24)["horsea"] == 1.0  # cache
    same_band = {**PROFILE, "level": 24}  # 23 e 24 estão na faixa 20-29: o cache vale
    assert m.rates(hunts, same_band, RAW, WELCOME_RULES, max_level=24)["horsea"] == 1.0
    up = {**PROFILE, "level": 31}
    assert (
        m.rates(hunts, up, RAW, WELCOME_RULES, max_level=24)["horsea"] > 1.0
    )  # outra faixa: recalcula
    # sem simular: devolve o que está em cache e conta o que falta
    fresh = ModelRates(n_kills=60)
    assert fresh.rates(hunts, PROFILE, RAW, WELCOME_RULES, max_level=24, compute=False) == {}
    assert fresh.missing == 2
    assert m.rates(hunts, None, RAW, WELCOME_RULES) == {}
    assert m.rates(hunts, PROFILE, RAW, {}) == {}  # sem tabela de tipos


def test_season_day_multiplies_damage_both_ways():
    from dataclasses import replace

    from pokeidle_farm.model.combat import season_factor

    assert season_factor(None, ("GRASS",), ("WATER",)) == 1.0
    assert season_factor("GRASS", ("GRASS", "POISON"), ("WATER",)) == 2.0  # bate ×2
    assert season_factor("WATER", ("GRASS",), ("WATER",)) == 0.25  # o selvagem do dia apanha ÷4
    me = Fighter(BULBA, 23, {s: 27 for s in STATS}, 1.6, 1.05)
    normal = kills_per_hour(me, FIRE_MON, 10, RULES)
    grass_day = kills_per_hour(me, FIRE_MON, 10, replace(RULES, season="GRASS"))
    fire_day = kills_per_hour(me, FIRE_MON, 10, replace(RULES, season="FIRE"))
    assert grass_day > normal > fire_day


def test_season_adjusts_measured_pace_only():
    from pokeidle_farm.model.predict import season_adjust

    rate = {"kabuto": (500.0, "measured"), "onix": (300.0, "model"), "geodude": (900.0, "measured")}
    normal = {"kabuto": 400.0, "onix": 300.0, "geodude": 1000.0}
    seasonal = {"kabuto": 100.0, "onix": 75.0, "geodude": 1000.0}  # dia de Pedra: Kabuto apanha ÷4
    out = season_adjust(rate, normal, seasonal)
    assert out["kabuto"] == (125.0, "measured_season")  # 500 × 100/400
    assert out["onix"] == (300.0, "model")  # a previsão já vem com o tipo do dia
    assert out["geodude"] == (900.0, "measured")  # o dia não muda essa hunt


def test_model_rates_keeps_both_season_caches():
    from pokeidle_farm.model.predict import ModelRates

    raw = {
        1: {
            "pokeId": 1,
            "type1": "GRASS",
            "baseHp": 45,
            "baseAtk": 49,
            "baseDef": 49,
            "baseSpAtk": 65,
            "baseSpDef": 65,
            "baseSpeed": 45,
            "attacks": [
                {
                    "name": "Razor Leaf",
                    "power": 56,
                    "type": "GRASS",
                    "category": "SPECIAL",
                    "cooldownMs": 19600,
                    "learnLevel": 1,
                }
            ],
        },
        116: {
            "pokeId": 116,
            "type1": "WATER",
            "baseHp": 30,
            "baseAtk": 40,
            "baseDef": 70,
            "baseSpAtk": 70,
            "baseSpDef": 25,
            "baseSpeed": 60,
        },
    }
    rules = {"tabelaTipos": TABLE, "potencias": [{"n": 1, "bonus": 0, "chance": 100}]}
    prof = {
        "speciesId": 1,
        "level": 20,
        "ivs": {s: 27 for s in STATS},
        "quality": 1.6,
        "potencia": 1,
    }
    m = ModelRates(n_kills=30)
    hunts = {"horsea": (10, 116)}
    normal = m.rates(hunts, prof, raw, rules)["horsea"]
    water = m.rates(hunts, prof, raw, rules, season="WATER")["horsea"]
    assert water < normal  # o Horsea do dia apanha ÷4
    assert len(m._caches) == 2
    assert m.rates(hunts, prof, raw, rules)["horsea"] == normal  # o cache normal continua lá
