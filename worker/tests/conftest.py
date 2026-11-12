"""Fixtures: servidor WebSocket falso que imita o pokeidle.io."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from websockets.asyncio.server import ServerConnection, serve

from pokeidle_farm.config import Settings
from pokeidle_farm.plugins.registry import PluginHost, discover
from pokeidle_farm.session import AccountSession
from pokeidle_farm.store.base import AccountRecord
from pokeidle_farm.store.memory import MemoryStore

Script = Callable[[ServerConnection, dict[str, Any], int], Awaitable[None]]


def welcome(**estado: Any) -> str:
    base = {"nick": "farm1", "level": 12, "huntSlug": "rota-1", "items": {"1": 5}}
    return json.dumps({"t": "welcome", "estado": {**base, **estado}, "hunts": []})


def battle(*evs: dict[str, Any]) -> str:
    return json.dumps({"t": "batalha", "ev": list(evs)})


@dataclass
class FakeGame:
    """Cada conexão roda `script(ws, hello, n_conexao)`."""

    script: Script
    hellos: list[dict[str, Any]] = field(default_factory=list)
    connections: int = 0
    url: str = ""

    async def handler(self, ws: ServerConnection) -> None:
        self.connections += 1
        n = self.connections
        hello = json.loads(await ws.recv())
        self.hellos.append(hello)
        await self.script(ws, hello, n)


@pytest.fixture
async def fake_game():
    servers = []

    async def start(script: Script) -> FakeGame:
        game = FakeGame(script)
        server = await serve(game.handler, "127.0.0.1", 0)
        servers.append(server)
        port = next(iter(server.sockets)).getsockname()[1]
        game.url = f"ws://127.0.0.1:{port}"
        return game

    yield start
    for s in servers:
        s.close()
        await s.wait_closed()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        welcome_timeout_s=1.0,
        reconnect_min_s=0.05,
        reconnect_max_s=0.1,
        online_limit_retry_s=0.05,
        lease_renew_s=0.2,
        lease_busy_retry_s=0.05,
        telemetry_flush_s=0.05,
        telemetry_buffer_path=str(tmp_path / "buffer.jsonl"),
        worker_holder="test-holder",
    )


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def account(store: MemoryStore) -> AccountRecord:
    acc = AccountRecord(id=uuid4(), nick="farm1", role="farm")
    store.add_account(acc, token="TOKEN-SECRETO", device_id="dev-123")
    return acc


@pytest.fixture
def make_session(store, settings, account):
    def make(url: str, **overrides: Any) -> AccountSession:
        s = settings.model_copy(update={"ws_url": url, **overrides})
        return AccountSession(account, store, s, PluginHost(discover()))

    return make


async def wait_until(pred: Callable[[], bool], timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not pred():
            await asyncio.sleep(0.01)
