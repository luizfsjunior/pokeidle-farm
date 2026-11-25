"""Captura manual: o worker joga a bola (docs/design/captura-manual.md, T4 a T13)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.ball_thrower import BallThrowerPlugin
from pokeidle_farm.plugins.base import AccountStateView, EmptyConfig, PluginContext
from pokeidle_farm.store.memory import MemoryStore

T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


class World:
    """Plugin com gateway real; `sleep` avança o relógio (os dois relógios andam juntos)."""

    def __init__(self, balls: dict[str, int] | None = None, capture: dict[str, Any] | None = None):
        self.t = 0.0  # segundos desde T0
        self.sent: list[tuple[float, dict[str, Any]]] = []
        self.rec: list[tuple[str, dict[str, Any]]] = []
        self.state = AccountStateView()
        self.state.balls = balls if balls is not None else {"1": 95, "4": 30, "5": 10}
        self.state.capture = capture

        async def send(m: dict[str, Any]) -> None:
            self.sent.append((self.t, m))

        async def record(t: str, d: dict[str, Any]) -> None:
            self.rec.append((t, d))

        gw = ActionGateway(
            "acc", ActionMode.ENABLED, send=send, record=record,
            limiter=RateLimiter(clock=lambda: self.t),
        )  # fmt: skip
        self.ctx = PluginContext(
            account_id=uuid4(), nick="farm2", config=EmptyConfig(), bus=EventBus(), actions=gw,
            state=self.state, store=MemoryStore(), settings=None, log=logging.getLogger("t"),
        )  # fmt: skip
        self.plugin = BallThrowerPlugin()
        self.plugin.now = lambda: T0 + timedelta(seconds=self.t)
        self.plugin.clock = lambda: self.t

        async def sleep(s: float) -> None:
            self.t += s

        self.plugin.sleep = sleep

    async def start(self) -> World:
        await self.plugin.start(self.ctx)
        return self

    async def kill(self, slot: int, name: str = "Pichu", shiny: bool = False, age_s: float = 0):
        at = T0 + timedelta(seconds=self.t - age_s)
        await self.plugin.on_event(
            Event(
                account_id=self.ctx.account_id, session_id=uuid4(), type="kill", received_at=at,
                data={"slot": slot, "wild_name": name, "shiny": shiny, "hunt_slug": "pichu"},
            )
        )  # fmt: skip

    def throws(self) -> list[dict[str, Any]]:
        return [m for _, m in self.sent if m["t"] == "ball.throw"]


PICHU = {"species_id": 172, "species_name": "Pichu", "ball_id": 1}


async def test_capture_throws_on_target_species():
    """T4."""
    w = await World(capture=PICHU).start()
    await w.kill(67)
    assert w.throws() == [{"t": "ball.throw", "ballId": 1, "slot": 67}]


async def test_capture_ignores_other_species():
    """T5."""
    w = await World(capture=PICHU).start()
    await w.kill(67, name="Pikachu")
    assert w.throws() == []


async def test_no_capture_no_throw():
    """T6."""
    w = await World().start()
    await w.kill(67)
    assert w.throws() == []


async def test_shiny_gets_the_best_ball_anywhere():
    """T7: sem captura ativa, com Beast em estoque."""
    w = await World(balls={"1": 95, "4": 30, "5": 10}).start()
    await w.kill(3, name="Rattata", shiny=True)
    assert w.throws() == [{"t": "ball.throw", "ballId": 5, "slot": 3}]


async def test_shiny_without_beast_and_without_balls():
    """T8."""
    w = await World(balls={"1": 95, "4": 30}).start()
    await w.kill(3, shiny=True)
    assert w.throws()[-1]["ballId"] == 4
    empty = await World(balls={"1": 0, "2": 0}).start()
    await empty.kill(3, name="Rattata", shiny=True)
    assert empty.throws() == []
    (missed,) = [d for t, d in empty.rec if t == "ball_thrower.shiny_missed"]
    assert missed["slot"] == 3 and missed["wild_name"] == "Rattata"


async def test_shiny_of_target_gets_one_best_ball():
    """T9: a regra do shiny ganha, uma bola só."""
    w = await World(capture=PICHU).start()
    await w.kill(67, shiny=True)
    assert w.throws() == [{"t": "ball.throw", "ballId": 5, "slot": 67}]


async def test_throws_are_spaced():
    """T10: o segundo arremesso sai pelo menos 1,2 s depois do primeiro."""
    w = await World(capture=PICHU).start()
    await w.kill(1)
    await w.kill(2)
    (t1, a), (t2, b) = w.sent
    assert (a["slot"], b["slot"]) == (1, 2) and t2 - t1 >= 1.2


async def test_body_past_30s_is_dropped():
    """T11."""
    w = await World(capture=PICHU).start()
    await w.kill(1, age_s=31)
    assert w.throws() == []


async def test_chosen_ball_out_of_stock_falls_back_below():
    """T12."""
    w = await World(balls={"1": 50, "3": 10}, capture={**PICHU, "ball_id": 4}).start()
    await w.kill(1)
    assert w.throws()[-1]["ballId"] == 3


async def test_worth_ball_or_poke():
    """T13 (o lado do thrower; o restock calcula a worth_ball, ver test_restock)."""
    w = await World(balls={"1": 50, "3": 10, "4": 5}, capture={**PICHU, "ball_id": None}).start()
    w.state.worth_ball = 3
    await w.kill(1)
    assert w.throws()[-1]["ballId"] == 3
    w.state.worth_ball = None  # menos de 50 abates
    w.t += 2
    await w.kill(2)
    assert w.throws()[-1]["ballId"] == 1


# --- bola em tudo (state.catch_all, do restock no foco capture) ---------------------------


async def test_catch_all_throws_worth_ball_on_every_body():
    """Bola em tudo: todo corpo, de qualquer espécie, leva a worth_ball (o shiny sai no arremesso)."""
    w = await World(balls={"1": 95, "4": 30}).start()
    w.state.catch_all, w.state.worth_ball = True, 4
    await w.kill(10, name="Magikarp")
    await w.kill(11, name="Horsea")
    assert w.throws() == [
        {"t": "ball.throw", "ballId": 4, "slot": 10},
        {"t": "ball.throw", "ballId": 4, "slot": 11},
    ]


async def test_catch_all_without_worth_ball_does_not_throw():
    """Sem bola que se pague (ou com menos de 50 abates), a bola em tudo não joga nada."""
    w = await World().start()
    w.state.catch_all, w.state.worth_ball = True, None
    await w.kill(10, name="Magikarp")
    assert w.throws() == []


async def test_catch_all_off_keeps_old_behaviour():
    """Sem bola em tudo, a worth_ball sozinha não faz jogar (só captura ativa e shiny)."""
    w = await World().start()
    w.state.worth_ball = 4
    await w.kill(10, name="Magikarp")
    assert w.throws() == []


async def test_catch_all_and_capture_target_together():
    """O alvo usa a bola dele; os outros corpos, a worth_ball."""
    w = await World(capture={**PICHU, "ball_id": 5}).start()
    w.state.catch_all, w.state.worth_ball = True, 1
    await w.kill(20, name="Pichu")
    await w.kill(21, name="Magikarp")
    assert w.throws() == [
        {"t": "ball.throw", "ballId": 5, "slot": 20},
        {"t": "ball.throw", "ballId": 1, "slot": 21},
    ]


async def test_catch_all_worth_ball_out_of_stock_falls_back_below():
    w = await World(balls={"1": 95, "4": 0}).start()
    w.state.catch_all, w.state.worth_ball = True, 4
    await w.kill(10, name="Magikarp")
    assert w.throws() == [{"t": "ball.throw", "ballId": 1, "slot": 10}]
