"""Parada de assinantes com prazo (reinício de plugin pelo painel, 17/11)."""

import asyncio
from typing import ClassVar
from uuid import uuid4

from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import Plugin
from pokeidle_farm.plugins.registry import PluginHost


def _ev(type_: str) -> Event:
    return Event(account_id=uuid4(), session_id=uuid4(), type=type_)


async def test_unsubscribe_with_timeout_drops_a_stuck_queue():
    bus = EventBus()
    seen: list[str] = []
    gate = asyncio.Event()

    async def stuck(ev: Event) -> None:
        seen.append(ev.type)
        await gate.wait()  # nunca libera: um handler travado

    unsub = bus.subscribe("lento", "*", stuck)
    for i in range(5):
        await bus.publish(_ev(f"e{i}"))
    await asyncio.sleep(0)
    await asyncio.wait_for(unsub(drain_s=0.05), 1)  # não trava
    await bus.publish(_ev("depois"))
    assert seen == ["e0"]


async def test_unsubscribe_without_timeout_still_drains():
    bus = EventBus()
    seen: list[str] = []

    async def ok(ev: Event) -> None:
        seen.append(ev.type)

    unsub = bus.subscribe("ok", "*", ok)
    for i in range(3):
        await bus.publish(_ev(f"e{i}"))
    await unsub()
    assert seen == ["e0", "e1", "e2"]


class _SlowStop(Plugin):
    name: ClassVar[str] = "lento"
    subscribes: ClassVar[set[str]] = {"kill"}

    async def on_event(self, event: Event) -> None:
        return None

    async def stop(self) -> None:
        await asyncio.sleep(3600)


async def test_stop_one_does_not_hang_on_a_slow_stop():
    host = PluginHost({})
    host.running["lento"] = _SlowStop()

    async def unsub(drain_s: float | None = None) -> None:
        return None

    host._unsubs["lento"] = unsub
    await asyncio.wait_for(host.stop_one("lento", drain_s=0.01, stop_s=0.05), 1)
    assert "lento" not in host.running
