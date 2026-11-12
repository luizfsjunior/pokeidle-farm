"""Sorteios de captura, conforme a seção 14 dos Termos do pokeidle.io
(versão de 2026-10-12, revisada em 2026-11-07).

Usados pelo simulador e, no futuro, para calcular chances de objetivos
(ex.: "quantas capturas até um Dratini qualidade ≥ 1,5").
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# Potência: (nível, peso em %, bônus de atributos)
POTENCY_TABLE: tuple[tuple[int, float, float], ...] = (
    (1, 74.495, 0.00),
    (2, 20.0, 0.05),
    (3, 5.0, 0.10),
    (4, 0.5, 0.25),
    (5, 0.005, 1.00),
)

# Qualidade: (mínimo, máximo, peso em %). Dentro da faixa, uniforme com 3 casas.
# Observação: os Termos não listam a faixa 1,6–1,7; as chances listadas já
# somam 100%, então ela não é sorteada aqui.
QUALITY_TABLE: tuple[tuple[float, float, float], ...] = (
    (0.8, 0.9, 5.0),
    (0.9, 1.0, 5.0),
    (1.0, 1.1, 34.03846),
    (1.1, 1.2, 20.0),
    (1.2, 1.3, 10.0),
    (1.3, 1.4, 10.0),
    (1.4, 1.5, 10.0),
    (1.5, 1.6, 5.0),
    (1.7, 1.8, 0.67308),
    (1.8, 1.8, 0.28846),  # exatamente 1,8
)

IV_STATS = ("hp", "atk", "def", "spa", "spd", "spe")
IV_MIN, IV_MAX = 1, 32
SHINY_IV_SUM_FLOOR = 110  # num shiny, os IVs são sorteados de novo até a soma passar disto
SHINY_ODDS = 24_000


@dataclass(frozen=True)
class CaptureRoll:
    shiny: bool
    potency: int
    quality: float
    ivs: dict[str, int]

    @property
    def iv_sum(self) -> int:
        return sum(self.ivs.values())


def roll_potency(rng: random.Random) -> int:
    levels = [p[0] for p in POTENCY_TABLE]
    weights = [p[1] for p in POTENCY_TABLE]
    return rng.choices(levels, weights=weights, k=1)[0]


def roll_quality(rng: random.Random) -> float:
    lo, hi, _ = rng.choices(QUALITY_TABLE, weights=[q[2] for q in QUALITY_TABLE], k=1)[0]
    if lo == hi:
        return lo
    # "qualquer valor tem a mesma chance (com três casas decimais)"
    steps = round((hi - lo) * 1000)
    return round(lo + rng.randrange(steps + 1) / 1000, 3)


def roll_ivs(rng: random.Random, *, shiny: bool) -> dict[str, int]:
    while True:
        ivs = {s: rng.randint(IV_MIN, IV_MAX) for s in IV_STATS}
        if not shiny or sum(ivs.values()) > SHINY_IV_SUM_FLOOR:
            return ivs


def roll_capture(
    rng: random.Random, *, shiny_odds: int = SHINY_ODDS, can_be_shiny: bool = True
) -> CaptureRoll:
    shiny = can_be_shiny and rng.randrange(shiny_odds) == 0
    return CaptureRoll(
        shiny=shiny,
        potency=roll_potency(rng),
        quality=roll_quality(rng),
        ivs=roll_ivs(rng, shiny=shiny),
    )
