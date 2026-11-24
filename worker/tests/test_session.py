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
    assert {"state.snapshot", "session.connected", "unknown"} <= set(t)
    assert "attack" not in t  # não persistido
    assert "kill" not in t  # o abate vai somado por minuto para kill_minute
    [minute] = store.kill_minutes
    assert minute["kills"] == 1 and minute["xp"] == 5
    assert minute["account_id"] == str(account.id)
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


async def test_online_limit_backoff_grows(fake_game, make_session):
    """limiteOnlineIp: a espera dobra a cada recusa e para no teto."""

    async def script(ws, hello, n):
        await ws.send('{"t":"erro","chave":"login.limiteOnlineIp"}')
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url, online_limit_retry_s=10.0, online_limit_retry_max_s=25.0)
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) >= 4:
            session.stop()

    session._sleep = fake_sleep  # type: ignore[method-assign]
    await session.run()
    assert 8 <= delays[0] <= 12
    assert 16 <= delays[1] <= 24
    assert all(20 <= d <= 30 for d in delays[2:])  # teto de 25 s com ±20%


async def test_server_restart_waits_before_reconnecting(fake_game, make_session):
    """Close 1012: espera o servidor subir em vez de voltar no backoff curto."""

    async def script(ws, hello, n):
        await ws.send(welcome())
        if n == 1:
            await ws.close(1012, "reinício")
            return
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url, server_restart_delay_s=100.0)
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        session.stop()

    session._sleep = fake_sleep  # type: ignore[method-assign]
    await session.run()
    assert len(delays) == 1 and 80 <= delays[0] <= 120


async def test_welcome_timeout_backoff_starts_high(fake_game, make_session):
    """Timeout esperando welcome: a espera começa no mínimo próprio e dobra."""

    async def script(ws, hello, n):
        await keep_open(ws)  # nunca manda o welcome

    game = await fake_game(script)
    session = make_session(
        game.url,
        welcome_timeout_s=0.05,
        welcome_retry_min_s=30.0,
        reconnect_min_s=1.0,
        reconnect_max_s=300.0,
    )
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) >= 2:
            session.stop()

    session._sleep = fake_sleep  # type: ignore[method-assign]
    await session.run()
    assert 24 <= delays[0] <= 36
    assert 48 <= delays[1] <= 72


async def test_online_limit_records_full_refusal_and_exit_ip(
    fake_game, make_session, store, monkeypatch
):
    """A recusa vai inteira para o evento (campos extras incluídos), com o IP de saída."""
    from pokeidle_farm import session as session_mod
    from pokeidle_farm.netcheck import parse

    async def fake_fetch(proxy, wait_s=15.0):
        return parse({"ip": "186.198.144.200", "company": {"name": "GTI BRASIL"}})

    monkeypatch.setattr(session_mod, "fetch_exit_ip", fake_fetch)

    async def script(ws, hello, n):
        if n == 1:
            await ws.send(
                '{"t":"erro","chave":"login.limiteOnlineIpLista","lista":["a","b"],"max":4}'
            )
            await keep_open(ws)
            return
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url, exit_ip_check=True)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    await wait_until(lambda: "session.connected" in types(store))
    session.stop()
    await task
    refused = next(e for e in store.events if e["type"] == "session.disconnected")
    data = refused["data"]
    assert data["reason"] == "login.limiteOnlineIpLista"
    assert data["erro"]["lista"] == ["a", "b"] and data["erro"]["max"] == 4
    assert data["exit_ip"] == "186.198.144.200 (GTI BRASIL)"
    connected = next(e for e in store.events if e["type"] == "session.connected")
    assert connected["data"]["exit_ip"] == "186.198.144.200 (GTI BRASIL)"


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


async def test_busy_lease_keeps_status_of_the_holder(fake_game, make_session, store, account):
    """Sem o lease, a sessão não mexe no status: quem grava é o worker que segura a conta.

    Em 17/11 um worker antigo (PC de casa) subiu junto com o do VPS e, a cada minuto, gravava
    `offline` por cima do `ready` do outro.
    """

    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    await store.acquire_lease(account.id, "outra-instancia", 3600)
    await store.set_status(account.id, "ready")
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.LEASE_BUSY)
    assert store.status[account.id] == "ready"
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
    await wait_until(lambda: "session.connected" in types(store))
    session.stop()
    await task
    ids = [e["id"] for e in store.events]
    assert len(ids) == len(set(ids))  # sem duplicatas
    assert [m["kills"] for m in store.kill_minutes] == [1]  # o abate saiu do buffer uma vez só
    assert not any(p.exists() for p in buffers)


