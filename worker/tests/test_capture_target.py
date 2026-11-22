"""Alvo de captura do painel (docs/design/captura-alvo.md)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.capture_target import CaptureTargetConfig, CaptureTargetPlugin
from pokeidle_farm.store.memory import MemoryStore

from .test_commands import Rig, farm

AUTO = {
    "ballIds": [3, 2, 1, 4, 5],
    "autoBallSemParar": False,
    "autoBallAteCapturar": False,
    "autoPotion": True,
}


class World:
    def __init__(self, **cfg: Any) -> None:
        self.sent: list[dict[str, Any]] = []
        self.rec: list[tuple[str, dict[str, Any]]] = []
        self.store = MemoryStore()
        self.state = AccountStateView()
        self.state.automation = dict(AUTO)
        self.state.balls = {"4": 500}
        self.state.gold = 100_000

        async def send(m: dict[str, Any]) -> None:
            self.sent.append(m)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.rec.append((t, d))

        self.gw = ActionGateway("acc", ActionMode.ENABLED, send=send, record=record)
        base = {
            "species_id": 140,
            "species_name": "Kabuto",
            "hunt_slug": "kabuto",
            "started_at": datetime.now(UTC),
        }
        self.cfg = CaptureTargetConfig(**{**base, **cfg})
        self.ctx = PluginContext(
            account_id=uuid4(),
            nick="farm1",
            config=self.cfg,
            bus=EventBus(),
            actions=self.gw,
            state=self.state,
            store=self.store,
            settings=None,
            log=logging.getLogger("t"),
        )
        self.plugin = CaptureTargetPlugin()

        async def never(_s: float) -> None:
            await asyncio.Event().wait()

        self.plugin.sleep = never

    def ev(self, type_: str, **data: Any) -> Event:
        return Event(account_id=self.ctx.account_id, session_id=uuid4(), type=type_, data=data)

    def notes(self, prefix: str) -> list[dict[str, Any]]:
        return [d for t, d in self.rec if t.startswith(prefix)]


async def test_start_goes_to_hunt_publishes_target_and_holds_hunt():
    w = World(count=2)
    await w.plugin.start(w.ctx)
    # a bola automática já está desligada: nenhum auto.set; quem joga é o ball_thrower
    assert w.sent == [{"t": "hunt.select", "slug": "kabuto"}]
    assert w.state.capture == {"species_id": 140, "species_name": "Kabuto", "ball_id": None}
    assert w.gw.held_by_other("hunt.select", "gems")
    assert not w.gw.held_by_other("auto.set", "restock")
    await w.plugin.stop()
    assert not w.gw.holds and w.state.capture is None


async def test_counts_target_captures_and_ends_clearing_target():
    w = World(count=2)
    await w.plugin.start(w.ctx)
    await w.plugin.on_event(w.ev("pokemon.captured", species_id=10))  # outra espécie: não conta
    await w.plugin.on_event(w.ev("pokemon.captured", species_id=140))
    assert w.plugin.captured == 1 and w.plugin.active
    await w.plugin.on_event(w.ev("pokemon.captured", species_id=140))
    assert not w.plugin.active and not w.gw.holds and w.state.capture is None
    assert w.notes("capture_target.ended")[-1]["reason"] == "count"
    assert [m for m in w.sent if m["t"] == "auto.set"] == []  # não religa bola automática no fim
    assert w.store.configs[w.ctx.account_id]["capture_target"][0] is False


async def test_ball_flag_on_is_turned_off_once():
    """T14: com uma flag de bola ligada, um auto.set desliga as duas (e não repete)."""
    w = World()
    w.state.automation = {**AUTO, "autoBallAteCapturar": True}
    await w.plugin.start(w.ctx)
    autos = [m for m in w.sent if m["t"] == "auto.set"]
    assert len(autos) == 1
    assert autos[0]["autoBallAteCapturar"] is False and autos[0]["autoBallSemParar"] is False
    await w.plugin.on_event(w.ev("kill"))  # o estado ainda não refletiu: não manda de novo
    assert len([m for m in w.sent if m["t"] == "auto.set"]) == 1
    await w.plugin.stop()


async def test_expired_or_already_done_ends_at_start():
    w = World(until=datetime.now(UTC) - timedelta(minutes=1))
    await w.plugin.start(w.ctx)
    assert not w.plugin.active and w.sent == [] and not w.gw.holds
    assert w.notes("capture_target.ended")[-1]["reason"] == "expired"


async def test_buys_the_ball_when_low_keeping_the_reserve():
    w = World(ball_id=4)
    w.state.balls = {"4": 3}
    w.state.gold = 5_000 + 130 * 10
    await w.plugin.start(w.ctx)
    buy = [m for m in w.sent if m["t"] == "shop.buy"]
    assert buy == [{"t": "shop.buy", "kind": "ball", "id": 4, "qty": 10}]
    await w.plugin.stop()


async def test_capture_commands():
    rig = Rig()
    try:
        acc = farm(rig.store, "farm1")
        await rig.boot()
        rig.store.configs.setdefault(acc.id, {})["hunt_hold"] = (
            True,
            {"slug": "meowth", "until": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )
        c = await rig.cmd(
            acc,
            "capture.start",
            species_id=140,
            species_name="Kabuto",
            hunt_slug="kabuto",
            ball_id=4,
            count=5,
            hours=2,
        )
        assert c["status"] == "done", c
        enabled, cfg = rig.store.configs[acc.id]["capture_target"]
        assert enabled and cfg["count"] == 5 and cfg["until"] and cfg["hunt_slug"] == "kabuto"
        assert rig.store.configs[acc.id]["hunt_hold"][0] is False
        c = await rig.cmd(acc, "capture.start", species_id=140, hunt_slug="kabuto", ball_id=9)
        assert c["status"] == "failed"
        c = await rig.cmd(acc, "capture.stop")
        assert c["status"] == "done" and rig.store.configs[acc.id]["capture_target"][0] is False
    finally:
        await rig.close()
