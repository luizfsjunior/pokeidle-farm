import asyncio
import json

from websockets.asyncio.server import ServerConnection

from pokeidle_farm.session import State

from .conftest import battle, wait_until, welcome


def types(store) -> list[str]:
    return [e["type"] for e in store.events]


async def keep_open(ws: ServerConnection) -> None:
    async for _ in ws:
        pass


async def test_handshake_ready_and_events_persisted(fake_game, make_session, store, account):
    async def script(ws, hello, n):
        await ws.send('{"t":"campo.init","slug":"x"}')  # antes do welcome: ignorado no handshake
        await ws.send(welcome())
        await ws.send(battle({"k": "ataque", "hpAlvo": 1}, {"k": "morte", "xpTreinador": 5}))
        await ws.send('{"t":"coisa.nova"}')
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: "unknown" in types(store))
    assert session.state is State.READY
    assert store.status[account.id] == "ready"
    assert game.hellos == [
        {
            "t": "hello",
            "nick": "farm1",
            "token": "TOKEN-SECRETO",
            "delta": 1,
            "dispositivo": "dev-123",
        }
    ]
    session.stop()
    await task

    t = types(store)
    assert {"state.snapshot", "session.connected", "kill", "unknown"} <= set(t)
    assert "attack" not in t  # não persistido
    kill = next(e for e in store.events if e["type"] == "kill")
    assert kill["data"]["xp"] == 5 and kill["raw"]["k"] == "morte"
    assert "TOKEN-SECRETO" not in json.dumps(store.events)
    assert account.id not in store.leases  # lease liberado ao parar


async def test_token_renewal_is_saved(fake_game, make_session, store, account):
    async def script(ws, hello, n):
        await ws.send(welcome())
        await ws.send('{"t":"sessao.renovada","token":"TOKEN-NOVO"}')
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: store.tokens[account.id].token == "TOKEN-NOVO")
    assert store.tokens[account.id].device_id == "dev-123"
    await wait_until(lambda: "session.token_renewed" in types(store))
    session.stop()
    await task
    assert "TOKEN-NOVO" not in json.dumps(store.events)


async def test_invalid_session_needs_login_without_retry(fake_game, make_session, store, account):
    async def script(ws, hello, n):
        await ws.send('{"t":"erro","chave":"auth.sessaoInvalida"}')
        await keep_open(ws)

    game = await fake_game(script)
    state = await asyncio.wait_for(make_session(game.url).run(), 3)
    assert state is State.NEEDS_LOGIN
    assert game.connections == 1
    assert store.status[account.id] == "needs_login"
    assert "session.rejected" in types(store)


async def test_close_4001_external_login(fake_game, make_session):
    async def script(ws, hello, n):
        await ws.send(welcome())
        await ws.close(4001, "login externo")

    game = await fake_game(script)
    state = await asyncio.wait_for(make_session(game.url).run(), 3)
    assert state is State.NEEDS_LOGIN and game.connections == 1


async def test_banned_account_is_rejected(fake_game, make_session):
    async def script(ws, hello, n):
        await ws.send('{"t":"erro","chave":"auth.contaBanida","motivoBan":"teste"}')
        await keep_open(ws)

    game = await fake_game(script)
    assert await asyncio.wait_for(make_session(game.url).run(), 3) is State.REJECTED


async def test_reconnects_after_drop(fake_game, make_session, store):
    async def script(ws, hello, n):
        await ws.send(welcome())
        if n == 1:
            await ws.close(1011, "queda")
            return
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: game.connections == 2 and session.state is State.READY)
    session.stop()
    await task
    t = types(store)
    assert t.count("session.connected") == 2 and "session.disconnected" in t


async def test_welcome_timeout_retries(fake_game, make_session):
    async def script(ws, hello, n):
        if n == 1:
            await keep_open(ws)  # nunca manda welcome
            return
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url, welcome_timeout_s=0.2)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    assert game.connections == 2
    session.stop()
    await task


async def test_online_limit_waits_and_retries(fake_game, make_session):
    async def script(ws, hello, n):
        if n == 1:
            await ws.send('{"t":"erro","chave":"login.limiteOnlineIp"}')
            await keep_open(ws)
            return
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    assert game.connections == 2
    session.stop()
    await task


async def test_busy_lease_prevents_connection(fake_game, make_session, store, account):
    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    await store.acquire_lease(account.id, "outra-instancia", 3600)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await asyncio.sleep(0.3)
    assert game.connections == 0 and session.state is State.LEASE_BUSY
    await store.release_lease(account.id, "outra-instancia")
    await wait_until(lambda: session.state is State.READY)
    assert store.leases[account.id][0] == "test-holder"
    session.stop()
    await task


async def test_telemetry_buffers_when_store_fails(fake_game, make_session, store, settings):
    async def script(ws, hello, n):
        await ws.send(welcome())
        await ws.send(battle({"k": "morte", "xpTreinador": 1}))
        await keep_open(ws)

    game = await fake_game(script)
    store.fail_inserts = True
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    await asyncio.sleep(0.2)
    assert store.events == []
    buffers = list(
        (
            settings.telemetry_buffer_path
            and __import__("pathlib").Path(settings.telemetry_buffer_path).parent
        ).glob("buffer.*.jsonl")
    )
    assert buffers, "eventos deveriam estar no buffer local"
    store.fail_inserts = False
    await wait_until(lambda: "kill" in types(store))
    session.stop()
    await task
    ids = [e["id"] for e in store.events]
    assert len(ids) == len(set(ids))  # sem duplicatas
    assert not any(p.exists() for p in buffers)