async def test_welcome_catalog_is_saved_and_exposed(fake_game, make_session, store):
    hunt = {
        "area": "kanto",
        "nome": "Caterpie",
        "slug": "caterpie",
        "nivel": 1,
        "especies": [{"nome": "Caterpie", "pokeId": 10, "pontos": 15}],
        "totalSpawns": 15,
    }

    async def script(ws, hello, n):
        frame = json.loads(welcome())
        frame["hunts"] = [hunt]
        frame["captura"] = {"base": 0.0075, "piso": 0.003, "teto": 0.1, "porDegrau": {"20": 2.8}}
        await ws.send(json.dumps(frame))
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: "caterpie" in store.game_hunts)
    assert session.catalog is not None and session.catalog.hunts["caterpie"].species_id == 10
    ctx = session._make_ctx(type("P", (), {"name": "x"}), None)
    assert ctx.catalog is session.catalog and ctx.species is None
    session.stop()
    await task


async def test_welcome_without_hunts_saves_nothing(fake_game, make_session, store):
    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    await asyncio.sleep(0.05)
    assert store.game_catalog == {}
    session.stop()
    await task


# --- AccountStateView: trava e relógio do servidor (fase-3b-rank-ligado.md, caso 46) ---


def test_state_view_locks_and_server_clock():
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from pokeidle_farm.events import Event
    from pokeidle_farm.plugins.base import AccountStateView

    def event(type_: str, **data: object) -> Event:
        return Event(account_id=uuid4(), session_id=uuid4(), type=type_, data=data)

    view = AccountStateView()
    lock = datetime(2026, 11, 15, 15, 0, 3, tzinfo=UTC)
    view.apply(event("state.patch", centro_livre_em=int(lock.timestamp() * 1000)))
    assert view.combat_free_at == lock
    view.apply(event("state.patch", gold=10))  # patch sem a trava não apaga a anterior
    assert view.combat_free_at == lock

    free = datetime(2026, 11, 15, 15, 0, 10, tzinfo=UTC)
    view.apply(event("hunt.changed", slug="caterpie", switch_free_at=free.isoformat()))
    assert view.switch_free_at == free
    assert view.hunt_slug is None  # a hunt atual vem do tradutor, não daqui

    now = datetime(2026, 11, 15, 15, 0, 0, tzinfo=UTC)
    assert view.server_now(now) == now
    view.server_offset = timedelta(seconds=5)
    assert view.server_now(now) == now + timedelta(seconds=5)


async def test_running_plugins_get_species_on_welcome(fake_game, make_session, store):
    """Os plugins sempre ligados sobem antes da Pokedex; o welcome entrega a Pokedex a eles."""
    hunt = {
        "area": "kanto",
        "nome": "Caterpie",
        "slug": "caterpie",
        "nivel": 1,
        "especies": [{"nome": "Caterpie", "pokeId": 10, "pontos": 15}],
        "totalSpawns": 15,
    }
    go = asyncio.Event()

    async def script(ws, hello, n):
        await go.wait()
        frame = json.loads(welcome())
        frame["hunts"] = [hunt]
        await ws.send(json.dumps(frame))
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: "market_prices" in session.plugins.running)
    assert session.plugins.running["market_prices"].ctx.species is None
    pokedex = object()
    session._species = lambda: pokedex
    go.set()
    await wait_until(lambda: session.catalog is not None)
    assert session.plugins.running["market_prices"].ctx.species is pokedex
    session.stop()
    await task


def test_state_view_tracks_active_level_from_kills():
    from uuid import uuid4

    from pokeidle_farm.events import Event
    from pokeidle_farm.plugins.base import AccountStateView

    view = AccountStateView()
    view.apply(
        Event(account_id=uuid4(), session_id=uuid4(), type="kill", data={"active_level": 23})
    )
    assert view.active_level == 23
    view.apply(
        Event(account_id=uuid4(), session_id=uuid4(), type="kill", data={"active_level": None})
    )
    assert view.active_level == 23


async def test_species_ready_after_welcome_reaches_plugins(fake_game, make_session, store):
    """A Pokedex que termina de carregar depois do welcome chega aos plugins no evento seguinte."""
    go = asyncio.Event()

    async def script(ws, hello, n):
        await ws.send(welcome())
        await go.wait()
        await ws.send(battle({"k": "morte"}))
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: "market_prices" in session.plugins.running)
    await wait_until(lambda: session.state == State.READY)
    assert session.plugins.running["market_prices"].ctx.species is None
    pokedex = object()
    session._species = lambda: pokedex
    go.set()
    await wait_until(lambda: session.plugins.running["market_prices"].ctx.species is pokedex)
    session.stop()
    await task


# --- a sessão não morre por erro do banco (21/11: conta 2 parada por 13 h) ----------------


def _failing(fn, fail_on):
    """Envolve um método do store para lançar erro nas chamadas de número `fail_on` (1, 2...)."""
    calls = {"n": 0}

    async def wrapped(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] in fail_on:
            raise RuntimeError("ConnectionTerminated")
        return await fn(*args, **kwargs)

    return wrapped, calls


