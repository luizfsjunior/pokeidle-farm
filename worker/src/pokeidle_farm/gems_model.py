"""Valor esperado em gemas de cada hunt (foco gemas; análise de 15/11, proposta B).

Ver docs/design/foco-gemas-e-ritmo.md. Do código público do jogo (`/shared/loot-pedras.mjs` e
`pedras-evolucao.mjs`, v1.420.0):

- todo selvagem pode dropar a pedra de evolução de cada um dos seus tipos;
- a chance por abate depende da posição na cadeia evolutiva: 0,2% (1º), 0,35% (2º) e 0,5%
  (3º, ou espécie sem evolução). Conferido no Magikarp: 0,26% em 4.260 abates.

Gemas por hora de uma hunt = abates/h × Σ (chance da pedra × preço médio em gemas), com um
teto de liquidez: de cada pedra só conta até `max_share` do que o Mercado vende por semana
(menos o que as outras contas já tiram dela).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .gamedata import HuntCatalog, SpeciesCatalog

# chance por abate (o jogo guarda 200/350/500 em milésimos de porcento)
STONE_CHANCE_BY_POSITION: tuple[float, float, float] = (0.002, 0.0035, 0.005)

STONE_BY_TYPE: dict[str, str] = {
    "NORMAL": "Sun Stone",
    "FIRE": "Fire Stone",
    "WATER": "Water Stone",
    "GRASS": "Leaf Stone",
    "ELECTRIC": "Thunder Stone",
    "ICE": "Ice Stone",
    "FIGHTING": "Punch Stone",
    "POISON": "Venom Stone",
    "GROUND": "Earth Stone",
    "FLYING": "Feather Stone",
    "PSYCHIC": "Enigma Stone",
    "BUG": "Cocoon Stone",
    "ROCK": "Rock Stone",
    "GHOST": "Darkness Stone",
    "DRAGON": "Ancient Stone",
    "DARK": "Darkness Stone",
    "STEEL": "Metal Stone",
    "FAIRY": "Heart Stone",
}

HOURS_PER_WEEK = 168


@dataclass(frozen=True)
class StonePrice:
    gems: float  # média de 7 dias em gemas
    sold_week: float  # unidades vendidas por semana no Mercado


@dataclass(frozen=True)
class StoneYield:
    name: str
    chance: float  # por abate
    gems: float | None
    sold_week: float | None
    per_week: float  # unidades por semana a esse ritmo (24 h/dia)
    counted_week: float  # quantas contam depois do teto de liquidez


@dataclass(frozen=True)
class GemOption:
    slug: str
    name: str | None
    level: int
    kills_per_hour: float
    kph_source: str  # "measured" | "level" | "default"
    stones: tuple[StoneYield, ...] = field(default_factory=tuple)
    gems_per_hour: float = 0.0  # sem teto
    capped_gems_per_hour: float = 0.0  # com o teto de liquidez


def chain_position(species: SpeciesCatalog, species_id: int) -> int:
    """0, 1 ou 2 como no `estagioDaPedra` do jogo; sem evolução nenhuma conta como 2."""
    sp = species.species.get(species_id)
    if sp is None:
        return 2
    parents = {s.evolves_to: s.id for s in species.species.values() if s.evolves_to}
    depth, cur, seen = 0, species_id, set()
    while cur in parents and cur not in seen:
        seen.add(cur)
        cur = parents[cur]
        depth += 1
    if depth == 0 and not sp.evolves_to:
        return 2
    return min(depth, 2)


def stones_of(
    species: SpeciesCatalog, species_id: int, by_type: dict[str, str] | None = None
) -> list[str]:
    sp = species.species.get(species_id)
    if sp is None:
        return []
    table = by_type or STONE_BY_TYPE
    out: list[str] = []
    for t in (sp.type1, sp.type2):
        stone = table.get(str(t).upper()) if t else None
        if stone and stone not in out:
            out.append(stone)
    return out


def rank_options(
    hunts: HuntCatalog,
    species: SpeciesCatalog,
    trainer_level: int,
    rate: dict[str, tuple[float, str]],
    prices: dict[str, StonePrice],
    *,
    max_share: float = 0.10,
    taken_week: dict[str, float] | None = None,
    chances: tuple[float, float, float] = STONE_CHANCE_BY_POSITION,
    by_type: dict[str, str] | None = None,
) -> list[GemOption]:
    """Hunts alcançáveis ordenadas por gemas/h com o teto de liquidez.

    `rate`: slug -> (abates/h, origem); hunt sem ritmo fica de fora.
    `taken_week`: pedra -> unidades por semana que outras contas já tiram.
    """
    taken = taken_week or {}
    out: list[GemOption] = []
    for h in hunts.hunts.values():
        if h.level > trainer_level or h.slug not in rate:
            continue
        kph, source = rate[h.slug]
        if kph <= 0:
            continue
        chance = chances[chain_position(species, h.species_id)]
        yields: list[StoneYield] = []
        raw = capped = 0.0
        for stone in stones_of(species, h.species_id, by_type):
            p = prices.get(stone)
            per_week = kph * chance * HOURS_PER_WEEK
            if p is None:
                yields.append(StoneYield(stone, chance, None, None, per_week, 0.0))
                continue
            room = max(0.0, max_share * p.sold_week - taken.get(stone, 0.0))
            counted = min(per_week, room)
            raw += kph * chance * p.gems
            capped += counted / HOURS_PER_WEEK * p.gems
            yields.append(StoneYield(stone, chance, p.gems, p.sold_week, per_week, counted))
        out.append(
            GemOption(
                slug=h.slug,
                name=h.species_name or h.name,
                level=h.level,
                kills_per_hour=kph,
                kph_source=source,
                stones=tuple(yields),
                gems_per_hour=raw,
                capped_gems_per_hour=capped,
            )
        )
    out.sort(key=lambda o: (-o.capped_gems_per_hour, -o.gems_per_hour, o.slug))
    return out


def option_dict(o: GemOption) -> dict[str, Any]:
    return {
        "slug": o.slug,
        "name": o.name,
        "level": o.level,
        "kills_per_hour": round(o.kills_per_hour, 1),
        "kph_source": o.kph_source,
        "gems_per_hour": round(o.gems_per_hour, 2),
        "capped_gems_per_hour": round(o.capped_gems_per_hour, 2),
        "stones": [
            {
                "name": s.name,
                "chance": s.chance,
                "gems": s.gems,
                "sold_week": s.sold_week,
                "per_week": round(s.per_week, 1),
                "counted_week": round(s.counted_week, 1),
            }
            for s in o.stones
        ],
    }
