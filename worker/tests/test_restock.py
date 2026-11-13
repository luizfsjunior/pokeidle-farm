"""Fase 3a: reposição de consumíveis (docs/design/fase-3-reposicao.md)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode, AutoSet, RateLimiter, ShopBuy
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.restock import RestockConfig, RestockPlugin
from pokeidle_farm.store.memory import MemoryStore

AUTOMATION = {
    "autoBallAteCapturar": False,
    "autoBallSemParar": True,
    "ballIds": [1, 4, 3, 5],
    "autoPotion": True,
    "potionIds": [200, 201],
    "hpLimiar": 0.3,
}


def ev(type_: str, **data: Any) -> Event:
    return Event(account_id=uuid4(), session_id=uuid4(), type=type_, data=data)


class Harness:
    """Plugin com gateway real (modo e relógios controlados) e estado editável."""

    def __init__(self, mode: ActionMode = ActionMode.ENABLED, **cfg: Any) -> None:
        self.now = 0.0
        self.sent: list[dict[str, Any]] = []
        self.recorded: list[tuple[str, dict[str, Any]]] = []
        self.state = AccountStateView(
            level=10,
            hunt_slug="magikarp",
            items={"200": 100, "205": 20},
            balls={"1": 500, "2": 0, "4": 0},
            gold=100_000,
            automation=dict(AUTOMATION),
        )

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.recorded.append((t, d))

        self.gateway = ActionGateway(
            "acc", mode, send=send, record=record, limiter=RateLimiter(clock=lambda: self.now)
        )
        self.plugin = RestockPlugin()
        self.plugin.clock = lambda: self.now
        self.ctx = PluginContext(
            account_id=uuid4(),
            nick="farm1",
            config=RestockConfig.model_validate(cfg),
            bus=EventBus(),
            actions=self.gateway,
            state=self.state,
            store=MemoryStore(),
            settings=None,
            log=logging.getLogger("test"),
        )

    async def start(self) -> Harness:
        await self.plugin.start(self.ctx)
        return self

    async def send_ev(self, event: Event) -> None:
        await self.plugin.on_event(event)

    async def kills(self, n: int, gold: int = 41, hunt: str = "magikarp") -> None:
        for _ in range(n):
            await self.send_ev(ev("kill", gold=gold, gold_autosell=0, hunt_slug=hunt))

    async def patch(self, **changes: Any) -> None:
        for k, v in changes.items():
            setattr(self.state, k, v)
        await self.send_ev(ev("state.patch"))

    def wires(self, t: str) -> list[dict[str, Any]]:
        return [p for p in self.sent if p["t"] == t]

    def events(self, t: str) -> list[dict[str, Any]]:
        return [d for typ, d in self.recorded if typ == t]


# --- ações --------------------------------------------------------------------


def test_shop_buy_wire():
    assert ShopBuy(kind="ball", id=1, qty=1).to_wire() == {
        "t": "shop.buy",
        "kind": "ball",
        "id": 1,
        "qty": 1,
    }
    assert ShopBuy(kind="item", id=200, qty=5).to_wire() == {
        "t": "shop.buy",
        "kind": "item",
        "id": 200,
        "qty": 5,
    }


def test_auto_set_wire_is_flat_and_complete():
    wire = AutoSet(automation=AUTOMATION).to_wire()
    assert wire == {"t": "auto.set", **AUTOMATION}


# --- estado da conta ----------------------------------------------------------


def test_state_view_applies_snapshot_and_patch():
    sv = AccountStateView()
    sv.apply(
        ev(
            "state.snapshot",
            level=2,
            hunt_slug="magikarp",
            items={"200": 100},
            balls={"1": 100},
            gold=1000,
            automation=AUTOMATION,
        )
    )
    assert (sv.level, sv.gold, sv.balls, sv.items) == (2, 1000, {"1": 100}, {"200": 100})
    assert sv.automation == AUTOMATION
    sv.apply(ev("state.patch", gold=1041, balls={"1": 99}, items={"205": 3}))
    assert sv.gold == 1041
    assert sv.balls == {"1": 99}
    assert sv.items == {"200": 100, "205": 3}  # merge: patch parcial não apaga o resto
    sv.apply(ev("kill", gold=41))  # outros eventos não mexem no estado
    assert sv.gold == 1041


# --- escolha da bola (foco captura) -------------------------------------------


async def test_picks_best_ball_that_pays_for_itself():
    h = await Harness().start()
    await h.kills(60, gold=41)  # 41 por abate → Great (20) se paga, Super (50) não
    (wire,) = h.wires("auto.set")
    assert wire["ballIds"][0] == 2
    assert wire["ballIds"] == [2, 1, 4, 3, 5]
    assert wire["autoBallSemParar"] is True and wire["autoBallAteCapturar"] is False
    assert wire["hpLimiar"] == 0.3  # parte do objeto atual


async def test_needs_min_kills_before_touching_ball():
    h = await Harness().start()
    await h.kills(49)
    assert h.wires("auto.set") == [] and h.wires("shop.buy") == []


async def test_net_gold_discounts_potions_and_revives():
    h = await Harness().start()
    h.state.automation = {**AUTOMATION, "ballIds": [4, 1, 3, 5]}
    for _ in range(60):
        await h.send_ev(ev("kill", gold=41, gold_autosell=0, hunt_slug="magikarp"))
        await h.send_ev(ev("item.consumed", item_id=200, qty=1, unit_price=26))
    # líquido sem as bolas = 41 − 26 = 15 por abate → só a Poké (5) se paga
    (wire,) = h.wires("auto.set")
    assert wire["ballIds"] == [1, 4, 3, 5]


async def test_no_ball_pays_turns_balls_off():
    h = await Harness().start()
    await h.kills(60, gold=4)  # nem a Poké (5) se paga
    (wire,) = h.wires("auto.set")
    assert wire["autoBallSemParar"] is False and wire["autoBallAteCapturar"] is False
    assert h.wires("shop.buy") == []


async def test_gold_xp_drop_focus_turns_balls_off_and_buys_none():
    h = await Harness(focus="gold_xp_drop").start()
    h.state.balls = {"1": 0}
    await h.kills(60)
    (wire,) = h.wires("auto.set")
    assert wire["autoBallSemParar"] is False and wire["autoBallAteCapturar"] is False
    assert wire["ballIds"] == AUTOMATION["ballIds"]
    assert h.wires("shop.buy") == []


async def test_auto_set_only_when_something_changes():
    h = await Harness().start()
    h.state.automation = {**AUTOMATION, "ballIds": [2, 1, 4, 3, 5]}
    await h.kills(80)
    assert h.wires("auto.set") == []


async def test_auto_set_is_not_repeated_while_waiting():
    h = await Harness().start()
    await h.kills(60)
    h.now = 30.0
    await h.kills(10)  # o servidor ainda não devolveu a automation nova
    assert len(h.wires("auto.set")) == 1
    h.now = 61.0
    await h.kills(1)
    assert len(h.wires("auto.set")) == 2


async def test_hunt_change_resets_window():
    h = await Harness().start()
    await h.kills(40, hunt="magikarp")
    await h.kills(40, hunt="caverna")  # 80 abates, mas só 40 na hunt atual
    assert h.wires("auto.set") == []


# --- compras ------------------------------------------------------------------


async def test_buys_chosen_ball_up_to_target():
    h = await Harness(ball_min=100, ball_target=1000).start()
    h.state.automation = {**AUTOMATION, "ballIds": [2, 1, 4, 3, 5]}
    h.state.balls = {"1": 500, "2": 30}
    await h.kills(60)
    (buy,) = h.wires("shop.buy")
    assert buy == {"t": "shop.buy", "kind": "ball", "id": 2, "qty": 970}


async def test_restocks_items_from_rules():
    h = await Harness(items=[{"id": 205, "min": 25, "target": 40}]).start()
    await h.send_ev(ev("state.patch"))
    (buy,) = h.wires("shop.buy")
    assert buy == {"t": "shop.buy", "kind": "item", "id": 205, "qty": 20}


async def test_respects_gold_reserve():
    h = await Harness(items=[{"id": 205, "min": 25, "target": 40}], gold_reserve=97_000).start()
    await h.send_ev(ev("state.patch"))  # 100.000 − 97.000 = 3.000 → 5 revives de 600
    (buy,) = h.wires("shop.buy")
    assert buy["qty"] == 5


async def test_respects_hourly_cap():
    h = await Harness(items=[{"id": 205, "min": 25, "target": 40}], max_gold_per_hour=1_200).start()
    await h.send_ev(ev("state.patch"))
    (buy,) = h.wires("shop.buy")
    assert buy["qty"] == 2
    await h.patch(items={"200": 100, "205": 22}, gold=98_800)  # confirmou
    h.now = 120.0
    await h.send_ev(ev("state.patch"))
    assert len(h.wires("shop.buy")) == 1  # teto da hora já gasto
    assert h.events("restock.failed")[-1]["reason"] == "sem_ouro"
    h.now = 3_700.0
    await h.send_ev(ev("state.patch"))
    assert len(h.wires("shop.buy")) == 2  # a hora passou


async def test_one_purchase_at_a_time_and_confirmation():
    h = await Harness(
        items=[{"id": 200, "min": 50, "target": 100}, {"id": 205, "min": 25, "target": 40}]
    ).start()
    h.state.items = {"200": 10, "205": 5}
    await h.send_ev(ev("state.patch"))
    await h.send_ev(ev("state.patch"))
    assert [b["id"] for b in h.wires("shop.buy")] == [200]  # espera a primeira
    h.now = 11.0
    await h.patch(items={"200": 100, "205": 5}, gold=95_500)
    assert h.events("restock.bought") == [
        {"kind": "item", "id": 200, "qty": 90, "gold_spent": 4_500}
    ]
    assert [b["id"] for b in h.wires("shop.buy")] == [200, 205]


async def test_purchase_timeout_is_reported():
    h = await Harness(items=[{"id": 205, "min": 25, "target": 40}], confirm_timeout_s=15).start()
    await h.send_ev(ev("state.patch"))
    h.now = 16.0
    await h.send_ev(ev("state.patch"))  # o estoque não subiu
    assert h.events("restock.failed") == [{"kind": "item", "id": 205, "reason": "timeout"}]
    assert h.events("restock.bought") == []


async def test_observe_only_reports_without_storm():
    h = Harness(mode=ActionMode.OBSERVE_ONLY, items=[{"id": 205, "min": 25, "target": 40}])
    await h.start()
    for _ in range(5):
        await h.send_ev(ev("state.patch"))
    assert h.sent == []
    failed = h.events("restock.failed")
    assert failed == [{"kind": "item", "id": 205, "reason": "observe_only"}]  # uma vez só
    h.now = 61.0
    await h.send_ev(ev("state.patch"))
    assert len(h.events("restock.failed")) == 2  # tenta de novo depois do retry_after_s
