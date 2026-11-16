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


async def test_start_goes_to_hunt_turns_on_balls_and_holds_others():
    w = World(count=2)
    await w.plugin.start(w.ctx)
    assert w.sent[0] == {"t": "hunt.select", "slug": "kabuto"}
    auto = w.sent[1]
    assert (
        auto["t"] == "auto.set" and auto["autoBallAteCapturar"] is True and auto["ballIds"][0] == 4
    )
    assert w.gw.held_by_other("hunt.select", "gems") and w.gw.held_by_other("auto.set", "restock")
    assert not w.gw.held_by_other("auto.set", "capture_target")
    await w.plugin.stop()
    assert not w.gw.holds


async def test_counts_target_captures_and_ends_restoring_balls():
    w = World(count=2)
    await w.plugin.start(w.ctx)
    w.state.automation = {**AUTO, "ballIds": [4, 3, 2, 1, 5], "autoBallAteCapturar": True}
    await w.plugin.on_event(w.ev("pokemon.captured", species_id=10))  # outra espécie: não conta
    await w.plugin.on_event(w.ev("pokemon.captured", species_id=140))
    assert w.plugin.captured == 1 and w.plugin.active
    w.gw.limiter._last.clear()  # type: ignore[union-attr]
    await w.plugin.on_event(w.ev("pokemon.captured", species_id=140))
    assert not w.plugin.active and not w.gw.holds
    assert w.notes("capture_target.ended")[-1]["reason"] == "count"
    restore = w.sent[-1]
    assert (
        restore["t"] == "auto.set"
        and restore["autoBallAteCapturar"] is False
        and restore["ballIds"][0] == 3
    )
    assert w.store.configs[w.ctx.account_id]["capture_target"][0] is False


async def test_server_turning_the_flag_off_gets_it_back_on():
    w = World()
    await w.plugin.start(w.ctx)
    w.state.automation = {**AUTO, "ballIds": [4, 3, 2, 1, 5], "autoBallAteCapturar": True}
    await w.plugin.on_event(w.ev("kill"))
    n = len(w.sent)
    w.state.automation = {
        **AUTO,
        "ballIds": [4, 3, 2, 1, 5],
        "autoBallAteCapturar": False,
    }  # capturou
    w.plugin._auto_sent_at = None
    w.gw.limiter._last.clear()  # type: ignore[union-attr]
    await w.plugin.on_event(w.ev("state.patch"))
    assert len(w.sent) == n + 1 and w.sent[-1]["autoBallAteCapturar"] is True
    await w.plugin.stop()


async def test_expired_or_already_done_ends_at_start():
    w = World(until=datetime.now(UTC) - timedelta(minutes=1))
    await w.plugin.start(w.ctx)
    assert not w.plugin.active and w.sent == [] and not w.gw.holds
    assert w.notes("capture_target.ended")[-1]["reason"] == "expired"


async def test_buys_the_ball_when_low_keeping_the_reserve():
    w = World()
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
