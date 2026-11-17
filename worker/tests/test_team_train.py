"""Plugin team_train (docs/design/team-train.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from pokeidle_farm.actions import ActionBlocked, TeamActive, TeamMove
from pokeidle_farm.events import Translator
from pokeidle_farm.plugins.team_train import TeamTrainConfig, TeamTrainPlugin

NOW = datetime(2026, 11, 17, 15, 0, tzinfo=UTC)


class _Actions:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.notes: list[tuple[str, dict[str, Any]]] = []
        self.block: float | None = None

    async def submit(self, action: Any, *, source: str) -> None:
        if self.block is not None:
            raise ActionBlocked("team.active", "rate_limit", wait_s=self.block)
        self.sent.append(action.to_wire())

    async def note(self, type_: str, data: dict[str, Any]) -> None:
        self.notes.append((type_, data))


def _team(*levels: int) -> list[dict[str, Any]]:
    return [{"id": 10 + i, "speciesId": 1, "level": lv, "slot": i} for i, lv in enumerate(levels)]


async def _plugin(team, active_id, active_level, **cfg) -> tuple[TeamTrainPlugin, _Actions]:
    actions = _Actions()
    state = SimpleNamespace(team=team, active_pokemon={"id": active_id, "level": active_level})
    ctx = SimpleNamespace(state=state, actions=actions, config=TeamTrainConfig(**cfg))
    p = TeamTrainPlugin()
    p.now = lambda: NOW
    await p.start(ctx)  # type: ignore[arg-type]
    return p, actions


def test_wire_formats():
    assert TeamActive(pokemon_id=7).to_wire() == {"t": "team.active", "pokemonId": 7}
    assert TeamMove(pokemon_id=7, slot=2).to_wire() == {"t": "team.move", "pokemonId": 7, "slot": 2}
    assert TeamMove(pokemon_id=7).to_wire() == {"t": "team.move", "pokemonId": 7, "slot": None}


async def test_keeps_training_the_active_below_target():
    _p, a = await _plugin(_team(120, 5, 40), 10, 120, target_level=300)
    assert a.sent == []


async def test_switches_to_the_weakest_when_the_active_reaches_target():
    _p, a = await _plugin(_team(356, 5, 40, 3), 10, 356, target_level=300)
    assert a.sent == [{"t": "team.active", "pokemonId": 13}]  # o de nível 3
    (note,) = [d for t, d in a.notes if t == "team_train.switch"]
    assert note["from"] == 10 and note["to"] == 13 and note["reason"] == "proximo"


async def test_active_outside_the_team_goes_to_the_weakest():
    _p, a = await _plugin(_team(356, 50), 99, 10, target_level=300)
    assert a.sent == [{"t": "team.active", "pokemonId": 11}]


async def test_waits_for_confirmation_then_retries():
    p, a = await _plugin(_team(356, 5), 10, 356, target_level=300, confirm_s=60)
    await p.check()  # ainda esperando o ativo mudar
    assert len(a.sent) == 1
    p.now = lambda: NOW + timedelta(seconds=61)
    await p.check()
    assert len(a.sent) == 2 and [t for t, _ in a.notes].count("team_train.failed") == 1


async def test_confirmed_switch_stops_sending():
    p, a = await _plugin(_team(356, 5), 10, 356, target_level=300)
    p.ctx.state.active_pokemon = {"id": 11, "level": 5}
    await p.check()
    assert len(a.sent) == 1


async def test_all_at_target_goes_back_to_the_strongest_and_notes_done():
    p, a = await _plugin(_team(356, 300, 301), 11, 300, target_level=300)
    assert a.sent == [{"t": "team.active", "pokemonId": 10}]
    p.ctx.state.active_pokemon = {"id": 10, "level": 356}
    await p.check()
    await p.check()
    assert [t for t, _ in a.notes].count("team_train.done") == 1


async def test_blocked_action_waits():
    actions_block = 30.0
    p, a = await _plugin(_team(356, 5), 10, 356, target_level=300)
    a.sent.clear()
    p._pending = None
    a.block = actions_block
    p.now = lambda: NOW + timedelta(seconds=120)
    await p.check()
    assert a.sent == [] and p._blocked_until == NOW + timedelta(seconds=150)


def test_translator_tracks_team_slots():
    tr = Translator(account_id=None, session_id=None)  # type: ignore[arg-type]
    tr._track_pokemon(
        [
            {"id": 1, "speciesId": 3, "level": 356, "slot": 0},
            {"id": 2, "speciesId": 129, "level": 1, "slot": 1},
            {"id": 3, "speciesId": 10, "level": 9, "slot": None},
        ]
    )
    assert [p["id"] for p in tr.team()] == [1, 2]
    tr._track_pokemon([{"id": 2, "level": 4, "slot": None}])  # saiu da equipe
    tr.pokemon_levels[1] = 357
    assert tr.team() == [{"id": 1, "speciesId": 3, "level": 357, "slot": 0}]
    tr._drop_pokemon([1])
    assert tr.team() == []
