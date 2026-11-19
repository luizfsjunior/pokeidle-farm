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
        cfg.setdefault("focus", "capture")  # o padrão do app é gold_xp_drop (caso 47)
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
    from datetime import UTC, datetime, timedelta

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


async def test_rank_active_buys_rank_ball_and_never_sets_automation():
    h = await Harness(focus="rank").start()
    await h.kills(60, gold=500)
    assert h.wires("auto.set") == []
    assert h.wires("shop.buy") == []
    await h.send_ev(ev("rank.mode", mode="active", ball_id=2))
    assert h.wires("shop.buy") == [{"t": "shop.buy", "kind": "ball", "id": 2, "qty": 1_000}]
    await h.kills(60, gold=500)
    assert h.wires("auto.set") == []


async def test_rank_mode_is_read_from_store_on_start():
    h = Harness(focus="rank")
    h.ctx.store.events.append(
        {
            "account_id": h.ctx.account_id,
            "type": "rank.mode",
            "received_at": datetime.now(UTC) - timedelta(hours=1),
            "data": {"mode": "active", "ball_id": 2},
        }
    )
    await h.start()
    await h.send_ev(ev("state.patch"))
    assert h.wires("shop.buy") == [{"t": "shop.buy", "kind": "ball", "id": 2, "qty": 1_000}]


async def test_rank_fallback_gold_xp_drop():
    h = await Harness(focus="rank").start()
    await h.send_ev(ev("rank.mode", mode="fallback", reason="queue_empty"))
    (a,) = h.wires("auto.set")
    assert a["autoBallSemParar"] is False and a["autoBallAteCapturar"] is False
    await h.kills(60, gold=500)
    assert h.wires("shop.buy") == []


async def test_rank_fallback_capture_then_back_to_active():
    h = await Harness(focus="rank", fallback_focus="capture").start()
    await h.send_ev(ev("rank.mode", mode="fallback", reason="queue_empty"))
    await h.kills(50, gold=200)
    (a,) = h.wires("auto.set")
    assert a["autoBallSemParar"] is True and a["ballIds"][0] == 4
    assert h.wires("shop.buy")[0]["id"] == 4
    await h.send_ev(ev("rank.mode", mode="active", ball_id=2))
    h.state.automation = {**AUTOMATION, "autoBallAteCapturar": True, "autoBallSemParar": False}
    h.now += 120
    await h.kills(60, gold=200)
    assert len(h.wires("auto.set")) == 1


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
