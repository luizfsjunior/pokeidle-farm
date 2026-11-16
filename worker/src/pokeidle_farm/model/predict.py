"""Ritmo previsto pelo modelo de combate para as hunts ainda não medidas.

O foco XP/gemas usa o ritmo medido quando existe; para as outras hunts, em vez do ritmo de outra
hunt do mesmo nível (que ignora a vantagem de tipo), usa a previsão do simulador para o pokémon
ativo (docs/design/simulador-1-combate.md). Pura: recebe o perfil do ativo, a Pokedex e as regras.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .combat import STATS, Fighter, Rules, SpeciesData, kills_per_hour

POTENCY_BONUS = {1: 0.0, 2: 0.05, 3: 0.1, 4: 0.25, 5: 1.0}


def fighter_from_profile(
    profile: dict[str, Any], raw_species: dict[int, dict[str, Any]], rules: dict[str, Any]
) -> Fighter | None:
    """Monta o lutador a partir do pokémon do `estado` (speciesId, level, ivs, quality, potencia)."""
    sid, level = profile.get("speciesId"), profile.get("level")
    if not isinstance(sid, int) or not isinstance(level, int) or sid not in raw_species:
        return None
    ivs = profile.get("ivs") if isinstance(profile.get("ivs"), dict) else {}
    pots = {
        int(p["n"]): float(p.get("bonus") or 0)
        for p in rules.get("potencias") or []
        if isinstance(p, dict) and isinstance(p.get("n"), int)
    } or POTENCY_BONUS
    mult = 1 + pots.get(int(profile.get("potencia") or 1), 0.0)
    if profile.get("shiny"):
        mult *= float(rules.get("multShinyStats") or 3)
    return Fighter(
        species=SpeciesData.from_raw(raw_species[sid]),
        level=level,
        ivs={s: int(ivs.get(s) or 16) for s in STATS},
        quality=float(profile.get("quality") or 1.0),
        multiplier=mult,
    )


class ModelRates:
    """Cache das previsões por (perfil do ativo, dia sazonal, hunt): só recalcula quando o ativo
    muda. Guarda os últimos `keep` perfis, porque no dia sazonal o foco XP pede as duas previsões
    (com e sem o tipo do dia) a cada plano."""

    def __init__(self, n_kills: int = 150, keep: int = 4) -> None:
        self.n_kills = n_kills
        self.keep = keep
        self._caches: dict[Any, dict[str, float]] = {}
        self._cache: dict[str, float] = {}

    def rates(
        self,
        hunts: dict[str, tuple[int, int]],  # slug -> (nível da hunt, espécie)
        profile: dict[str, Any] | None,
        raw_species: dict[int, dict[str, Any]],
        rules: dict[str, Any],
        max_level: int | None = None,
        season: str | None = None,
    ) -> dict[str, float]:
        if not profile or not rules.get("tabelaTipos"):
            return {}
        fighter = fighter_from_profile(profile, raw_species, rules)
        if fighter is None:
            return {}
        key = (
            fighter.species.id,
            fighter.level,
            fighter.quality,
            fighter.multiplier,
            tuple(sorted(fighter.ivs.items())),
            season,
        )
        if key not in self._caches:
            self._caches[key] = {}
            while len(self._caches) > self.keep:
                self._caches.pop(next(iter(self._caches)))
        self._cache = self._caches[key]
        parsed = replace(Rules.from_welcome(rules), season=season)
        out = {}
        for slug, (level, sid) in hunts.items():
            if max_level is not None and level > max_level:
                continue
            if slug not in self._cache:
                if sid not in raw_species:
                    continue
                wild = SpeciesData.from_raw(raw_species[sid])
                self._cache[slug] = kills_per_hour(
                    fighter, wild, level, parsed, n_kills=self.n_kills
                )
            out[slug] = self._cache[slug]
        return out


def season_adjust(
    rate: dict[str, tuple[float, str]],
    normal: dict[str, float],
    seasonal: dict[str, float],
) -> dict[str, tuple[float, str]]:
    """Ritmo medido corrigido para o dia sazonal: medido × (previsão com o tipo do dia ÷ previsão sem).

    O ritmo medido vem de dias normais; o simulador sabe quanto o tipo do dia muda aquela hunt para
    o ativo (o pokémon do tipo do dia bate ×2 e apanha ÷4). As outras origens não mudam (a previsão
    das hunts não medidas já vem com o tipo do dia).
    """
    out = dict(rate)
    for slug, (kph, source) in rate.items():
        base, now = normal.get(slug), seasonal.get(slug)
        if source == "measured" and base and now and base > 0 and abs(now / base - 1) > 1e-9:
            out[slug] = (kph * now / base, "measured_season")
    return out
