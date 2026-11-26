"""Tier da Outland: regra do maior liberado, plugin outland_tier e comando outland.tier."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode, OutlandTierSelect, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event, Translator
from pokeidle_farm.outland_model import best_tier, current_tier, outland_tiers, tier_upgrade
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.outland_tier import OutlandTierConfig, OutlandTierPlugin
from pokeidle_farm.protocol.codec import decode
from pokeidle_farm.store.memory import MemoryStore

from .test_commands import farm, rig  # noqa: F401  (fixture)

# o formato do welcome (shared/outland-tiers.mjs): tier = 100 + número
ESCADA = [(150, 1), (500, 1.1), (750, 1.15), (1_000, 1.25), (2_000, 1.85), (2_250, 2), (65_000, 20)]
RULES = {
    "outlandTiers": [
        {"tier": 101 + i, "numero": i + 1, "rotulo": f"Outland {i + 1}", "nivel": lv, "mult": m}
        for i, (lv, m) in enumerate(ESCADA)
    ]
}
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


# --- regra -------------------------------------------------------------------


def test_best_tier_is_the_highest_unlocked():
    tiers = outland_tiers(RULES)
    assert best_tier(tiers, 149) is None
    assert best_tier(tiers, 150).tier == 101
    assert best_tier(tiers, 999).tier == 102 + 1  # 750 libera a Outland 3
    assert best_tier(tiers, 2_300).number == 6


def test_tier_id_falls_back_to_position_without_tier_field():
    old = {"outlandTiers": [{"nivel": 150, "mult": 1}, {"nivel": 500, "mult": 1.1}]}
    assert [t.tier for t in outland_tiers(old)] == [101, 102]


def test_current_tier_handles_default_and_legacy_steps():
    tiers = outland_tiers(RULES)
    assert current_tier(tiers, None).tier == 101  # sem outlandTier: o padrão do jogo
    assert current_tier(tiers, 104).number == 4
    # degrau antigo 3 = nível 2.000: o tier novo mais alto até ele (Outland 5, nível 2.000)
    assert current_tier(tiers, 3).tier == 105


def test_upgrade_only_when_better_tier_is_unlocked():
    assert tier_upgrade(RULES, 149, None) is None  # Outland ainda trancada
    assert tier_upgrade(RULES, 300, None) is None  # só a Outland 1 liberada
    assert tier_upgrade(RULES, 300, 101) is None
    assert tier_upgrade(RULES, 520, None).tier == 102
    assert tier_upgrade(RULES, 520, 102) is None
    assert tier_upgrade(RULES, 2_100, 3) is None  # degrau antigo 3 já é a Outland 5
    assert tier_upgrade(RULES, 2_300, 3).tier == 106
    assert tier_upgrade({}, 5_000, None) is None  # sem regras: não mexe


def test_action_wire():
    assert OutlandTierSelect(tier=105).to_wire() == {"t": "outland.tier", "tier": 105}


def test_translator_carries_outland_tier():
    tr = Translator(uuid4(), uuid4())
    msg, raw = decode(json.dumps({"t": "estado", "estado": {"outlandTier": 103}}))
    (ev,) = [e for e in tr.translate(msg, raw) if e.type == "state.patch"]
    view = AccountStateView()
    view.apply(ev)
    assert view.outland_tier == 103


# --- plugin ------------------------------------------------------------------


class Rig:
    def __init__(self, level: int | None, tier: int | None = None, **cfg: Any) -> None:
        self.now = NOW
        self.sent: list[dict[str, Any]] = []
        self.notes: list[tuple[str, dict[str, Any]]] = []

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.notes.append((t, d))

        self.state = AccountStateView(level=level, outland_tier=tier)
        self.plugin = OutlandTierPlugin()
        self.plugin.now = lambda: self.now
        self.ctx = PluginContext(
            account_id=uuid4(),
            nick="farm1",
            config=OutlandTierConfig.model_validate(cfg),
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
            catalog=SimpleNamespace(rules=RULES),
        )

    async def start(self) -> Rig:
        await self.plugin.start(self.ctx)
        return self

    async def tick(self) -> None:
        await self.plugin.on_event(
            Event(account_id=uuid4(), session_id=uuid4(), type="state.patch", data={})
        )

    def tiers_sent(self) -> list[int]:
        return [p["tier"] for p in self.sent if p["t"] == "outland.tier"]

    def note(self, t: str) -> list[dict[str, Any]]:
        return [d for typ, d in self.notes if typ == t]


async def test_plugin_moves_up_and_confirms():
    r = await Rig(level=800).start()
    assert r.tiers_sent() == [103]
    assert r.note("outland.tier_set")[0]["number"] == 3
    await r.tick()  # sem resposta ainda: não repete
    assert r.tiers_sent() == [103]
    r.state.outland_tier = 103
    await r.tick()
    assert r.note("outland.tier_changed") == [{"tier": 103, "number": 3, "mult": 1.15}]
    await r.tick()
    assert r.tiers_sent() == [103]


async def test_plugin_follows_the_trainer_level():
    r = await Rig(level=400, tier=101).start()
    assert r.tiers_sent() == []
    r.state.level = 501
    await r.tick()
    assert r.tiers_sent() == [102]


async def test_plugin_retries_after_no_confirmation():
    r = await Rig(level=600, confirm_s=60, retry_min=30).start()
    assert r.tiers_sent() == [102]
    r.now = NOW + timedelta(seconds=61)
    await r.tick()
    assert r.note("outland.tier_failed")[0]["reason"] == "sem_confirmacao"
    r.now = NOW + timedelta(minutes=10)
    await r.tick()
    assert r.tiers_sent() == [102]  # ainda esperando o retry
    r.now = NOW + timedelta(minutes=32)
    await r.tick()
    assert r.tiers_sent() == [102, 102]


async def test_plugin_does_nothing_below_150_without_rules_or_when_inactive():
    assert (await Rig(level=120).start()).tiers_sent() == []
    r = Rig(level=5_000)
    r.ctx.catalog = None
    await r.start()
    assert r.tiers_sent() == []
    assert (await Rig(level=5_000, active=False).start()).tiers_sent() == []


# --- comando -----------------------------------------------------------------


def _wire(rig_: Any, level: int, tier: int | None) -> list[Any]:
    s = rig_.sessions[0]
    s.catalog = SimpleNamespace(rules=RULES, hunts={})  # type: ignore[attr-defined]
    s.state_view = AccountStateView(level=level, outland_tier=tier)  # type: ignore[attr-defined]
    sent: list[Any] = []

    async def confirm(check, since, within):  # type: ignore[no-untyped-def]
        s.state_view.outland_tier = sent[-1].tier  # o jogo aplica na hora
        return None if check() else "não mudou"

    class Gateway:
        async def submit(self, action, *, source):  # type: ignore[no-untyped-def]
            sent.append(action)

    s.confirm = confirm  # type: ignore[attr-defined]
    s.gateway = Gateway()  # type: ignore[attr-defined]
    return sent


async def test_command_picks_best_or_number_and_refuses_locked(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    await rig.boot()
    sent = _wire(rig, level=800, tier=None)
    c = await rig.cmd(acc, "outland.tier")
    assert c["status"] == "done", c["error"]
    assert c["result"]["tier"] == 103 and sent[-1].tier == 103
    c = await rig.cmd(acc, "outland.tier", number=2)
    assert c["status"] == "done" and sent[-1].tier == 102
    assert "Outland 3 está liberada" in c["result"]["warning"]
    c = await rig.cmd(acc, "outland.tier", number=4)
    assert c["status"] == "failed" and "pede nível 1000" in c["error"]
    c = await rig.cmd(acc, "outland.tier", number=2)
    assert c["status"] == "done" and c["result"]["detail"] == "já estava nesse tier"