async def test_lease_renewal_error_does_not_kill_renewal(fake_game, make_session, store):
    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    store.acquire_lease, calls = _failing(store.acquire_lease, {2})  # a 1ª renovação falha
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: calls["n"] >= 4)  # continuou renovando depois da falha
    assert session.state is State.READY and game.connections == 1
    session.stop()
    await task


async def test_dead_lease_task_and_drop_still_reconnect(fake_game, make_session, store):
    """A renovação falha e a conexão cai: a sessão reconecta em vez de terminar."""

    async def script(ws, hello, n):
        await ws.send(welcome())
        if n == 1:
            await asyncio.sleep(0.5)  # dá tempo de a renovação (0,2 s) falhar
            await ws.close(1012, "reinício")
            return
        await keep_open(ws)

    game = await fake_game(script)
    store.acquire_lease, _ = _failing(store.acquire_lease, {2, 3, 4})
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: game.connections == 2 and session.state is State.READY)
    assert not task.done()
    session.stop()
    await task


async def test_unexpected_error_on_connect_retries(fake_game, make_session, store):
    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    store.get_token, _ = _failing(store.get_token, {1})
    session = make_session(game.url)
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    assert not task.done() and "session.disconnected" in types(store)
    session.stop()
    await task


# --- IP de saída conferido antes de cada conexão (ADR 0015) -------------------------------


def _exit_ip_answers(monkeypatch, *answers):
    """Troca a consulta do IP de saída por respostas em fila (ExitIp ou exceção)."""
    from pokeidle_farm import session as session_mod

    queue = list(answers)

    async def fake_fetch(proxy, wait_s=15.0):
        got = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(got, Exception):
            raise got
        return got

    monkeypatch.setattr(session_mod, "fetch_exit_ip", fake_fetch)


async def test_datacenter_exit_never_reaches_the_game(fake_game, make_session, store, monkeypatch):
    """Tailscale fora / exit node removido: o IP do VPS aparece e a conta não conecta."""
    from pokeidle_farm.netcheck import parse

    _exit_ip_answers(
        monkeypatch,
        parse({"ip": "165.22.1.2", "is_datacenter": True, "company": {"name": "DigitalOcean"}}),
    )

    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url, exit_ip_check=True)
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) >= 2:
            session.stop()

    session._sleep = fake_sleep  # type: ignore[method-assign]
    await asyncio.wait_for(session.run(), 3)
    assert game.connections == 0  # o jogo não viu o IP
    assert len(delays) == 2 and delays[1] > delays[0]  # backoff, sem martelar
    refused = [e for e in store.events if e["type"] == "session.disconnected"]
    assert refused[0]["data"]["reason"] == "IP de saída de datacenter; não conectei"
    assert refused[0]["data"]["exit_ip"] == "165.22.1.2 (DigitalOcean)"
    assert "session.connected" not in types(store)


async def test_unconfirmed_exit_waits_then_connects(fake_game, make_session, store, monkeypatch):
    """Os dois serviços fora: não conecta no escuro; quando confirmar, conecta."""
    from pokeidle_farm.netcheck import ExitIpUnknown, parse

    _exit_ip_answers(
        monkeypatch,
        ExitIpUnknown("ipapi.is: timeout; ip-api.com: timeout"),
        parse({"ip": "179.84.141.61", "company": {"name": "TELEFÔNICA BRASIL S.A."}}),
    )

    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url, exit_ip_check=True)
    connections_while_waiting: list[int] = []

    async def fake_sleep(seconds: float) -> None:
        connections_while_waiting.append(game.connections)

    session._sleep = fake_sleep  # type: ignore[method-assign]
    task = asyncio.create_task(session.run())
    await wait_until(lambda: session.state is State.READY)
    session.stop()
    await task
    assert connections_while_waiting == [0]  # durante a dúvida, nenhuma conexão
    assert game.connections == 1
    refused = next(e for e in store.events if e["type"] == "session.disconnected")
    assert refused["data"]["reason"] == "IP de saída não confirmado; não conectei"
    assert refused["data"]["exit_ip"] is None
    connected = next(e for e in store.events if e["type"] == "session.connected")
    assert connected["data"]["exit_ip"] == "179.84.141.61 (TELEFÔNICA BRASIL S.A.)"


async def test_exit_check_off_connects_without_asking(fake_game, make_session, store, monkeypatch):
    _exit_ip_answers(monkeypatch, AssertionError("não deveria consultar"))

    async def script(ws, hello, n):
        await ws.send(welcome())
        await keep_open(ws)

    game = await fake_game(script)
    session = make_session(game.url)  # conftest: exit_ip_check=False
    task = asyncio.create_task(session.run())
    await wait_until(lambda: "session.connected" in types(store))
    session.stop()
    await task
    connected = next(e for e in store.events if e["type"] == "session.connected")
    assert connected["data"]["exit_ip"] is None
