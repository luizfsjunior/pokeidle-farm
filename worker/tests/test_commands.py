"""Fase 4b: comandos do painel (docs/design/fase-4b-comandos.md)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from pokeidle_farm.commands import CommandLoop, FakeSession, Supervisor
from pokeidle_farm.plugins.registry import PluginHost, discover
from pokeidle_farm.session import State
from pokeidle_farm.store.base import AccountRecord
from pokeidle_farm.store.memory import MemoryStore

from .conftest import wait_until, welcome


def farm(store: MemoryStore, nick: str, enabled: bool = True) -> AccountRecord:
    acc = AccountRecord(id=uuid4(), nick=nick, role="farm", enabled=enabled)
    store.add_account(acc, token="T", device_id="d")
    return acc


class Rig:
    def __init__(self) -> None:
        self.store = MemoryStore()
        self.available = discover()
        self.sessions: list[FakeSession] = []
        self.now = 0.0

        def make(acc: AccountRecord) -> FakeSession:
            s = FakeSession(acc, PluginHost(self.available))
            self.sessions.append(s)
            return s

        self.sup = Supervisor(self.store, make, self.available, holder="pc-casa")
        self.loop = CommandLoop(self.sup, self.store, clock=lambda: self.now)

    async def boot(self) -> Rig:
        await self.sup.load()
        self.sup.start_enabled()
        await asyncio.sleep(0)
        return self

    async def cmd(self, acc: AccountRecord, type_: str, **params: Any) -> dict[str, Any]:
        cid = self.store.add_command(acc.id, type_, params)
        await self.loop.poll_once()
        return self.store.commands[cid]

    async def close(self) -> None:
        await self.sup.stop_all()


@pytest.fixture
async def rig():
    r = Rig()
    yield r
    await r.close()


async def test_ping_reports_state(rig):
    acc = farm(rig.store, "farm1")
    await rig.boot()
    c = await rig.cmd(acc, "ping")
    assert c["status"] == "done"
    assert c["result"]["state"] == "ready" and c["result"]["running"] is True
    assert c["holder"] == "pc-casa"
    (ev,) = [e for e in rig.store.events if e["type"] == "command.executed"]
    assert ev["data"]["command"] == "ping" and ev["data"]["status"] == "done"


async def test_enable_and_disable(rig):
    acc = farm(rig.store, "farm2", enabled=False)
    await rig.boot()
    assert rig.sessions == []  # desligada não sobe
    c = await rig.cmd(acc, "account.enable")
    assert c["status"] == "done" and c["result"] == {"started": True}
    assert rig.store.accounts[acc.id].enabled is True
    assert len(rig.sessions) == 1

    c = await rig.cmd(acc, "account.disable")
    assert c["result"] == {"stopped": True}
    assert rig.store.accounts[acc.id].enabled is False
    assert rig.store.status[acc.id] == "offline"
    c = await rig.cmd(acc, "ping")
    assert c["result"]["state"] == "stopped"


async def test_enable_respects_four_accounts(rig):
    accs = [farm(rig.store, f"farm{i}") for i in range(4)]
    extra = farm(rig.store, "farm5", enabled=False)
    await rig.boot()
    c = await rig.cmd(extra, "account.enable")
    assert c["status"] == "failed" and "máximo é 4" in c["error"]
    assert rig.store.accounts[extra.id].enabled is False
    c = await rig.cmd(accs[0], "account.enable")
    assert c["result"]["started"] is False  # já rodava


async def test_reconnect_running_and_restart_stopped(rig):
    acc = farm(rig.store, "farm1")
    await rig.boot()
    c = await rig.cmd(acc, "session.reconnect")
    assert c["result"] == {"mode": "reconnect"} and rig.sessions[0].reconnects == 1
    rig.sessions[0].stop()  # imita um estado terminal (needs_login)
    await asyncio.sleep(0.01)
    c = await rig.cmd(acc, "session.reconnect")
    assert c["result"] == {"mode": "restart"} and len(rig.sessions) == 2


async def test_reconnect_disabled_fails(rig):
    acc = farm(rig.store, "farm1", enabled=False)
    await rig.boot()
    c = await rig.cmd(acc, "session.reconnect")
    assert c["status"] == "failed" and "desligada" in c["error"]


async def test_plugin_set_validates_and_persists(rig):
    acc = farm(rig.store, "farm1")
    await rig.boot()
    c = await rig.cmd(acc, "plugin.set", plugin="nao-existe", enabled=True)
    assert c["status"] == "failed" and "desconhecido" in c["error"]

    c = await rig.cmd(acc, "plugin.set", plugin="restock", config={"focus": "ouro"})
    assert c["status"] == "failed" and "config inválida em focus" in c["error"]
    assert "restock" not in rig.store.configs.get(acc.id, {})

    c = await rig.cmd(acc, "plugin.set", plugin="restock", enabled=True, config={"ball_min": 50})
    assert c["status"] == "done" and c["result"] == {"enabled": True, "applied": "agora"}
    assert rig.store.configs[acc.id]["restock"] == (True, {"ball_min": 50})

    # parcial: só desliga, mantém a config
    c = await rig.cmd(acc, "plugin.set", plugin="restock", enabled=False)
    assert rig.store.configs[acc.id]["restock"] == (False, {"ball_min": 50})

    c = await rig.cmd(acc, "plugin.set", plugin="restock", extra=1)
    assert c["status"] == "failed" and "params inválidos" in c["error"]


async def test_unknown_account_and_type(rig):
    acc = farm(rig.store, "farm1")
    await rig.boot()
    c = await rig.cmd(acc, "rm -rf")
    assert c["status"] == "failed" and "desconhecido" in c["error"]


async def test_rate_limit_per_account(rig):
    acc = farm(rig.store, "farm1")
    await rig.boot()
    for _ in range(10):
        assert (await rig.cmd(acc, "ping"))["status"] == "done"
    c = await rig.cmd(acc, "ping")
    assert c["status"] == "failed" and c["error"].startswith("rate_limited")
    rig.now = 61.0
    assert (await rig.cmd(acc, "ping"))["status"] == "done"


async def test_handler_crash_becomes_failed(rig, monkeypatch):
    acc = farm(rig.store, "farm1")
    await rig.boot()

    async def boom(*_a: Any) -> dict[str, Any]:
        raise RuntimeError("bug")

    monkeypatch.setattr(rig.sup, "execute", boom)
    c = await rig.cmd(acc, "ping")
    assert c["status"] == "failed" and c["error"] == "erro interno: RuntimeError"


async def test_timeout(rig, monkeypatch):
    acc = farm(rig.store, "farm1")
    await rig.boot()
    rig.loop.timeout_s = 0.05

    async def slow(*_a: Any) -> dict[str, Any]:
        await asyncio.sleep(1)
        return {}

    monkeypatch.setattr(rig.sup, "execute", slow)
    c = await rig.cmd(acc, "ping")
    assert c["status"] == "failed" and c["error"].startswith("timeout")


async def test_recover_marks_orphans_failed(rig):
    acc = farm(rig.store, "farm1")
    await rig.boot()
    cid = rig.store.add_command(acc.id, "ping")
    rig.store.commands[cid].update(status="running", holder="pc-casa")
    rig.loop.stop()
    await rig.loop.run()  # recover e sai
    assert rig.store.commands[cid]["status"] == "failed"
    assert "interrompido" in rig.store.commands[cid]["error"]


async def test_session_reconnect_reconnects_quickly(fake_game, make_session):
    async def script(ws, hello, n):
        await ws.send(welcome())
        async for _ in ws:
            pass

    game = await fake_game(script)
    session = make_session(game.url, reconnect_min_s=30.0)  # backoff alto: tem que pular
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    session.reconnect()
    await wait_until(lambda: game.connections == 2 and session.state is State.READY, timeout=4)
    session.stop()
    await task


# --- focus.set (docs/design/fase-3b-rank-ligado.md, casos 43 a 45) ----------------------


async def test_focus_set_rank_writes_both_plugins(rig):
    acc = farm(rig.store, "farm1")
    items = [{"id": 200, "min": 50, "target": 100}]
    rig.store.configs[acc.id] = {
        "restock": (True, {"items": items, "focus": "capture"}),
        "rank": (True, {"queue_preview": 5}),
    }
    await rig.boot()
    c = await rig.cmd(
        acc,
        "focus.set",
        focus="rank",
        rank={"rank_balls": [2, 1], "fallback_focus": "capture", "fallback_hunt": "magikarp"},
    )
    assert c["status"] == "done", c["error"]
    assert c["result"] == {"focus": "rank", "applied": "agora"}
    assert rig.store.configs[acc.id]["restock"] == (
        True,
        {"items": items, "focus": "rank", "fallback_focus": "capture"},
    )
    assert rig.store.configs[acc.id]["rank"] == (
        True,
        {"queue_preview": 5, "rank_balls": [2, 1], "fallback_hunt": "magikarp", "dry_run": False},
    )


async def test_focus_set_other_focus_turns_rank_off(rig):
    acc = farm(rig.store, "farm1")
    acc2 = farm(rig.store, "farm2")
    rig.store.configs[acc.id] = {
        "restock": (True, {"focus": "rank", "fallback_focus": "capture"}),
        "rank": (True, {"dry_run": False, "rank_balls": [2]}),
    }
    await rig.boot()
    c = await rig.cmd(acc, "focus.set", focus="gold_xp_drop")
    assert c["status"] == "done", c["error"]
    assert rig.store.configs[acc.id]["restock"] == (
        True,
        {"focus": "gold_xp_drop", "fallback_focus": "capture"},
    )
    assert rig.store.configs[acc.id]["rank"] == (False, {"dry_run": False, "rank_balls": [2]})

    # sem rank configurado: não cria a linha
    c = await rig.cmd(acc2, "focus.set", focus="capture")
    assert c["status"] == "done", c["error"]
    assert rig.store.configs[acc2.id] == {"restock": (True, {"focus": "capture"})}


@pytest.mark.parametrize(
    "params",
    [
        {"focus": "xyz"},
        {"focus": "rank", "rank": {"rank_balls": []}},
        {"focus": "rank", "rank": {"foo": 1}},
    ],
)
async def test_focus_set_invalid_writes_nothing(rig, params):
    acc = farm(rig.store, "farm1")
    rig.store.configs[acc.id] = {"restock": (True, {"focus": "capture"})}
    await rig.boot()
    c = await rig.cmd(acc, "focus.set", **params)
    assert c["status"] == "failed"
    assert rig.store.configs[acc.id] == {"restock": (True, {"focus": "capture"})}


async def test_focus_set_gems(rig):
    acc = farm(rig.store, "farm1")
    rig.store.configs[acc.id] = {
        "restock": (True, {"focus": "rank", "items": []}),
        "rank": (True, {"dry_run": False}),
    }
    await rig.boot()
    c = await rig.cmd(acc, "focus.set", focus="gems", gems={"max_market_share": 0.2})
    assert c["status"] == "done", c["error"]
    cfg = rig.store.configs[acc.id]
    assert cfg["restock"] == (True, {"focus": "gold_xp_drop", "items": []})
    assert cfg["rank"] == (False, {"dry_run": False})
    assert cfg["gems"] == (
        True,
        {"max_market_share": 0.2, "dry_run": False, "objective": "gems"},
    )
    c = await rig.cmd(acc, "focus.set", focus="xp")
    assert c["status"] == "done", c["error"]
    assert rig.store.configs[acc.id]["gems"][1]["objective"] == "xp"
    assert rig.store.configs[acc.id]["restock"][1]["focus"] == "gold_xp_drop"
    assert rig.store.configs[acc.id]["restock"][1]["potions_uncapped"] is True  # foco XP
    c = await rig.cmd(acc, "focus.set", focus="capture")
    assert rig.store.configs[acc.id]["gems"][0] is False
    assert "potions_uncapped" not in rig.store.configs[acc.id]["restock"][1]
