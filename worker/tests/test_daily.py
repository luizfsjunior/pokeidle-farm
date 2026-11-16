"""Plugin daily: passe de batalha (docs/design/simulador-4-decisoes.md)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode, PassClaim, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.daily import DailyConfig, DailyPlugin, pass_day
from pokeidle_farm.store.memory import MemoryStore

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
TODAY = pass_day(NOW.timestamp() * 1000)


class Rig:
    def __init__(self, level: int = 33, ultimo: int = 0, **cfg: Any) -> None:
        self.now = NOW
        self.sent: list[dict[str, Any]] = []
        self.notes: list[tuple[str, dict[str, Any]]] = []

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.notes.append((t, d))

        self.state = AccountStateView(level=level)
        self.state.battle_pass = {"degrau": 0, "ultimo": ultimo, "total": 0}
        self.plugin = DailyPlugin()
        self.plugin.now = lambda: self.now
        self.ctx = PluginContext(
            account_id=uuid4(),
            nick="farm1",
            config=DailyConfig.model_validate(cfg),
            bus=EventBus(),
            actions=ActionGateway(
                "acc",
                ActionMode.ENABLED,
                send=send,
                record=record,
                limiter=RateLimiter(clock=lambda: self.now.timestamp()),
            ),
            state=self.state,
            store=MemoryStore(),
            settings=None,
            log=logging.getLogger("t"),
        )

    async def start(self) -> Rig:
        await self.plugin.start(self.ctx)
        return self

    async def tick(self) -> None:
        await self.plugin.on_event(
            Event(account_id=uuid4(), session_id=uuid4(), type="kill", data={})
        )

    def claims(self) -> int:
        return sum(p["t"] == "passe.resgatar" for p in self.sent)

    def note(self, t: str) -> list[dict[str, Any]]:
        return [d for typ, d in self.notes if typ == t]


def test_pass_day_turns_at_midnight_brasilia():
    before = datetime(2026, 11, 16, 2, 59, tzinfo=UTC).timestamp() * 1000
    after = datetime(2026, 11, 16, 3, 0, tzinfo=UTC).timestamp() * 1000
    assert pass_day(after) == pass_day(before) + 1
    assert PassClaim().to_wire() == {"t": "passe.resgatar"}


async def test_claims_once_and_confirms():
    r = await Rig().start()
    assert r.claims() == 1
    await r.tick()
    assert r.claims() == 1  # aguardando a confirmação
    r.state.battle_pass = {"degrau": 1, "ultimo": TODAY, "total": 1}
    await r.tick()
    assert r.note("daily.claimed") == [{"day": TODAY, "step": 1, "total": 1}]
    r.now += timedelta(hours=2)
    await r.tick()
    assert r.claims() == 1  # já resgatou hoje
    r.now = NOW + timedelta(days=1)
    await r.tick()
    assert r.claims() == 2  # dia novo


async def test_already_claimed_or_low_level_does_nothing():
    assert (await Rig(ultimo=TODAY).start()).claims() == 0
    assert (await Rig(level=9).start()).claims() == 0
    assert (await Rig(claim_pass=False).start()).claims() == 0


async def test_no_confirmation_reports_and_retries_later():
    r = await Rig().start()
    r.now += timedelta(seconds=61)
    await r.tick()
    assert r.note("daily.failed") == [{"day": TODAY, "reason": "sem_confirmacao"}]
    r.now += timedelta(minutes=10)
    await r.tick()
    assert r.claims() == 1  # espera o retry_min
    r.now += timedelta(minutes=21)
    await r.tick()
    assert r.claims() == 2
