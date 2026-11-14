"""Fila de hunts do foco rank, ordenada pelo tempo esperado até a captura.

Ver docs/design/fase-3b-catalogo-e-fila.md, seções 5 e 6. Funções puras: quem lê
eventos do banco e decide o que fazer é o plugin `rank`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .gamedata import HuntCatalog, SpeciesCatalog

ChanceSource = Literal["observed", "stage", "worst"]


@dataclass(frozen=True)
class QueueItem:
    slug: str
    species_id: int
    name: str | None
    level: int
    kills_per_hour: float
    chance: float
    hours: float
    chance_source: ChanceSource
    kph_known: bool


def plan_queue(
    hunts: HuntCatalog,
    species: SpeciesCatalog | None,
    trainer_level: int,
    scored_species: set[int],
    ball_id: int,
    kills_per_hour: dict[str, float],
    default_kills_per_hour: float,
    known_chance: dict[int, float],
) -> list[QueueItem]:
    ball = hunts.balls.get(ball_id)
    table = hunts.capture
    if ball is None or table is None or default_kills_per_hour <= 0:
        return []
    out: list[QueueItem] = []
    for h in hunts.hunts.values():
        if h.level > trainer_level or h.species_id in scored_species:
            continue
        source: ChanceSource
        if h.species_id in known_chance:
            chance, source = known_chance[h.species_id], "observed"
        elif species is not None and h.species_id in species.species:
            chance = table.chance(ball.catch_rate, species.species[h.species_id].stage)
            source = "stage"
        else:
            chance, source = table.chance(ball.catch_rate, None), "worst"
        kph = kills_per_hour.get(h.slug)
        rate = kph if kph and kph > 0 else default_kills_per_hour
        if chance <= 0:
            continue
        out.append(
            QueueItem(
                slug=h.slug,
                species_id=h.species_id,
                name=h.species_name or h.name,
                level=h.level,
                kills_per_hour=rate,
                chance=chance,
                hours=1 / (rate * chance),
                chance_source=source,
                kph_known=bool(kph and kph > 0),
            )
        )
    out.sort(key=lambda q: (q.hours, q.level, q.slug))
    return out


def observed_chances(
    attempts: Iterable[tuple[datetime, dict[str, Any]]], hunts: HuntCatalog, ball_id: int
) -> dict[int, float]:
    """Chance observada por espécie (a tentativa mais recente), convertida para `ball_id`."""
    target = hunts.balls.get(ball_id)
    table = hunts.capture
    if target is None or table is None:
        return {}
    latest: dict[int, tuple[datetime, float]] = {}
    for at, data in attempts:
        chance = data.get("chance")
        hunt = hunts.hunts.get(data.get("hunt_slug") or "")
        used = (
            hunts.balls.get(data.get("ball_id")) if isinstance(data.get("ball_id"), int) else None
        )
        if not isinstance(chance, int | float) or hunt is None or used is None:
            continue
        value = table.clamp(chance * target.catch_rate / used.catch_rate)
        prev = latest.get(hunt.species_id)
        if prev is None or at >= prev[0]:
            latest[hunt.species_id] = (at, value)
    return {sid: v for sid, (_, v) in latest.items()}
