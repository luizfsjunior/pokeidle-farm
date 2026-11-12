import asyncio
from typing import ClassVar
from uuid import uuid4

import pytest
from pydantic import BaseModel

from pokeidle_farm.actions import ActionBlocked, ActionGateway, ActionMode, ActionSpec, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event


def ev(type_: str = "kill") -> Event:
    return Event(account_id=uuid4(), session_id=uuid4(), type=type_)


async def test_slow_subscriber_does_not_block_others():
    bus = EventBus()
    fast: list[str] = []
    release = asyncio.Event()

    async def slow(_: Event) -> None:
        await release.wait()

    async def quick(e: Event) -> None:
        fast.append(e.type)

    bus.subscribe("slow", "*", slow)
    bus.subscribe("quick", {"kill"}, quick)
    for _ in range(3):
        await bus.publish(ev())
    await bus.publish(ev("other"))
    await asyncio.sleep(0.05)
    assert fast == ["kill", "kill", "kill"]  # filtra por tipo e não espera o lento
    release.set()
    await bus.close()


async def test_handler_error_is_isolated():
    errors: list[str] = []
    bus = EventBus(on_error=lambda name, exc: errors.append(name))
    got: list[Event] = []

    async def boom(_: Event) -> None:
        raise RuntimeError("x")

    async def ok(e: Event) -> None:
        got.append(e)

    bus.subscribe("boom", "*", boom)
    bus.subscribe("ok", "*", ok)
    await bus.publish(ev())
    await bus.publish(ev())
    await bus.drain()
    assert errors == ["boom", "boom"] and len(got) == 2
    await bus.close()


async def test_full_queue_drops_oldest():
    bus = EventBus()
    release = asyncio.Event()
    seen: list[str] = []

    async def h(e: Event) -> None:
        await release.wait()
        seen.append(e.type)

    bus.subscribe("h", "*", h, maxsize=2)
    await bus.publish(ev("a"))
    await asyncio.sleep(0.01)  # "a" em processamento
    for t in ("b", "c", "d"):
        await bus.publish(ev(t))
    release.set()
    await bus.drain()
    assert seen == ["a", "c", "d"]
    await bus.close()


class _Result(BaseModel):
    ok: bool


class FakeAction(ActionSpec):
    name: ClassVar[str] = "fake"
    description: ClassVar[str] = "ação de teste"
    result_model: ClassVar[type[BaseModel]] = _Result
    min_interval_s: ClassVar[float] = 10.0
    x: int = 1

    def to_wire(self):
        return {"t": "fake", "x": self.x}


async def test_observe_only_blocks_everything():
    sent, recorded = [], []

    async def send(p):
        sent.append(p)

    async def record(t, d):
        recorded.append((t, d["reason"]))

    gw = ActionGateway("acc", ActionMode.OBSERVE_ONLY, send=send, record=record)
    with pytest.raises(ActionBlocked, match="observe_only"):
        await gw.submit(FakeAction(), source="test")
    assert sent == [] and recorded == [("action.blocked", "observe_only")]


async def test_rate_limit_when_enabled():
    t = [0.0]
    sent = []

    async def send(p):
        sent.append(p)

    gw = ActionGateway(
        "acc", ActionMode.ENABLED, send=send, limiter=RateLimiter(clock=lambda: t[0])
    )
    await gw.submit(FakeAction(x=1), source="test")
    with pytest.raises(ActionBlocked, match="rate_limit"):
        await gw.submit(FakeAction(x=2), source="test")
    t[0] = 10.0
    await gw.submit(FakeAction(x=3), source="test")
    assert [p["x"] for p in sent] == [1, 3]
