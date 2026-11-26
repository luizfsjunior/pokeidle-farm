"""Soma dos abates, do consumo de itens e das bolas lançadas por minuto (tabela kill_minute).

Um abate por linha em `events` eram ~56 mil linhas por dia com 4 contas; o banco do plano grátis (500 MB)
não aguentava nem 2 dias. A telemetria passa os `kill`, os `item.consumed` e os `capture_attempt` por aqui e
grava uma linha por minuto com o que as métricas usam. Ver docs/design/retencao-eventos.md, "Abates por minuto"
e "Bolas por minuto".

Chave da linha: (conta, sessão, minuto, hunt, espécie do pokémon ativo, dia sazonal, parte). Um minuto só é
entregue depois de fechado; se chegar um abate de um minuto já entregue (fila atrasada), ele vai para uma
parte nova, porque a gravação é `on conflict do nothing` (reenviar o buffer não pode contar duas vezes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .events import Event

AGGREGATED = frozenset({"kill", "item.consumed", "capture_attempt"})

# chave sem a parte: (conta, sessão, minuto, hunt, espécie ativa, dia sazonal)
_Key = tuple[str, str, datetime, str, int, str]


def minute_of(at: datetime) -> datetime:
    return at.replace(second=0, microsecond=0)


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


@dataclass
class _Bucket:
    kills: int = 0
    xp: int = 0
    gold: int = 0
    active_level_sum: int = 0
    kills_leveled: int = 0
    drops: dict[str, int] = field(default_factory=dict)
    consumables_gold: int = 0
    capture_attempts: int = 0
    capture_successes: int = 0
    balls_gold: int = 0
    # a última chance de captura vista no minuto e a bola dela (plugin rank: rank_hunt_stats)
    last_chance: float | None = None
    last_ball_id: int | None = None


class KillMinutes:
    """Acumula os eventos agregados e entrega as linhas dos minutos fechados."""

    def __init__(self) -> None:
        self._open: dict[_Key, _Bucket] = {}
        self._next_part: dict[_Key, int] = {}  # parte da próxima linha de um minuto já entregue

    def __len__(self) -> int:
        return len(self._open)

    def add(self, event: Event) -> None:
        d = event.data
        if event.type == "kill":
            species = _int(d.get("active_species_id"))
            season = d.get("season") if isinstance(d.get("season"), str) else ""
        elif event.type in ("item.consumed", "capture_attempt"):
            # o consumo e as bolas não carregam o pokémon ativo nem o dia sazonal
            species, season = 0, ""
        else:
            raise ValueError(f"evento não agregado: {event.type}")
        key: _Key = (
            str(event.account_id),
            str(event.session_id),
            minute_of(event.received_at),
            d.get("hunt_slug") or "",
            species,
            season,
        )
        b = self._open.setdefault(key, _Bucket())
        if event.type == "kill":
            b.kills += 1
            b.xp += _int(d.get("xp"))
            b.gold += _int(d.get("gold")) + _int(d.get("gold_autosell"))
            level = d.get("active_level")
            if isinstance(level, int) and not isinstance(level, bool):
                b.active_level_sum += level
                b.kills_leveled += 1
            for drop in d.get("drops") or []:
                name = drop.get("name") if isinstance(drop, dict) else None
                if name:
                    qty = drop.get("qty")
                    b.drops[name] = b.drops.get(name, 0) + (_int(qty) if _int(qty) > 0 else 1)
        elif event.type == "item.consumed":
            b.consumables_gold += _int(d.get("qty")) * _int(d.get("unit_price"))
        else:
            b.capture_attempts += 1
            b.capture_successes += d.get("success") is True
            b.balls_gold += _int(d.get("ball_price"))
            chance = d.get("chance")
            if isinstance(chance, int | float) and not isinstance(chance, bool):
                b.last_chance = float(chance)
                ball = d.get("ball_id")
                b.last_ball_id = (
                    ball if isinstance(ball, int) and not isinstance(ball, bool) else None
                )

    def take(self, before: datetime | None = None) -> list[dict[str, Any]]:
        """Tira as linhas dos minutos anteriores a `before` (todos, se None)."""
        cut = minute_of(before) if before is not None else None
        keys = [k for k in self._open if cut is None or k[2] < cut]
        rows = []
        for key in keys:
            b = self._open.pop(key)
            part = self._next_part.get(key, 0)
            self._next_part[key] = part + 1
            account_id, session_id, minute, hunt_slug, species, season = key
            rows.append(
                {
                    "account_id": account_id,
                    "session_id": session_id,
                    "minute": minute.isoformat(),
                    "hunt_slug": hunt_slug,
                    "active_species_id": species,
                    "season": season,
                    "part": part,
                    "kills": b.kills,
                    "xp": b.xp,
                    "gold": b.gold,
                    "active_level_sum": b.active_level_sum,
                    "kills_leveled": b.kills_leveled,
                    "drops": [{"name": n, "qty": q} for n, q in sorted(b.drops.items())],
                    "consumables_gold": b.consumables_gold,
                    "capture_attempts": b.capture_attempts,
                    "capture_successes": b.capture_successes,
                    "balls_gold": b.balls_gold,
                    "last_chance": b.last_chance,
                    "last_ball_id": b.last_ball_id,
                }
            )
        # as partes de minutos antigos não servem mais: a fila não atrasa uma hora
        if cut is not None:
            self._next_part = {
                k: v for k, v in self._next_part.items() if (cut - k[2]).total_seconds() < 3600
            }
        return rows
