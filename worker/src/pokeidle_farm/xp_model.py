"""XP por hora de cada hunt (foco XP; docs/design/foco-xp.md).

Do código público do jogo (`/shared/sell-value.mjs`, `xpDoNivel`): a XP de um abate é
⌊0,6 × nível do selvagem²⌋ + 8 até o nível 150 (acima disso, 0,6 × 150² × (n/150)^1,25), a mesma
para o treinador e para o pokémon ativo, multiplicada pelos bônus (VIP, XP Boost, evento...).

XP/h da hunt = abates/h projetados (ritmo pelo nível do ativo) × XP por abate:
- medida na própria hunt quando ela tem `min_kills` abates (já vem com os bônus);
- senão, a fórmula × o bônus medido da conta (XP real ÷ XP da fórmula nas hunts medidas).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .gamedata import HuntCatalog

ANCHOR_LEVEL = 150


def base_xp(level: int) -> float:
    """XP de um abate de um selvagem desse nível, sem bônus (xpDoNivel do jogo)."""
    n = max(1, int(level))
    if n <= ANCHOR_LEVEL:
        return math.floor(6 * n * n / 10) + 8
    return round(0.6 * ANCHOR_LEVEL**2 * (n / ANCHOR_LEVEL) ** 1.25)


def total_xp(level: int) -> int:
    """XP total para chegar ao nível do treinador (curva da wiki: 50/3·(L³ − 6L² + 17L − 12))."""
    lv = max(1, int(level))
    return round(50 / 3 * (lv**3 - 6 * lv**2 + 17 * lv - 12))


@dataclass(frozen=True)
class XpOption:
    slug: str
    name: str | None
    level: int
    kills_per_hour: float
    kph_source: str
    xp_per_kill: float
    xp_source: str  # "measured" | "formula"
    xp_per_hour: float


def account_bonus(
    xp_book: dict[str, tuple[float, float]], levels: dict[str, int], min_kills: int
) -> float:
    """XP real ÷ XP da fórmula nas hunts com abates suficientes (1,0 sem dado)."""
    real = formula = 0.0
    for slug, (xp, kills) in xp_book.items():
        if kills >= min_kills and slug in levels and xp > 0:
            real += xp
            formula += kills * base_xp(levels[slug])
    return real / formula if formula > 0 else 1.0


def xp_options(
    hunts: HuntCatalog,
    trainer_level: int,
    rate: dict[str, tuple[float, str]],
    xp_book: dict[str, tuple[float, float]],
    *,
    min_kills: int = 30,
) -> list[XpOption]:
    """Hunts alcançáveis ordenadas por XP/h. `xp_book`: slug -> (XP total, abates)."""
    levels = {s: h.level for s, h in hunts.hunts.items()}
    bonus = account_bonus(xp_book, levels, min_kills)
    out: list[XpOption] = []
    for h in hunts.hunts.values():
        if h.level > trainer_level or h.slug not in rate:
            continue
        kph, source = rate[h.slug]
        if kph <= 0:
            continue
        xp, kills = xp_book.get(h.slug, (0.0, 0.0))
        if kills >= min_kills and xp > 0:
            xpk, xp_src = xp / kills, "measured"
        else:
            xpk, xp_src = base_xp(h.level) * bonus, "formula"
        out.append(
            XpOption(
                slug=h.slug,
                name=h.species_name or h.name,
                level=h.level,
                kills_per_hour=kph,
                kph_source=source,
                xp_per_kill=xpk,
                xp_source=xp_src,
                xp_per_hour=kph * xpk,
            )
        )
    out.sort(key=lambda o: (-o.xp_per_hour, o.slug))
    return out


def xp_option_dict(o: XpOption) -> dict[str, Any]:
    d = asdict(o)
    for k in ("kills_per_hour", "xp_per_kill", "xp_per_hour"):
        d[k] = round(d[k], 1)
    return d
