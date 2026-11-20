"""Plugin watchdog (docs/design/conta-v2.md, seção 5): a noite de 18 para 19/11 da luizfsjunior_1."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionBlocked
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.watchdog import WatchdogConfig, WatchdogPlugin

VENUSAUR, MAGIKARP = 125291236, 128267394


class _Actions:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.notes: list[tuple[str, dict[str, Any]]] = []
        self.block = False

    async def submit(self, action: Any, *, source: str) -> None:
        if self.block:
            raise ActionBlocked(action.name, "rate_limit", wait_s=5)
        self.sent.append(action.to_wire())

    async def note(self, type_: str, data: dict[str, Any]) -> None:
        self.notes.append((type_, data))


def _ev(type_: str, **data: Any) -> Event:
    return Event(account_id=uuid4(), session_id=uuid4(), type=type_, data=data)


async def _plugin(**cfg: Any) -> tuple[WatchdogPlugin, _Actions, SimpleNamespace, list[float]]:
    actions = _Actions()
    state = SimpleNamespace(
        in_center=False,
        hunt_slug="brave_steelix",
        items={"200": 100, "205": 20},
        active_pokemon={"id": VENUSAUR},
        team=[
            {"id": VENUSAUR, "level": 397, "slot": 0, "hp": 9000},
            {"id": MAGIKARP, "level": 1, "slot": 1, "hp": 24},
        ],
    )
    ctx = SimpleNamespace(state=state, actions=actions, config=WatchdogConfig(**cfg))
    clock = [1000.0]
    p = WatchdogPlugin()
    p.clock = lambda: clock[0]
    p.sleep = lambda s: asyncio.Event().wait()  # o tick roda só quando o teste chama check()
    await p.start(ctx)  # type: ignore[arg-type]
    return p, actions, state, clock


async def test_death_in_hunt_heals_at_center_and_restores_the_active():
    p, actions, state, clock = await _plugin()
    await p.on_event(_ev("kill"))  # o Venusaur abate: é o ativo de verdade
    # a equipe cai: o jogo troca para o Magikarp e manda para o Pokécenter
    state.active_pokemon = {"id": MAGIKARP}
    for m in state.team:
        m["hp"] = 0
    await p.on_event(_ev("pokecenter", reason="morte"))
    state.in_center = True
    await p.on_event(_ev("field.init", is_center=True))
    assert actions.sent == []  # ainda não: espera heal_after_s
    clock[0] += 25
    await p.check()
    assert actions.sent == [{"t": "centro.curar"}]
    clock[0] += 10
    await p.check()
    assert len(actions.sent) == 1  # uma tentativa por minuto
    # curou e voltou para a hunt
    for m in state.team:
        m["hp"] = 100
    state.in_center = False
    await p.on_event(_ev("hunt.changed", slug="brave_steelix"))
    assert actions.sent[-1] == {"t": "team.active", "pokemonId": VENUSAUR}
    assert ("watchdog.restore_active", {"pokemon_id": VENUSAUR, "was": MAGIKARP}) in actions.notes


async def test_no_heal_without_survival_items():
    p, actions, state, clock = await _plugin()
    state.items = {"200": 0, "205": 0}
    for m in state.team:
        m["hp"] = 0
    state.in_center = True
    await p.check()
    clock[0] += 60
    await p.check()
    assert actions.sent == []


async def test_healed_but_still_in_center_goes_back_to_the_hunt():
    # 19/11 10:15: curada, mas o jogo não voltou sozinho; a vigia curava de novo a cada minuto
    p, actions, state, clock = await _plugin()
    state.in_center = True
    await p.check()
    clock[0] += 25
    await p.check()
    assert actions.sent == [{"t": "hunt.select", "slug": "brave_steelix"}]
    assert ("watchdog.back_to_hunt", {"hunt_slug": "brave_steelix"}) in actions.notes


async def test_hold_lets_through_a_return_to_the_same_hunt():
    from datetime import UTC, datetime, timedelta

    from pokeidle_farm.actions import ActionGateway, ActionMode, HuntSelect

    sent: list[dict[str, Any]] = []

    async def send(msg: dict[str, Any]) -> None:
        sent.append(msg)

    gw = ActionGateway(account_id="a", mode=ActionMode.ENABLED, send=send)
    gw.hold(
        "hunt.select", datetime.now(UTC) + timedelta(hours=1), "capture_target", "brave_steelix"
    )
    await gw.submit(HuntSelect(slug="brave_steelix"), source="watchdog")
    assert sent == [{"t": "hunt.select", "slug": "brave_steelix"}]
    try:
        await gw.submit(HuntSelect(slug="meowth"), source="watchdog")
    except ActionBlocked as exc:
        assert "hold" in exc.reason
    else:
        raise AssertionError("trocar de hunt furou a trava")


async def test_does_not_touch_an_active_chosen_by_someone_else():
    p, actions, state, _clock = await _plugin()
    await p.on_event(_ev("kill"))
    state.active_pokemon = {"id": MAGIKARP}  # o usuário ou o team_train trocou, sem morte
    await p.on_event(_ev("state.patch"))
    assert actions.sent == []


async def test_two_deaths_in_the_same_hunt_raise_the_alert():
    p, actions, _state, clock = await _plugin()
    await p.on_event(_ev("pokecenter", reason="morte"))
    clock[0] += 600
    await p.on_event(_ev("pokecenter", reason="morte"))
    notes = [n for n in actions.notes if n[0] == "watchdog.dangerous_hunt"]
    assert notes and notes[0][1]["hunt_slug"] == "brave_steelix" and notes[0][1]["deaths"] == 2


async def test_no_kills_alert_once():
    p, actions, _state, clock = await _plugin(no_kills_s=600)
    clock[0] += 601
    await p.check()
    await p.check()
    assert [n[0] for n in actions.notes].count("watchdog.no_kills") == 1


async def test_revive_storm_marks_the_hunt_and_restores_the_strongest():
    """20/11: o nv 20 virou ativo na hunt nv 260 e o jogo reviveu ele em loop por uma hora."""
    p, actions, state, clock = await _plugin(revive_storm=4, revive_window_s=60)
    state.danger = {}
    state.active_pokemon = {"id": MAGIKARP}
    for _ in range(3):
        clock[0] += 5
        await p.on_event(_ev("battle.revive"))
    assert actions.sent == []  # 3 em 15 s: ainda não
    clock[0] += 5
    await p.on_event(_ev("battle.revive"))
    assert actions.sent == [{"t": "team.active", "pokemonId": VENUSAUR}]
    storm = [d for t, d in actions.notes if t == "watchdog.revive_storm"]
    assert storm == [{"hunt_slug": "brave_steelix", "active_id": MAGIKARP, "revives": 4}]
    assert (MAGIKARP, "brave_steelix") in state.danger
    # mais revives logo depois, mesmo par: não repete
    for _ in range(4):
        clock[0] += 1
        await p.on_event(_ev("battle.revive"))
    assert len([t for t, _ in actions.notes if t == "watchdog.revive_storm"]) == 1


async def test_spread_out_revives_are_not_a_storm():
    p, actions, state, clock = await _plugin(revive_storm=4, revive_window_s=60)
    state.danger = {}
    for _ in range(10):
        clock[0] += 30  # um revive a cada 30 s: no máximo 2 na janela
        await p.on_event(_ev("battle.revive"))
    assert not [t for t, _ in actions.notes if t == "watchdog.revive_storm"]
