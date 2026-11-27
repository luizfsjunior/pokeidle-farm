"""Bosses lendários (épico C4): escolha do boss, penalidade da equipe e o plugin boss."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from pokeidle_farm.actions import ActionGateway, ActionMode, BossAuto, BossEnter, RateLimiter
from pokeidle_farm.boss_model import bosses, choose, penalty, prize_of, rotation_day
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.boss import BossConfig, BossPlugin
from pokeidle_farm.store.memory import MemoryStore


def _boss(key: str, region: str, step: int, pos: int, level: int) -> dict[str, Any]:
    # o formato do `bossesJogaveis` do welcome (visto em 12/11)
    return {
        "key": key,
        "nome": key.title(),
        "regiao": region,
        "degrau": step,
        "posicao": pos,
        "premio": ["tm", "mega", "tickets"][pos],
        "level": level,
        "teamLevel": level,
        "equipeIdeal": 5,
        "minNivelTreinador": level,
        "entrada": {"qtd": 1, "nome": "Bronze Boss Token", "itemId": 70000},
    }


RULES = {
    "bossesJogaveis": [
        _boss("articuno", "kanto", 0, 0, 300),
        _boss("moltres", "kanto", 0, 1, 300),
        _boss("zapdos", "kanto", 0, 2, 300),
        _boss("suicune", "johto", 1, 0, 650),
        _boss("entei", "johto", 1, 1, 650),
        _boss("raikou", "johto", 1, 2, 650),
    ]
}
# 27/11 12:00 UTC: dia sazonal 27/11 → 10 dias depois de 17/11 → dia 1 da rotação
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)
FULL = [300, 310, 305, 400, 300]


# --- modelo ------------------------------------------------------------------


def test_catalog_parses_the_welcome():
    bs = bosses(RULES)
    assert [b.key for b in bs][:3] == ["articuno", "moltres", "zapdos"]
    assert bs[0].entry_item == 70000 and bs[0].team_level == 300 and bs[0].ideal == 5
    assert bosses({}) == [] and bosses(None) == []


def test_rotation_matches_the_game():
    assert rotation_day(datetime(2026, 11, 17, 12, tzinfo=UTC)) == 0
    assert rotation_day(datetime(2026, 11, 17, 21, 30, tzinfo=UTC)) == 1  # virou às 18:00 BRT
    assert rotation_day(NOW) == 1
    assert rotation_day(NOW, "2026-11-19") == 2  # a chave do estado vale mais que o relógio
    # posição 1 (Moltres) no dia 1 dá TM; no dia 0 dá Mega (premioDaPosicaoNoDia)
    moltres = bosses(RULES)[1]
    assert prize_of(moltres, 0) == "mega" and prize_of(moltres, 1) == "tm"


def test_penalty_is_the_app_js_formula():
    assert penalty(FULL, 300, 5) == (5.0, 1.0)
    force, mult = penalty([612, 242, 100, 141, 140], 300, 5)  # a equipe da _1 em 27/11
    assert force == pytest.approx(1 + 242 / 300 + 100 / 300 + 141 / 300 + 140 / 300)
    assert mult == pytest.approx(3 ** (5 - force))
    assert penalty([300, 300, 300, 300], 300, 5)[1] == 3.0  # um a menos: ×3


def test_choose_picks_todays_prize_in_the_highest_region_that_works():
    items = {"70000": 4}
    c = choose(RULES, trainer_level=700, team_levels=[700] * 5, items=items, prize="mega", now=NOW)
    assert c.ok and c.boss.key == "raikou"  # Johto; no dia 1 a Mega é a posição 2
    # time no nível de Kanto mas não de Johto: desce para Kanto
    c = choose(RULES, trainer_level=700, team_levels=FULL, items=items, prize="mega", now=NOW)
    assert c.ok and c.boss.key == "zapdos"
    c = choose(
        RULES,
        trainer_level=700,
        team_levels=FULL,
        items=items,
        prize="mega",
        region="johto",
        now=NOW,
    )
    assert c.reason == "equipe_fraca" and c.boss.key == "raikou" and c.mult > 1


def test_choose_explains_why_not():
    kw: dict[str, Any] = {"prize": "tm", "now": NOW}
    assert choose({}, trainer_level=700, team_levels=FULL, items={}, **kw).reason == "sem_catalogo"
    assert choose(RULES, trainer_level=200, team_levels=FULL, items={}, **kw).reason == (
        "nivel_treinador"
    )
    weak = choose(RULES, trainer_level=400, team_levels=[300, 300, 100], items={"70000": 3}, **kw)
    assert weak.reason == "equipe_fraca" and weak.tokens == 3
    assert choose(RULES, trainer_level=400, team_levels=FULL, items={}, **kw).reason == "sem_token"
    loose = choose(
        RULES,
        trainer_level=400,
        team_levels=[300, 300, 300, 300],
        items={"70000": 1},
        max_mult=3,
        **kw,
    )
    assert loose.ok and loose.boss.key == "moltres"  # aceita ×3; TM no dia 1 é a posição 1


def test_actions_wire():
    assert BossEnter(key="moltres").to_wire() == {"t": "boss.entrar", "key": "moltres"}
    assert BossAuto(key="moltres", ativo=True).to_wire() == {
        "t": "boss.auto",
        "ativo": True,
        "key": "moltres",
    }


# --- plugin ------------------------------------------------------------------


class Rig:
    def __init__(self, team: list[int], tokens: int = 3, level: int = 400, **cfg: Any) -> None:
        self.t = 1000.0
        self.sent: list[dict[str, Any]] = []
        self.notes: list[tuple[str, dict[str, Any]]] = []

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.notes.append((t, d))

        self.state = AccountStateView(
            level=level,
            items={"70000": tokens},
            team=[{"id": i + 1, "level": lv, "slot": i} for i, lv in enumerate(team)],
            season={"chave": "2026-11-27"},
        )
        self.plugin = BossPlugin()
        self.plugin.clock = lambda: self.t
        self.plugin.now = lambda: NOW
        self.ctx = PluginContext(
            account_id=uuid4(),
            nick="farm1",
            config=BossConfig.model_validate({"prize": "tm", **cfg}),
            bus=EventBus(),
            actions=ActionGateway(
                "acc",
                ActionMode.ENABLED,
                send=send,
                record=record,
                limiter=RateLimiter(clock=lambda: self.t),
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

    async def event(self, boss: dict[str, Any] | None = None, kind: str = "state.patch") -> None:
        estado = {"boss": boss} if boss is not None else {}
        await self.plugin.on_event(
            Event(
                account_id=uuid4(),
                session_id=uuid4(),
                type=kind,
                data={},
                raw={"t": "estado", "estado": estado},
            )
        )

    def note(self, t: str) -> list[dict[str, Any]]:
        return [d for typ, d in self.notes if typ == t]


async def test_dry_run_only_records_what_it_would_do():
    r = await Rig(FULL).start()
    await r.event({"auto": False, "arena": None, "autoKey": None}, "state.snapshot")
    assert r.sent == []
    assert r.note("boss.plan")[0]["key"] == "moltres" and r.note("boss.plan")[0]["reason"] == "ok"
    assert [w["step"] for w in r.note("boss.would")] == ["boss.auto_set", "boss.entered"]
    r.t += 600
    await r.event()
    assert len(r.note("boss.would")) == 2  # não repete a cada minuto
    assert len(r.note("boss.plan")) == 1  # só grava quando a escolha muda


async def test_live_turns_repeat_on_enters_and_follows_the_state():
    r = await Rig(FULL, dry_run=False).start()
    await r.event({"auto": False, "arena": None, "autoKey": None}, "state.snapshot")
    assert r.sent == [
        {"t": "boss.auto", "ativo": True, "key": "moltres"},
        {"t": "boss.entrar", "key": "moltres"},
    ]
    r.t += 61
    await r.event({"auto": True, "autoKey": "moltres", "arena": {"key": "moltres"}})
    assert len(r.sent) == 2  # já repetindo e na arena
    # a equipe enfraqueceu (um caiu de nível na troca): desliga a repetição que ligou
    r.state.team = r.state.team[:4]
    r.t += 61
    await r.event()
    assert r.sent[-1] == {"t": "boss.auto", "ativo": False, "key": "moltres"}
    assert r.note("boss.plan")[-1]["reason"] == "equipe_fraca"


async def test_live_does_not_turn_off_a_repeat_it_did_not_turn_on():
    r = await Rig([300, 300, 100], dry_run=False).start()
    await r.event({"auto": True, "autoKey": "zapdos", "arena": None}, "state.snapshot")
    assert r.sent == []


async def test_waits_for_the_catalog_and_the_level():
    r = Rig(FULL)
    r.ctx.catalog = None
    await r.start()
    await r.event({"auto": False})
    assert r.notes == []
