"""Fase 3a: reposição de consumíveis (docs/design/fase-3-reposicao.md)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
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
    "autoBallSemParar": False,
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
        cfg.setdefault("focus", "capture")  # o padrão do app é gold_xp_drop (caso 47)
        self.now = 0.0
        self.sent: list[dict[str, Any]] = []
        self.recorded: list[tuple[str, dict[str, Any]]] = []
        self.state = AccountStateView(
            level=10,
            hunt_slug="magikarp",
            items={"200": 100, "205": 20},
            # bolas no mínimo (captura-manual.md, P3): os testes que não são de bola não compram bola
            balls={"1": 1000, "2": 100, "3": 100, "4": 100},
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


# --- a bola que vale a pena e a bola automática (captura-manual.md) ------------


async def test_worth_ball_is_the_best_that_pays_for_itself():
    h = await Harness().start()
    await h.kills(60, gold=41)  # 41 por abate → Great (20) se paga, Super (50) não
    assert h.state.worth_ball == 2
    assert h.wires("auto.set") == []  # a bola automática já está desligada


async def test_worth_ball_needs_min_kills():
    h = await Harness().start()
    await h.kills(49)
    assert h.state.worth_ball is None


async def test_net_gold_discounts_potions_and_revives():
    h = await Harness().start()
    for _ in range(60):
        await h.send_ev(ev("kill", gold=41, gold_autosell=0, hunt_slug="magikarp"))
        await h.send_ev(ev("item.consumed", item_id=200, qty=1, unit_price=26))
    # líquido sem as bolas = 41 − 26 = 15 por abate → só a Poké (5) se paga
    assert h.state.worth_ball == 1


async def test_no_ball_pays_leaves_worth_ball_empty():
    h = await Harness().start()
    await h.kills(60, gold=4)  # nem a Poké (5) se paga: o ball_thrower usa a Poké
    assert h.state.worth_ball is None


async def test_hunt_change_resets_window():
    h = await Harness().start()
    await h.kills(40, hunt="magikarp")
    await h.kills(40, hunt="caverna")  # 80 abates, mas só 40 na hunt atual
    assert h.state.worth_ball is None


async def test_ball_flags_on_are_turned_off_in_any_focus():
    for focus in ("capture", "gold_xp_drop"):
        h = await Harness(focus=focus).start()
        h.state.automation = {**AUTOMATION, "autoBallSemParar": True}
        await h.kills(1)
        (wire,) = h.wires("auto.set")
        assert wire["autoBallSemParar"] is False and wire["autoBallAteCapturar"] is False
        assert wire["ballIds"] == AUTOMATION["ballIds"] and wire["hpLimiar"] == 0.3


async def test_auto_set_is_not_repeated_while_waiting():
    h = await Harness().start()
    h.state.automation = {**AUTOMATION, "autoBallSemParar": True}
    await h.kills(1)
    h.now = 30.0
    await h.kills(10)  # o servidor ainda não devolveu a automation nova
    assert len(h.wires("auto.set")) == 1
    h.now = 61.0
    await h.kills(1)
    assert len(h.wires("auto.set")) == 2


# --- compras ------------------------------------------------------------------


async def test_keeps_every_buyable_ball_above_min():
    """T16/T17: abaixo de 100, a Poké vai até 1.000 e as outras até 100; a Beast (5) nunca."""
    h = await Harness(focus="gold_xp_drop", ball_min=100, ball_target=1000).start()
    h.state.balls = {"1": 80, "2": 150, "3": 0, "4": 99, "5": 0}
    await h.kills(1)
    assert h.wires("shop.buy") == [{"t": "shop.buy", "kind": "ball", "id": 1, "qty": 920}]
    h.state.balls = {**h.state.balls, "1": 1000}
    h.now += 11
    await h.kills(1)
    h.state.balls = {**h.state.balls, "3": 100}
    h.now += 11
    await h.kills(1)
    assert h.wires("shop.buy")[1:] == [
        {"t": "shop.buy", "kind": "ball", "id": 3, "qty": 100},
        {"t": "shop.buy", "kind": "ball", "id": 4, "qty": 1},
    ]
    assert all(b["id"] != 5 for b in h.wires("shop.buy"))


async def test_no_ball_bought_at_the_gold_reserve():
    """T18."""
    h = await Harness(focus="gold_xp_drop", gold_reserve=100_000).start()
    h.state.balls = {"1": 0}
    await h.kills(1)
    assert h.wires("shop.buy") == []


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
    h = await Harness(
        items=[{"id": 205, "min": 25, "target": 40}],
        max_gold_per_hour=1_200,
        potions_uncapped=False,
    ).start()
    await h.send_ev(ev("state.patch"))
    (buy,) = h.wires("shop.buy")
    assert buy["qty"] == 2
    await h.patch(items={"200": 100, "205": 22}, gold=98_800)  # confirmou
    h.now = 120.0
    await h.send_ev(ev("state.patch"))
    assert len(h.wires("shop.buy")) == 1  # teto da hora já gasto
    assert h.events("restock.failed")[-1]["reason"] == "teto_hora"
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


async def test_late_confirmation_counts_toward_cap_and_blocks_rebuy():
    h = await Harness(
        items=[{"id": 205, "min": 25, "target": 40}],
        confirm_timeout_s=15,
        max_gold_per_hour=20_000,
        potions_uncapped=False,
    ).start()
    await h.send_ev(ev("state.patch"))  # compra 20 revives (12.000)
    h.now = 16.0
    await h.send_ev(ev("state.patch"))  # passou do prazo
    assert h.events("restock.failed")[-1]["reason"] == "timeout"
    h.now = 90.0
    await h.send_ev(ev("state.patch"))
    assert len(h.wires("shop.buy")) == 1  # não recompra enquanto pode chegar
    await h.patch(items={"200": 100, "205": 40}, gold=88_000)  # chegou atrasada
    assert h.events("restock.bought") == [
        {"kind": "item", "id": 205, "qty": 20, "gold_spent": 12_000, "late": True}
    ]
    h.now = 400.0
    await h.patch(items={"200": 100, "205": 10})  # gastou revives de novo
    (_, second) = h.wires("shop.buy")
    assert second["qty"] == 13  # sobrou 8.000 do teto: 13 × 600


async def test_late_window_expires():
    h = await Harness(items=[{"id": 205, "min": 25, "target": 40}], confirm_timeout_s=15).start()
    await h.send_ev(ev("state.patch"))
    h.now = 16.0
    await h.send_ev(ev("state.patch"))
    h.now = 400.0  # passou late_confirm_s (300)
    await h.patch(items={"200": 100, "205": 40})
    assert h.events("restock.bought") == []


async def test_hourly_cap_survives_restart():

    h = Harness(
        items=[{"id": 205, "min": 25, "target": 40}],
        max_gold_per_hour=1_200,
        potions_uncapped=False,
    )
    now = datetime.now(UTC)
    for minutes_ago, spent in ((30, 1_200), (90, 50_000)):  # a de 90 min não conta
        h.ctx.store.events.append(
            {
                "account_id": str(h.ctx.account_id),
                "type": "restock.bought",
                "received_at": (now - timedelta(minutes=minutes_ago)).isoformat(),
                "data": {"kind": "item", "id": 205, "qty": 2, "gold_spent": spent},
            }
        )
    await h.start()
    await h.send_ev(ev("state.patch"))
    assert h.wires("shop.buy") == []  # o teto já foi gasto antes do reinício
    assert h.events("restock.failed")[-1]["reason"] == "teto_hora"
    h.now = 31 * 60.0  # a compra de 30 min atrás sai da janela
    await h.send_ev(ev("state.patch"))
    assert h.wires("shop.buy")[0]["qty"] == 2


async def test_store_failure_on_start_does_not_break_plugin():
    h = Harness(items=[{"id": 205, "min": 25, "target": 40}])

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise ConnectionError("fora do ar")

    h.ctx.store.recent_events = boom  # type: ignore[method-assign]
    await h.start()
    await h.send_ev(ev("state.patch"))
    assert len(h.wires("shop.buy")) == 1


# --- foco rank (docs/design/fase-3b-rank-ligado.md, casos 39 a 42 e 47) -----------------


def test_default_focus_is_gold_xp_drop():
    assert RestockConfig().focus == "gold_xp_drop"
    assert RestockConfig().fallback_focus == "gold_xp_drop"


async def test_rank_active_never_sets_automation():
    h = await Harness(focus="rank").start()
    h.state.automation = {**AUTOMATION, "autoBallAteCapturar": True}
    await h.send_ev(ev("rank.mode", mode="active", ball_id=2))
    await h.kills(60, gold=500)
    assert h.wires("auto.set") == []


async def test_rank_fallback_turns_balls_off():
    h = await Harness(focus="rank").start()
    h.state.automation = {**AUTOMATION, "autoBallSemParar": True}
    await h.send_ev(ev("rank.mode", mode="fallback", reason="queue_empty"))
    (a,) = h.wires("auto.set")
    assert a["autoBallSemParar"] is False and a["autoBallAteCapturar"] is False


# --- poção pela de menor custo por HP útil (simulador camada 2) -------------------


async def test_potion_rule_switches_to_cheapest_per_useful_hp():
    # HP máximo 5.000: a Ultimate (3.000 HP por 1.500) sai a 0,5 de ouro por HP, a Small a 0,83
    h = Harness(focus="gold_xp_drop", items=[{"id": 200, "min": 50, "target": 100}])
    h.state.items = {"200": 0}
    h.state.active_pokemon = {"maxHp": 5_000}
    await h.start()
    await h.kills(1)
    (buy,) = h.wires("shop.buy")
    # 100 Small = 6.000 HP de estoque = 2 Ultimate (mínimo de 5 e alvo mínimo + 5)
    assert buy == {"t": "shop.buy", "kind": "item", "id": 204, "qty": 10}


async def test_potion_rule_keeps_small_with_low_hp_or_off():
    h = Harness(focus="gold_xp_drop", items=[{"id": 200, "min": 50, "target": 100}])
    h.state.items = {"200": 0}
    h.state.active_pokemon = {"maxHp": 468}
    await h.start()
    await h.kills(1)
    assert h.wires("shop.buy")[0]["id"] == 200
    off = Harness(
        focus="gold_xp_drop", potion_auto=False, items=[{"id": 200, "min": 50, "target": 100}]
    )
    off.state.items = {"200": 0}
    off.state.active_pokemon = {"maxHp": 5_000}
    await off.start()
    await off.kills(1)
    assert off.wires("shop.buy")[0]["id"] == 200


def test_best_potion_by_max_hp():
    from pokeidle_farm.catalog import best_potion

    assert best_potion(468)[0] == 200
    assert best_potion(2_000)[0] == 203  # Hyper: 1.000 HP por 800
    assert best_potion(4_500)[0] == 204  # Ultimate cabe inteira (70% de 4.500 > 3.000)


async def test_potions_uncapped_ignores_hourly_cap_but_not_reserve():
    h = Harness(
        focus="gold_xp_drop",
        potions_uncapped=True,
        max_gold_per_hour=1_000,
        items=[{"id": 200, "min": 50, "target": 100}],
    )
    h.state.items = {"200": 0}
    await h.start()
    await h.kills(1)
    assert h.wires("shop.buy")[0]["qty"] == 100  # 5.000 de ouro, acima do teto de 1.000/h
    capped = Harness(
        focus="gold_xp_drop",
        max_gold_per_hour=1_000,
        potions_uncapped=False,
        items=[{"id": 200, "min": 50, "target": 100}],
    )
    capped.state.items = {"200": 0}
    await capped.start()
    await capped.kills(1)
    assert capped.wires("shop.buy")[0]["qty"] == 20  # 1.000 / 50
    poor = Harness(
        focus="gold_xp_drop",
        potions_uncapped=True,
        gold_reserve=99_000,
        items=[{"id": 200, "min": 50, "target": 100}],
    )
    poor.state.items = {"200": 0}
    await poor.start()
    await poor.kills(1)
    assert poor.wires("shop.buy")[0]["qty"] == 20  # só os 1.000 acima da reserva


async def test_out_of_gold_still_says_sem_ouro():
    h = Harness(items=[{"id": 205, "min": 25, "target": 40}], gold_reserve=100_000)
    await h.start()
    await h.send_ev(ev("state.patch"))
    assert h.wires("shop.buy") == []
    assert h.events("restock.failed")[-1]["reason"] == "sem_ouro"


async def test_survival_items_ignore_the_hourly_cap_by_default():
    h = await Harness(items=[{"id": 205, "min": 25, "target": 40}], max_gold_per_hour=1).start()
    await h.send_ev(ev("state.patch"))
    assert h.wires("shop.buy")[0]["qty"] > 1


async def test_worth_ball_super_with_60_per_kill():
    """T13 (o lado do restock): 60 de ouro líquido por abate paga a Super (50), não a Ultra (130)."""
    h = await Harness().start()
    await h.kills(60, gold=60)
    assert h.state.worth_ball == 3
