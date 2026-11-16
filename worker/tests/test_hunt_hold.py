"""Hunt escolhida pelo painel (docs/design/painel-fase-3.md): trava no gateway, plugin e comandos."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from pokeidle_farm.actions import ActionBlocked, ActionGateway, ActionMode, HuntSelect
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.hunt_hold import HuntHoldConfig, HuntHoldPlugin
from pokeidle_farm.store.memory import MemoryStore

from .test_commands import Rig, farm


def gateway() -> tuple[ActionGateway, list[dict[str, Any]], list[tuple[str, dict[str, Any]]]]:
    sent: list[dict[str, Any]] = []
    rec: list[tuple[str, dict[str, Any]]] = []

    async def send(m: dict[str, Any]) -> None:
        sent.append(m)

    async def record(t: str, d: dict[str, Any]) -> None:
        rec.append((t, d))

    return ActionGateway("acc", ActionMode.ENABLED, send=send, record=record), sent, rec


async def test_gateway_hold_blocks_others_until_it_ends():
    gw, sent, rec = gateway()
    gw.hold_hunt("kabuto", datetime.now(UTC) + timedelta(hours=1), "hunt_hold")
    with pytest.raises(ActionBlocked) as exc:
        await gw.submit(HuntSelect(slug="meowth"), source="gems")
    assert exc.value.wait_s is not None and 3500 < exc.value.wait_s <= 3600
    assert rec[-1][1]["reason"] == "hunt_hold" and sent == []
    await gw.submit(HuntSelect(slug="kabuto"), source="hunt_hold")
    assert sent == [{"t": "hunt.select", "slug": "kabuto"}]
    gw.release_hunt("gems")  # só o dono solta
    assert gw.hunt_hold is not None
    gw.hunt_hold = ("kabuto", datetime.now(UTC) - timedelta(seconds=1), "hunt_hold")
    gw.limiter._last.clear()  # type: ignore[union-attr]
    await gw.submit(HuntSelect(slug="meowth"), source="gems")  # prazo vencido: passa
    assert gw.hunt_hold is None and sent[-1]["slug"] == "meowth"


def ctx_for(gw: ActionGateway, cfg: HuntHoldConfig) -> PluginContext:
    return PluginContext(
        account_id=uuid4(),
        nick="farm1",
        config=cfg,
        bus=EventBus(),
        actions=gw,
        state=AccountStateView(),
        store=MemoryStore(),
        settings=None,
        log=logging.getLogger("t"),
    )


async def test_plugin_holds_switches_and_releases_on_stop():
    gw, sent, rec = gateway()
    plugin = HuntHoldPlugin()

    async def never(_s: float) -> None:
        await asyncio.Event().wait()

    plugin.sleep = never
    cfg = HuntHoldConfig(slug="kabuto", until=datetime.now(UTC) + timedelta(hours=2))
    ctx = ctx_for(gw, cfg)
    await plugin.start(ctx)
    assert gw.hunt_hold is not None and gw.hunt_hold[0] == "kabuto"
    assert sent == [{"t": "hunt.select", "slug": "kabuto"}]
    await plugin.on_event(
        Event(
            account_id=ctx.account_id,
            session_id=uuid4(),
            type="hunt.changed",
            data={"slug": "kabuto"},
        )
    )
    assert plugin.switch.current == "kabuto"
    await plugin.stop()
    assert gw.hunt_hold is None
    assert [t for t, _ in rec if t.startswith("hunt_hold.")] == [
        "hunt_hold.started",
        "hunt_hold.ended",
    ]


async def test_plugin_with_expired_deadline_does_nothing():
    gw, sent, rec = gateway()
    plugin = HuntHoldPlugin()
    cfg = HuntHoldConfig(slug="kabuto", until=datetime.now(UTC) - timedelta(minutes=1))
    await plugin.start(ctx_for(gw, cfg))
    assert gw.hunt_hold is None and sent == []
    assert rec[-1] == ("hunt_hold.ended", {"slug": "kabuto", "reason": "expired"})
    await plugin.stop()


async def test_hunt_commands_write_the_plugin_config():
    rig = Rig()
    try:
        acc = farm(rig.store, "farm1")
        await rig.boot()
        c = await rig.cmd(acc, "hunt.release")
        assert c["status"] == "done" and c["result"]["applied"] == "nada a soltar"
        c = await rig.cmd(acc, "hunt.select", slug="kabuto", hours=1.5)
        assert c["status"] == "done", c
        enabled, cfg = rig.store.configs[acc.id]["hunt_hold"]
        until = datetime.fromisoformat(cfg["until"])
        assert enabled and cfg["slug"] == "kabuto"
        assert timedelta(minutes=89) < until - datetime.now(UTC) <= timedelta(minutes=90)
        c = await rig.cmd(acc, "hunt.select", slug="kabuto", hours=48)
        assert c["status"] == "failed" and "params inválidos" in c["error"]
        c = await rig.cmd(acc, "hunt.release")
        assert c["status"] == "done" and rig.store.configs[acc.id]["hunt_hold"][0] is False
    finally:
        await rig.close()
