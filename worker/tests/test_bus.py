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


class _SlowStart(Plugin):
    name: ClassVar[str] = "devagar"
    subscribes: ClassVar[set[str]] = {"kill"}
    always_on: ClassVar[bool] = True
    started: ClassVar[int] = 0

    async def start(self, ctx) -> None:  # type: ignore[no-untyped-def]
        await super().start(ctx)
        await asyncio.sleep(0.05)
        type(self).started += 1

    async def on_event(self, event: Event) -> None:
        return None


async def test_restart_waits_for_a_running_start_all():
    """A partida da sessão e o reinício pelo painel não sobem o mesmo plugin duas vezes."""
    from types import SimpleNamespace

    _SlowStart.started = 0
    host = PluginHost({"devagar": _SlowStart})
    bus = EventBus()

    def make_ctx(cls, cfg):  # type: ignore[no-untyped-def]
        return SimpleNamespace(config=cfg, log=None, nick="t")

    boot = asyncio.create_task(host.start_all(bus, {}, make_ctx))
    await asyncio.sleep(0)
    await host.restart("devagar", bus, {}, make_ctx)
    await boot
    assert list(host.running) == ["devagar"]
    assert _SlowStart.started == 2  # a partida e depois o reinício, um de cada vez
    assert len([s for s in bus._subs if s.name.endswith("devagar")]) == 1
