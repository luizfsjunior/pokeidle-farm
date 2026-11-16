"""Ritmo de abates por hunt, aprendido durante a sessão e projetado para o nível do ativo.

Ver docs/design/foco-gemas-e-ritmo.md (proposta A) e docs/design/ritmo-por-nivel.md.

- O ritmo medido junta o histórico do banco (`rank_hunt_stats`) com os abates da sessão.
- O ritmo cresce com o nível do pokémon ativo: o dano do jogo é
  ((2 × nível/5 + 2) × poder × atk/def)/50 + 2, e o atk também cresce com o nível. Então um
  ritmo medido com o ativo no nível L0 é projetado para o nível atual L multiplicando por
  f(L)/f(L0), com f(L) = (0,4·L + 2)·L, e limitado pelo teto (o maior ritmo observado: a partir
  daí o que limita é andar até o selvagem e ele reaparecer, não o dano).
- Uma hunt nunca medida usa a mediana das hunts medidas do mesmo nível; senão a do nível medido
  mais próximo abaixo (a estimativa conservadora).
"""

from __future__ import annotations

from datetime import datetime
from statistics import median

NEAR_CAP = 0.8  # perto do teto o ritmo não escala com o dano


def damage_factor(level: float) -> float:
    """Quanto o dano por golpe cresce com o nível do ativo (fórmula do jogo, stats ∝ nível)."""
    lv = max(1.0, float(level))
    return (0.4 * lv + 2) * lv


class PaceBook:
    def __init__(self, min_active_minutes: float) -> None:
        self.min_active_minutes = min_active_minutes
        # slug -> (abates, minutos, nível médio do ativo ou None) do banco
        self._base: dict[str, tuple[float, float, float | None]] = {}
        self._live_kills: dict[str, int] = {}
        self._live_minutes: dict[str, set[int]] = {}
        self._live_level: dict[str, tuple[float, int]] = {}  # soma dos níveis, abates com nível

    def load(self, slug: str, kills: float, minutes: float, avg_level: float | None = None) -> None:
        self._base[slug] = (kills, minutes, avg_level)

    def add_kill(self, slug: str | None, at: datetime, level: int | None = None) -> None:
        if not slug:
            return
        self._live_kills[slug] = self._live_kills.get(slug, 0) + 1
        self._live_minutes.setdefault(slug, set()).add(int(at.timestamp() // 60))
        if isinstance(level, int) and level > 0:
            s, n = self._live_level.get(slug, (0.0, 0))
            self._live_level[slug] = (s + level, n + 1)

    def totals(self, slug: str) -> tuple[float, float]:
        k, m, _ = self._base.get(slug, (0.0, 0.0, None))
        return k + self._live_kills.get(slug, 0), m + len(self._live_minutes.get(slug, ()))

    def level_of(self, slug: str) -> float | None:
        """Nível médio do ativo em que o ritmo da hunt foi medido."""
        k, _, lvl = self._base.get(slug, (0.0, 0.0, None))
        s, n = (lvl * k, k) if lvl is not None and k > 0 else (0.0, 0.0)
        ls, ln = self._live_level.get(slug, (0.0, 0))
        total = n + ln
        return (s + ls) / total if total > 0 else None

    def measured(self, slug: str) -> float | None:
        """Abates/h medidos, ou None com menos de `min_active_minutes` na hunt."""
        kills, minutes = self.totals(slug)
        if minutes < max(self.min_active_minutes, 1) or kills <= 0:
            return None
        return kills / minutes * 60

    def cap(self) -> float | None:
        """Teto do ritmo: o maior medido (a partir dele o limite é andar e reaparecer)."""
        values = [v for v in (self.measured(s) for s in self._slugs()) if v is not None]
        return max(values) if values else None

    def projected(self, slug: str, level_now: int | None) -> float | None:
        """Medido, projetado para o nível atual do ativo (sem nível conhecido, o medido)."""
        kph = self.measured(slug)
        if kph is None or level_now is None:
            return kph
        lvl0 = self.level_of(slug)
        cap = self.cap()
        if lvl0 is None or cap is None or kph >= NEAR_CAP * cap:
            return kph
        return min(cap, kph * damage_factor(level_now) / damage_factor(lvl0))

    def _slugs(self) -> set[str]:
        return set(self._base) | set(self._live_kills)

    def all_measured(self, level_now: int | None = None) -> dict[str, float]:
        out = {}
        for slug in self._slugs():
            kph = self.projected(slug, level_now)
            if kph is not None:
                out[slug] = kph
        return out

    def by_level(self, levels: dict[str, int], level_now: int | None = None) -> dict[int, float]:
        """Mediana do ritmo (projetado) por nível de hunt (`levels`: slug -> nível)."""
        groups: dict[int, list[float]] = {}
        for slug, kph in self.all_measured(level_now).items():
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
    levels: dict[str, int],
    pace: PaceBook,
    default_kph: float,
    active_level: int | None = None,
    model: dict[str, float] | None = None,
) -> dict[str, tuple[float, str]]:
    """Ritmo de cada hunt com a origem, projetado para o nível do ativo quando ele é conhecido.

    - "measured": medido na própria hunt;
    - "level": mediana das hunts medidas do mesmo nível;
    - "near_level": a do nível medido mais próximo **abaixo** (hunts mais altas são mais lentas,
      então é a estimativa conservadora); sem nenhum abaixo, a do mais próximo acima;
    - "default": nada medido ainda (o padrão da conta).

    Com `model` (previsão do simulador de combate para o ativo), toda hunt não medida usa a
    previsão ("model") no lugar de "level"/"near_level"/"default": ela enxerga a vantagem de tipo.
    """
    measured = pace.all_measured(active_level)
    level_kph = pace.by_level(levels, active_level)
    known = sorted(level_kph)
    out: dict[str, tuple[float, str]] = {}
    for slug, lvl in levels.items():
        if slug in measured:
            out[slug] = (measured[slug], "measured")
        elif model and slug in model:
            out[slug] = (model[slug], "model")
        elif lvl in level_kph:
            out[slug] = (level_kph[lvl], "level")
        elif known:
            below = [k for k in known if k < lvl]
            near = below[-1] if below else known[0]
            out[slug] = (level_kph[near], "near_level")
        else:
            out[slug] = (default_kph, "default")
    return out
