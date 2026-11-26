"""Avisos no Discord (plugin notifier, épico A): filtros, limite compartilhado, teste e degradado."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr

from pokeidle_farm.actions import ActionGateway, ActionMode
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins import notifier as nt
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.notifier import Dispatcher, Notice, NotifierConfig, NotifierPlugin
from pokeidle_farm.plugins.registry import PluginHost
from pokeidle_farm.store.memory import MemoryStore

from .test_commands import farm, rig  # noqa: F401  (fixture)

HOOK = "https://discord.test/hook"
T0 = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
BULBA = {
    "baseHp": 45,
    "baseAtk": 49,
    "baseDef": 49,
    "baseSpAtk": 65,
    "baseSpDef": 65,
    "baseSpeed": 45,
}


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.t += s


def make_dispatcher(per_minute: int = 10) -> tuple[Dispatcher, list[dict[str, Any]], Clock]:
    clock = Clock()
    posted: list[dict[str, Any]] = []

    async def post(payload: dict[str, Any]) -> None:
        posted.append({"at": clock.t, **payload})

    d = Dispatcher(url=HOOK, per_minute=per_minute, post=post, clock=clock, sleep=clock.sleep)
    return d, posted, clock


def settings(**kw: Any) -> SimpleNamespace:
    base = {
        "discord_webhook_url": SecretStr(HOOK),
        "panel_url": "https://painel.test/",
        "notify_per_minute": 10,
    }
    return SimpleNamespace(**{**base, **kw})


@pytest.fixture(autouse=True)
def _clean():
    nt.reset_state()
    nt.set_dispatcher(None)
    yield
    nt.reset_state()
    nt.set_dispatcher(None)


class World:
    def __init__(self, per_minute: int = 10, account_id=None, **cfg: Any) -> None:
        self.d, self.posted, self.clock = make_dispatcher(per_minute)
        nt.set_dispatcher(self.d)
        species = SimpleNamespace(
            species={1: SimpleNamespace(name="Bulbasaur"), 129: SimpleNamespace(name="Magikarp")},
            raw={1: BULBA},
        )

        async def noop(*_a: Any) -> None:
            pass

        self.ctx = PluginContext(
            account_id=account_id or uuid4(), nick="farm1", config=NotifierConfig(**cfg),
            bus=EventBus(), actions=ActionGateway("farm1", ActionMode.OBSERVE_ONLY, send=noop, record=noop),
            state=AccountStateView(), store=MemoryStore(), log=logging.getLogger("t"),
            settings=settings(notify_per_minute=per_minute), species=species,
        )  # fmt: skip
        self.plugin = NotifierPlugin()
        self.plugin.clock = self.clock
        self.plugin.wall = lambda: T0 + timedelta(seconds=self.clock.t)

        async def never(_s: float) -> None:
            await __import__("asyncio").Event().wait()

        self.plugin.sleep = never  # o timer não anda sozinho; o teste chama check_down

    async def start(self) -> World:
        await self.plugin.start(self.ctx)
        return self

    async def ev(self, type_: str, **data: Any) -> None:
        e = Event(account_id=self.ctx.account_id, session_id=uuid4(), type=type_, data=data)
        await self.plugin.on_event(e)
        await self.d.idle()

    def titles(self) -> list[str]:
        return [p["embeds"][0]["title"] for p in self.posted if "embeds" in p]


async def test_shiny_seen_and_captured_with_sprite_and_link():
    w = await World().start()
    await w.ev("kill", wild_name="Magikarp", shiny=True, hunt_slug="rota-1", slot=3)
    await w.ev("kill", wild_name="Magikarp", shiny=False, hunt_slug="rota-1")
    await w.ev(
        "pokemon.captured", species="Bulbasaur", species_id=1, shiny=True, potency=2,
        quality=1.6, level=5, ivs=dict.fromkeys(("hp", "atk", "def", "spAtk", "spDef", "speed"), 27),
    )  # fmt: skip
    assert w.titles() == ["Shiny visto: Magikarp · farm1", "Shiny capturado: Bulbasaur · farm1"]
    seen, cap = (p["embeds"][0] for p in w.posted)
    assert seen["thumbnail"]["url"].endswith("/shiny/129.png")
    assert seen["url"] == f"https://painel.test/contas/{w.ctx.account_id}"
    fields = {f["name"]: f["value"] for f in cap["fields"]}
    assert fields["Potência"] == "P2" and fields["Nota"] != "?"


async def test_shiny_missed_is_sent_even_without_kill_notice():
    w = await World().start()
    await w.ev("ball_thrower.shiny_missed", wild_name="Magikarp", hunt_slug="rota-1", slot=1)
    assert w.titles() == ["Shiny Magikarp sem bola · farm1"]


async def test_rare_capture_by_potency_or_species_top_pct_and_switch_off():
    w = await World(min_potency=4, top_pct=5).start()
    ivs = lambda v: dict.fromkeys(("hp", "atk", "def", "spAtk", "spDef", "speed"), v)  # noqa: E731
    cap = lambda p, q, iv: w.ev(  # noqa: E731
        "pokemon.captured", species="Bulbasaur", species_id=1, potency=p, quality=q, ivs=ivs(iv)
    )
    cut = nt.grade_cut(
        1, {"hp": 45, "atk": 49, "def": 49, "spAtk": 65, "spDef": 65, "speed": 45}, 5
    )
    assert 1.3 < cut < 1.9  # o top 5% do Bulbasaur (nota do jogo; um comum tira ~0,6)
    await cap(1, 1.0, 10)  # comum
    await cap(4, 0.9, 5)  # P4: rara pela potência, mesmo com nota baixa
    await cap(2, 1.6, 27)  # nota 3,179: top 5% da espécie
    assert w.titles() == ["Captura rara: Bulbasaur · farm1"] * 2
    w.plugin.cfg = NotifierConfig(rare_capture=False)
    await cap(5, 1.8, 32)
    assert len(w.posted) == 2


async def test_rare_drop_by_name_list():
    w = await World(drops=["fragment", "Boss Token"]).start()
    await w.ev(
        "kill", wild_name="Rattata", hunt_slug="outland-1",
        drops=[{"name": "Water Stone", "qty": 1}, {"name": "Bronze Boss Token", "qty": 1},
               {"name": "Shiny Stone Fragment", "qty": 2}],
    )  # fmt: skip
    assert w.titles() == [
        "Drop raro: Bronze Boss Token · farm1",
        "Drop raro: Shiny Stone Fragment · farm1",
    ]


async def test_account_down_after_minutes_once_and_back():
    w = await World(down_after_min=10).start()
    await w.ev("session.disconnected", reason="close 1006", will_retry=True)
    w.clock.t = 5 * 60
    w.plugin.check_down()
    await w.ev("session.disconnected", reason="close 1006", will_retry=True)
    assert w.titles() == []  # ainda dentro dos 10 min
    w.clock.t = 11 * 60
    w.plugin.check_down()
    w.plugin.check_down()
    await w.d.idle()
    assert w.titles() == ["Conta desconectada · farm1"]
    await w.ev("session.connected")
    assert w.titles()[-1] == "Conta de volta · farm1"
    await w.ev("session.connected")
    assert len(w.titles()) == 2


async def test_down_state_survives_a_plugin_restart():
    """A sessão encerrada (needs_login) para o plugin; a sessão nova da conta avisa a volta."""
    acc = uuid4()
    w = await World(account_id=acc).start()
    await w.ev("session.rejected", state="needs_login", reason="tokenInvalido")
    assert w.titles() == ["Conta parada · farm1"]
    await w.plugin.stop()
    w2 = World(account_id=acc)
    w2.d, w2.posted = w.d, w.posted
    nt.set_dispatcher(w.d)
    await w2.start()
    await w2.ev("session.connected")
    assert w2.titles()[-1] == "Conta de volta · farm1"


async def test_no_kills_then_kill_is_back():
    w = await World().start()
    await w.ev("watchdog.no_kills", minutes=10, hunt_slug="rota-1")
    await w.ev("watchdog.no_kills", minutes=20, hunt_slug="rota-1")
    await w.ev("session.connected")  # conectada mas sem abater: ainda caída
    await w.ev("kill", wild_name="Rattata")
    assert w.titles() == ["Conta sem abates · farm1", "Conta de volta · farm1"]


async def test_rank_band_changes_only():
    w = await World(rank_marks=[1, 3, 10, 100]).start()

    def pos(p, inside=True):
        return dict(position=p, inside=inside, species=40, missing=0 if inside else 3)

    await w.ev("rank.position", **pos(12))  # primeira vista: só marca
    await w.ev("rank.position", **pos(11))  # mesma faixa (top 100)
    await w.ev("rank.position", **pos(9))
    await w.ev("rank.position", **pos(None, inside=False))
    assert w.titles() == [
        "Top Catch: entrou no top 10 · farm1",
        "Top Catch: fora dos premiados · farm1",
    ]
    assert "Próximo marco: top 3" in w.posted[0]["embeds"][0]["description"]


async def test_level_marks_trainer_only():
    w = await World(level_marks=[150, 300]).start()
    await w.ev("level_up", who="treinador", level=149)
    await w.ev("level_up", who="treinador", level=150)
    await w.ev("level_up", who="pokemon", level=300)
    assert w.titles() == ["Nível 150 · farm1"]


async def test_inactive_account_sends_nothing():
    w = await World(active=False).start()
    await w.ev("kill", wild_name="Magikarp", shiny=True)
    await w.ev("level_up", who="treinador", level=300)
    assert w.posted == []


# --- limite compartilhado -------------------------------------------------------------------------


async def test_shared_limit_and_summary():
    d, posted, _ = make_dispatcher(per_minute=3)
    for i in range(10):  # 4 contas mandando junto: a fila guarda um minuto, o resto vira resumo
        d.submit(Notice("shiny_seen" if i % 2 else "rare_drop", {"content": str(i)}))
    await d.idle()
    times = [p["at"] for p in posted]
    contents = [p["content"] for p in posted]
    assert contents[:3] == ["0", "1", "2"] and times[:3] == [0, 0, 0]
    assert contents[3].startswith("+7 aviso(s)") and times[3] >= 60
    # nunca mais que 3 por janela de 60 s
    for i, t in enumerate(times):
        assert sum(1 for u in times if t <= u < t + 60) <= 3, (i, times)


async def test_two_plugins_share_one_dispatcher():
    s = settings(notify_per_minute=7)
    a, b = nt.get_dispatcher(s), nt.get_dispatcher(s)
    assert a is b and a.per_minute == 7
    assert nt.get_dispatcher(settings(discord_webhook_url=None)) is None


async def test_post_error_does_not_stop_the_queue():
    d, posted, _ = make_dispatcher()
    calls = 0

    async def flaky(payload: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("rede")
        posted.append(payload)

    d.post = flaky
    d.submit(Notice("rank", {"content": "a"}))
    d.submit(Notice("rank", {"content": "b"}))
    await d.idle()
    assert [p["content"] for p in posted] == ["b"]


# --- sem webhook, comando de teste ----------------------------------------------------------------


async def test_without_webhook_the_plugin_is_degraded_not_the_session():
    host = PluginHost({"notifier": NotifierPlugin})
    bus = EventBus()

    def make_ctx(cls, cfg):
        return SimpleNamespace(
            nick="farm1",
            account_id=uuid4(),
            config=cfg,
            settings=settings(discord_webhook_url=None),
        )

    await host.start_all(bus, {}, make_ctx)
    assert "notifier" not in host.running and "DISCORD_WEBHOOK_URL" in host.degraded["notifier"]
    await bus.close()


async def test_notify_test_command(rig):  # noqa: F811
    acc = farm(rig.store, "farm1", enabled=False)
    await rig.boot()
    c = await rig.cmd(acc, "notify.test")
    assert c["status"] == "failed" and "DISCORD_WEBHOOK_URL" in c["error"]

    d, posted, _ = make_dispatcher()
    nt.set_dispatcher(d)
    rig.sup.settings = settings()
    c = await rig.cmd(acc, "notify.test")  # sai mesmo com a conta desligada
    assert c["status"] == "done" and c["result"] == {"sent": True}
    (p,) = posted
    assert p["embeds"][0]["title"] == "Aviso de teste"
    assert p["embeds"][0]["url"] == f"https://painel.test/contas/{acc.id}"
