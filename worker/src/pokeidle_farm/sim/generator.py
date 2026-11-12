"""Gera eventos internos realistas para desenvolver métricas e painel sem o jogo.

Os eventos têm o mesmo formato dos que o worker grava (`events.Event`) e são
marcados com `raw._sim = true`, para poderem ser apagados depois:

    delete from public.events where raw->>'_sim' = 'true';

Os números de ritmo (abates por minuto, chance de captura, drops) são
**chutes** para gerar dados plausíveis, não medições do jogo.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from ..events import Event
from .rolls import roll_capture


@dataclass(frozen=True)
class HuntProfile:
    slug: str
    name: str
    level: int
    species: tuple[str, ...]
    xp_per_kill: tuple[int, int]
    gold_per_kill: tuple[int, int]
    drops: tuple[tuple[str, float], ...]  # (nome, chance por abate)


DEFAULT_HUNTS: tuple[HuntProfile, ...] = (
    HuntProfile(
        slug="sim-rota-dragao",
        name="Rota do Dragão (simulada)",
        level=1200,
        species=("Dratini", "Horsea", "Magikarp", "Goldeen"),
        xp_per_kill=(900, 1400),
        gold_per_kill=(60, 120),
        drops=(("Dragon Scale", 0.004), ("Pena", 0.05), ("Escama", 0.03)),
    ),
    HuntProfile(
        slug="sim-caverna",
        name="Caverna (simulada)",
        level=800,
        species=("Geodude", "Zubat", "Onix", "Machop"),
        xp_per_kill=(500, 800),
        gold_per_kill=(40, 90),
        drops=(("Pedra", 0.08), ("Hard Stone", 0.006)),
    ),
)


@dataclass
class SimConfig:
    kills_per_minute: float = 6.0  # chute
    capture_attempt_rate: float = 0.25  # fração de abates em que joga bola
    capture_success: float = 0.35  # chance de a bola fechar (chute)
    hunt_change_every_h: float = 6.0
    disconnect_every_h: float = 8.0
    pokecenter_rate: float = 0.002  # por abate
    shiny_odds: int = 24_000
    seed: int | None = None


@dataclass
class _State:
    hunt: HuntProfile
    session_id: UUID = field(default_factory=uuid4)
    level: int = 50
    xp: int = 0


class EventSimulator:
    def __init__(
        self,
        account_id: UUID,
        cfg: SimConfig | None = None,
        hunts: tuple[HuntProfile, ...] = DEFAULT_HUNTS,
    ) -> None:
        self.account_id = account_id
        self.cfg = cfg or SimConfig()
        self.hunts = hunts
        self.rng = random.Random(self.cfg.seed)
        self.state = _State(hunt=hunts[0])

    # --- API ----------------------------------------------------------------

    def generate(self, start: datetime, end: datetime) -> Iterator[Event]:
        """Eventos de `start` a `end`, em ordem de tempo."""
        self._t = start
        yield from self._connect(self._t)
        while True:
            self._t += timedelta(seconds=self.rng.expovariate(self.cfg.kills_per_minute / 60))
            if self._t >= end:
                return
            yield from self._tick()

    # --- internos -----------------------------------------------------------

    def _ev(
        self, t: datetime, type_: str, data: dict[str, Any], raw: dict[str, Any] | None = None
    ) -> Event:
        return Event(
            account_id=self.account_id,
            session_id=self.state.session_id,
            type=type_,
            server_ts=t,
            received_at=t,
            data=data,
            raw={"_sim": True, **(raw or {})},
        )

    def _connect(self, t: datetime) -> Iterator[Event]:
        s = self.state
        s.session_id = uuid4()
        yield self._ev(
            t,
            "state.snapshot",
            {"level": s.level, "hunt_slug": s.hunt.slug, "items": {}, "active_pokemon_id": None},
        )
        yield self._ev(
            t,
            "session.connected",
            {
                "level": s.level,
                "hunt_slug": s.hunt.slug,
                "server_offset_ms": 0,
                "holder": "simulador",
            },
        )

    def _per_kill(self, every_h: float) -> float:
        kills_per_h = self.cfg.kills_per_minute * 60
        return 1 / (every_h * kills_per_h) if every_h > 0 else 0.0

    def _tick(self) -> Iterator[Event]:
        rng, s, cfg = self.rng, self.state, self.cfg
        t = self._t

        if rng.random() < self._per_kill(cfg.disconnect_every_h):
            yield self._ev(
                t, "session.disconnected", {"reason": "queda simulada", "will_retry": True}
            )
            # o relógio do simulador avança junto, para os eventos seguirem em ordem
            self._t = t = t + timedelta(seconds=rng.uniform(10, 60))
            yield from self._connect(t)

        if rng.random() < self._per_kill(cfg.hunt_change_every_h) and len(self.hunts) > 1:
            s.hunt = rng.choice([h for h in self.hunts if h is not s.hunt])
            yield self._ev(t, "hunt.changed", {"slug": s.hunt.slug, "name": s.hunt.name})

        wild = rng.choice(s.hunt.species)
        xp = rng.randint(*s.hunt.xp_per_kill)
        gold = rng.randint(*s.hunt.gold_per_kill)
        drops = [{"name": name} for name, p in s.hunt.drops if rng.random() < p]
        yield self._ev(
            t,
            "kill",
            {"wild_name": wild, "xp": xp, "gold": gold, "gold_autosell": 0, "drops": drops},
        )
        s.xp += xp
        while s.xp >= s.level * 2000:  # curva de nível inventada
            s.xp -= s.level * 2000
            s.level += 1

        if rng.random() < cfg.capture_attempt_rate:
            roll = roll_capture(rng, shiny_odds=cfg.shiny_odds)
            success = rng.random() < cfg.capture_success
            yield self._ev(
                t,
                "capture_attempt",
                {
                    "ball_id": 2,
                    "success": success,
                    "shiny": roll.shiny,
                    "chance": cfg.capture_success,
                },
            )
            if success:
                yield self._ev(
                    t,
                    "pokemon.captured",
                    {
                        "species": wild,
                        "level": rng.randint(max(1, s.hunt.level // 40), s.hunt.level // 20),
                        "shiny": roll.shiny,
                        "potency": roll.potency,
                        "quality": roll.quality,
                        "ivs": roll.ivs,
                        "iv_sum": roll.iv_sum,
                        "hunt_slug": s.hunt.slug,
                    },
                )

        if rng.random() < cfg.pokecenter_rate:
            yield self._ev(t, "pokecenter", {"reason": "equipe desmaiou (simulado)"})
