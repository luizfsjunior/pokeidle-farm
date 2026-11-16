"""Simulador, camada 3: sorte da captura (docs/design/simulador-3-captura.md).

Regras do jogo (código público v1.420.0: `nota-pokemon.mjs`, `captura-degrau.mjs`, wiki Captura):
- cada abate deixa um corpo por 30 s e a automação joga 1 bola nele: capturas/h = abates/h × chance;
- chance = base × catchRate da bola ÷ fator do degrau da cadeia (20: 2,8669; 40: 3,5745; 100: 4,4681)
  × 1,4 (selvagem derrubado), entre o piso (0,3%) e o teto (10%) — a `CaptureTable` do catálogo;
- o nascimento tem três sorteios independentes que nunca mais mudam (evoluir não rerola): IV de 1 a 32
  em cada um dos seis stats, qualidade pelas faixas e potência pela tabela do `welcome`; shiny com a
  `chanceShiny` (1 em 24 mil), que triplica os stats;
- em Kanto o capturado nasce no nível da hunt.

O que este módulo responde: quanto tempo e ouro custa capturar a espécie X, e com que probabilidade o
nascimento sai bom o bastante (melhor que o ativo atual numa hunt de referência, no mesmo nível).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from .combat import QUALITY_BANDS, STATS, Fighter, Rules, SpeciesData, _pick, simulate_hunt


@dataclass(frozen=True)
class Birth:
    ivs: dict[str, int]
    quality: float
    potency: int
    shiny: bool

    def multiplier(self, potency_bonus: dict[int, float], shiny_mult: float = 3.0) -> float:
        m = 1 + potency_bonus.get(self.potency, 0.0)
        return m * (shiny_mult if self.shiny else 1.0)


def potency_table(rules_raw: dict[str, Any]) -> list[tuple[int, float, float]]:
    """(n, bônus, chance %) da tabela `potencias` do welcome."""
    out = []
    for p in rules_raw.get("potencias") or []:
        if isinstance(p, dict) and isinstance(p.get("n"), int):
            out.append((p["n"], float(p.get("bonus") or 0), float(p.get("chance") or 0)))
    return out or [(1, 0.0, 100.0)]


def roll_birth(rng: random.Random, rules_raw: dict[str, Any]) -> Birth:
    lo, hi = _pick(rng, [((a, b), w) for a, b, w in QUALITY_BANDS])
    pots = potency_table(rules_raw)
    n = _pick(rng, [(n, w) for n, _, w in pots])
    shiny = rng.random() < float(rules_raw.get("chanceShiny") or 0)
    return Birth(
        ivs={s: rng.randint(1, 32) for s in STATS},
        quality=round(rng.uniform(lo, hi), 3),
        potency=n,
        shiny=shiny,
    )


def form_at_level(sid: int, level: int, raw_species: dict[int, dict[str, Any]]) -> int:
    """A forma da cadeia em que a espécie estaria nesse nível (evoluindo assim que pode)."""
    seen = set()
    while sid in raw_species and sid not in seen:
        seen.add(sid)
        sp = raw_species[sid]
        to, lv = sp.get("evolvesToId"), int(sp.get("evolveLevel") or 0)
        if not to or to == sid or to not in raw_species or not lv or level < lv:
            break
        sid = int(to)
    return sid


def fighter_from_birth(
    sid: int,
    level: int,
    birth: Birth,
    raw_species: dict[int, dict[str, Any]],
    rules_raw: dict[str, Any],
    evolve: bool = True,
) -> Fighter:
    form = form_at_level(sid, level, raw_species) if evolve else sid
    bonus = {n: b for n, b, _ in potency_table(rules_raw)}
    return Fighter(
        species=SpeciesData.from_raw(raw_species[form]),
        level=level,
        ivs=dict(birth.ivs),
        quality=birth.quality,
        multiplier=birth.multiplier(bonus, float(rules_raw.get("multShinyStats") or 3)),
    )


@dataclass(frozen=True)
class CaptureOdds:
    chance: float  # por abate (1 bola por corpo)
    ball_price: int

    @property
    def kills_per_capture(self) -> float:
        return 1 / self.chance if self.chance > 0 else float("inf")

    @property
    def gold_per_capture(self) -> float:
        return self.ball_price * self.kills_per_capture

    def hours_per_capture(self, kills_per_hour: float) -> float:
        return self.kills_per_capture / kills_per_hour if kills_per_hour > 0 else float("inf")


@dataclass(frozen=True)
class CaptureOutcome:
    """Distribuição do que a captura rende numa hunt de referência, no nível de comparação."""

    species_id: int
    form_id: int
    level: int
    kph_quantiles: dict[str, float]  # p10, p50, p90, p99 dos abates/h na hunt de referência
    p_beats: float  # probabilidade de um nascimento render mais que `baseline_kph`
    baseline_kph: float


def outcome(
    sid: int,
    level: int,
    ref_wild: SpeciesData,
    ref_level: int,
    baseline_kph: float,
    raw_species: dict[int, dict[str, Any]],
    rules_raw: dict[str, Any],
    *,
    n_births: int = 200,
    n_kills: int = 40,
    seed: int = 11,
    evolve: bool = True,
) -> CaptureOutcome:
    """Monte Carlo: sorteia `n_births` nascimentos e simula cada um na hunt de referência."""
    rng = random.Random(seed)
    rules = Rules.from_welcome(rules_raw)
    kphs = []
    form = form_at_level(sid, level, raw_species) if evolve else sid
    for i in range(n_births):
        f = fighter_from_birth(
            sid, level, roll_birth(rng, rules_raw), raw_species, rules_raw, evolve
        )
        kphs.append(
            simulate_hunt(f, ref_wild, ref_level, rules, n_kills=n_kills, seed=i).kills_per_hour
        )
    kphs.sort()

    def q(p: float) -> float:
        return kphs[min(len(kphs) - 1, int(p * len(kphs)))]

    beats = sum(1 for k in kphs if k > baseline_kph) / len(kphs)
    return CaptureOutcome(
        species_id=sid,
        form_id=form,
        level=level,
        kph_quantiles={"p10": q(0.10), "p50": q(0.50), "p90": q(0.90), "p99": q(0.99)},
        p_beats=beats,
        baseline_kph=baseline_kph,
    )


@dataclass(frozen=True)
class CaptureOption:
    hunt: str
    species_id: int
    hunt_level: int
    odds: CaptureOdds
    hours_per_capture: float
    outcome: CaptureOutcome

    @property
    def captures_to_beat(self) -> float:
        p = self.outcome.p_beats
        return 1 / p if p > 0 else float("inf")

    @property
    def hours_to_beat(self) -> float:
        return self.hours_per_capture * self.captures_to_beat

    @property
    def gold_to_beat(self) -> float:
        return self.odds.gold_per_capture * self.captures_to_beat

    def as_dict(self) -> dict[str, Any]:
        o = self.outcome
        inf = float("inf")
        rnd = lambda v: None if v == inf else round(v, 2)  # noqa: E731
        return {
            "hunt": self.hunt,
            "species_id": self.species_id,
            "form_id": o.form_id,
            "hunt_level": self.hunt_level,
            "compare_level": o.level,
            "chance": round(self.odds.chance, 5),
            "hours_per_capture": rnd(self.hours_per_capture),
            "gold_per_capture": rnd(self.odds.gold_per_capture),
            "kph_quantiles": {k: round(v, 1) for k, v in o.kph_quantiles.items()},
            "baseline_kph": round(o.baseline_kph, 1),
            "p_beats": round(o.p_beats, 4),
            "hours_to_beat": rnd(self.hours_to_beat),
            "gold_to_beat": rnd(self.gold_to_beat),
        }


# --- nota do pokémon (nota-pokemon.mjs) e pontos do Sacrifício (sacrificio.mjs) ------------
# A nota (0 a 10) é a força de nascimento numa escala logarítmica entre o pior e o melhor
# nascimento possível da espécie (IV 32, qualidade 1,8, P5, shiny). Não depende do nível.
# Conferida contra a conta de teste (Bulbasaur 3,179; Zubat 1,334...). Sem os "ancestrais"
# (piso pela pré-evolução), que só sobe a nota de formas evoluídas.

_QUALITY_EXP = {"hp": 0.95, "speed": 0.95, "atk": 0.8, "def": 0.8, "spAtk": 0.8, "spDef": 0.8}
_POTENCY_BONUS = (0.0, 0.05, 0.1, 0.25, 1.0)
_REF_BASE = dict.fromkeys(STATS, 80.0)
SACRIFICE_POINTS = (  # (nota mínima, pontos)
    (3.5, 10),
    (3.6, 12),
    (3.7, 14),
    (3.8, 17),
    (3.9, 20),
    (4.0, 25),
    (4.1, 30),
    (4.2, 35),
    (4.3, 42),
    (4.4, 50),
    (4.5, 60),
    (4.6, 70),
    (4.7, 80),
    (4.8, 90),
    (4.9, 100),
    (5.0, 110),
    (5.1, 125),
    (5.2, 140),
    (5.3, 155),
    (5.4, 170),
    (5.5, 190),
    (5.6, 210),
    (5.7, 235),
    (5.8, 260),
    (5.9, 290),
    (6.0, 320),
    (6.1, 360),
    (6.2, 400),
    (6.3, 450),
    (6.4, 500),
    (6.5, 560),
    (6.6, 620),
    (6.7, 700),
    (6.8, 780),
    (6.9, 870),
    (7.0, 1000),
)


def _birth_sum(
    ivs: dict[str, int], q: float, potency: int, shiny: bool, base: dict[str, float]
) -> int:
    q = min(max(q, 0.8), 1.8)
    m = (1 + _POTENCY_BONUS[min(max(potency, 1), 5) - 1]) * (3 if shiny else 1)
    return sum(round((base[k] + 2 * ivs.get(k, 1)) * q ** _QUALITY_EXP[k] * m) for k in STATS)


def _limits(base: dict[str, float]) -> tuple[int, int]:
    lo = _birth_sum(dict.fromkeys(STATS, 1), 0.8, 1, False, base)
    hi = _birth_sum(dict.fromkeys(STATS, 32), 1.8, 5, True, base)
    return max(1, lo), max(lo + 1, hi)


_REF_LIMITS = _limits(_REF_BASE)


def _score(
    ivs: dict[str, int], q: float, potency: int, shiny: bool, base: dict[str, float]
) -> float:
    import math

    lo, hi = _REF_LIMITS
    s = min(max(_birth_sum(ivs, q, potency, shiny, base), lo), hi)
    raw = 10 * (math.log(max(1, s)) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return min(max(round(min(max(raw, 0), 10) * 1000) / 1000 / 10, 0), 1)


def pokemon_grade(
    ivs: dict[str, int], quality: float, potency: int, shiny: bool, base: dict[str, float]
) -> float:
    """A nota do jogo (0 a 10) de um nascimento, para os stats base da espécie."""
    mn = _score(dict.fromkeys(STATS, 1), 0.8, 1, False, base)
    mx = max(mn, _score(dict.fromkeys(STATS, 32), 1.8, 5, True, base))
    if mx <= mn:
        return 0.0
    s = min(max(_score(ivs, quality, potency, shiny, base), mn), mx)
    return round(10 * (s - mn) / (mx - mn) * 1000) / 1000


def sacrifice_points(grade: float) -> int:
    """Pontos do Sacrifício por uma nota (0 abaixo de 3,5)."""
    import math

    tenth = math.floor(round(grade * 1000) / 100)
    if tenth < 35:
        return 0
    return SACRIFICE_POINTS[min(tenth - 35, len(SACRIFICE_POINTS) - 1)][1]
