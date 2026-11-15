"""Ritmo de abates por hunt, aprendido durante a sessão (análise de 15/11, proposta A).

Ver docs/design/foco-gemas-e-ritmo.md. O ritmo de uma hunt depende muito do nível dela em
relação ao time (15/11, treinador nível 20: ~900 abates/h nas de nível 1, ~100 nas de nível
10, ~60 nas de nível 20). Por isso:

- o ritmo medido junta o histórico do banco (`rank_hunt_stats`) com os abates da sessão;
- uma hunt nunca medida usa a mediana das hunts medidas do mesmo nível, não o ritmo médio
  da conta (que vem quase todo das hunts fáceis).
"""

from __future__ import annotations

from datetime import datetime
from statistics import median


class PaceBook:
    def __init__(self, min_active_minutes: float) -> None:
        self.min_active_minutes = min_active_minutes
        self._base: dict[str, tuple[float, float]] = {}  # slug -> (abates, minutos) do banco
        self._live_kills: dict[str, int] = {}
        self._live_minutes: dict[str, set[int]] = {}

    def load(self, slug: str, kills: float, minutes: float) -> None:
        self._base[slug] = (kills, minutes)

    def add_kill(self, slug: str | None, at: datetime) -> None:
        if not slug:
            return
        self._live_kills[slug] = self._live_kills.get(slug, 0) + 1
        self._live_minutes.setdefault(slug, set()).add(int(at.timestamp() // 60))

    def totals(self, slug: str) -> tuple[float, float]:
        k, m = self._base.get(slug, (0.0, 0.0))
        return k + self._live_kills.get(slug, 0), m + len(self._live_minutes.get(slug, ()))

    def measured(self, slug: str) -> float | None:
        """Abates/h medidos, ou None com menos de `min_active_minutes` na hunt."""
        kills, minutes = self.totals(slug)
        if minutes < max(self.min_active_minutes, 1) or kills <= 0:
            return None
        return kills / minutes * 60

    def all_measured(self) -> dict[str, float]:
        out = {}
        for slug in set(self._base) | set(self._live_kills):
            kph = self.measured(slug)
            if kph is not None:
                out[slug] = kph
        return out

    def by_level(self, levels: dict[str, int]) -> dict[int, float]:
        """Mediana do ritmo medido por nível de hunt (`levels`: slug -> nível)."""
        groups: dict[int, list[float]] = {}
        for slug, kph in self.all_measured().items():
            if slug in levels:
                groups.setdefault(levels[slug], []).append(kph)
        return {lvl: median(v) for lvl, v in groups.items()}

    def estimate(self, slug: str, level: int, level_kph: dict[int, float]) -> float | None:
        """Medido; senão a mediana do mesmo nível; senão None (quem chama usa o padrão)."""
        kph = self.measured(slug)
        if kph is not None:
            return kph
        return level_kph.get(level)


def rates_for(
    levels: dict[str, int], pace: PaceBook, default_kph: float
) -> dict[str, tuple[float, str]]:
    """Ritmo de cada hunt com a origem.

    - "measured": medido na própria hunt;
    - "level": mediana das hunts medidas do mesmo nível;
    - "near_level": a do nível medido mais próximo **abaixo** (hunts mais altas são mais lentas,
      então é a estimativa conservadora); sem nenhum abaixo, a do mais próximo acima;
    - "default": nada medido ainda (o padrão da conta).
    """
    measured = pace.all_measured()
    level_kph = pace.by_level(levels)
    known = sorted(level_kph)
    out: dict[str, tuple[float, str]] = {}
    for slug, lvl in levels.items():
        if slug in measured:
            out[slug] = (measured[slug], "measured")
        elif lvl in level_kph:
            out[slug] = (level_kph[lvl], "level")
        elif known:
            below = [k for k in known if k < lvl]
            near = below[-1] if below else known[0]
            out[slug] = (level_kph[near], "near_level")
        else:
            out[slug] = (default_kph, "default")
    return out
