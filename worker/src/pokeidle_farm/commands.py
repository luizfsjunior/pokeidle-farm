"""Comandos do painel (fase 4b, docs/design/fase-4b-comandos.md).

O `Supervisor` cuida das sessões de todas as contas de farm (inclusive as
desligadas, para poder ligá-las por comando). O `CommandLoop` busca os comandos
pendentes no Supabase a cada `commands_poll_s`, executa um por vez e grava o
resultado. A pegada (`claim_commands`) é atômica no banco: dois workers nunca
executam o mesmo comando.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from .events import Event
from .plugins.base import Plugin
from .store.base import AccountRecord, CommandRecord, Store

log = logging.getLogger(__name__)

MAX_FARM_ACCOUNTS = 3  # Termos, seção 5: 4 por pessoa, uma é a pessoal


class SessionLike(Protocol):
    account: AccountRecord
    state: Any

    async def run(self) -> Any: ...
    def stop(self) -> None: ...
    def reconnect(self) -> None: ...
    async def restart_plugin(self, name: str) -> bool: ...
    @property
    def plugins(self) -> Any: ...


SessionFactory = Callable[[AccountRecord], SessionLike]


class CommandError(Exception):
    """Falha esperada de um comando: vira `failed` com esta mensagem."""


@dataclass
class _Live:
    session: SessionLike
    task: asyncio.Task[Any]


class Supervisor:
    def __init__(
        self,
        store: Store,
        make_session: SessionFactory,
        available_plugins: dict[str, type[Plugin]],
        holder: str,
    ) -> None:
        self.store = store
        self.make_session = make_session
        self.available = available_plugins
        self.holder = holder
        self.accounts: dict[UUID, AccountRecord] = {}
        self.live: dict[UUID, _Live] = {}
        self._stopping = False

    async def load(self) -> None:
        accounts = await self.store.list_accounts(include_disabled=True)
        self.accounts = {a.id: a for a in accounts if a.role == "farm"}
        enabled = [a for a in self.accounts.values() if a.enabled]
        if len(enabled) > MAX_FARM_ACCOUNTS:
            raise CommandError(
                f"{len(enabled)} contas de farm habilitadas; o máximo é {MAX_FARM_ACCOUNTS}"
            )

    def start_enabled(self) -> None:
        for acc in self.accounts.values():
            if acc.enabled:
                self._start(acc)

    def _is_running(self, account_id: UUID) -> bool:
        live = self.live.get(account_id)
        return live is not None and not live.task.done()

    def _start(self, acc: AccountRecord) -> None:
        session = self.make_session(acc)
        task = asyncio.create_task(self._run_session(session), name=f"session:{acc.nick}")
        self.live[acc.id] = _Live(session, task)

    async def _run_session(self, session: SessionLike) -> Any:
        state = await session.run()
        log.info("[%s] sessão terminou em %s", session.account.nick, getattr(state, "name", state))
        return state

    async def _stop(self, account_id: UUID, wait_s: float = 30.0) -> None:
        live = self.live.pop(account_id, None)
        if live is None:
            return
        live.session.stop()
        done, _ = await asyncio.wait({live.task}, timeout=wait_s)
        if not done:
            live.task.cancel()

    async def stop_all(self) -> None:
        self._stopping = True
        await asyncio.gather(*(self._stop(a) for a in list(self.live)))

    # --- handlers -----------------------------------------------------------

    async def execute(self, cmd: CommandRecord) -> dict[str, Any]:
        acc = self.accounts.get(cmd.account_id)
        if acc is None:
            raise CommandError("conta não é de farm ou não é deste worker")
        handler = _HANDLERS.get(cmd.type)
        if handler is None:
            raise CommandError(f"tipo desconhecido: {cmd.type}")
        return await handler(self, acc, cmd.params)

    async def _ping(self, acc: AccountRecord, _p: dict[str, Any]) -> dict[str, Any]:
        live = self.live.get(acc.id)
        running = self._is_running(acc.id)
        state = getattr(live.session.state, "value", None) if live else None
        plugins = live.session.plugins if live else None
        return {
            "holder": self.holder,
            "enabled": acc.enabled,
            "running": running,
            "state": state if running else "stopped",
            "plugins": sorted(plugins.running) if plugins else [],
            "degraded": dict(plugins.degraded) if plugins else {},
        }

    async def _enable(self, acc: AccountRecord, _p: dict[str, Any]) -> dict[str, Any]:
        running = sum(1 for a in self.live if self._is_running(a))
        if not self._is_running(acc.id) and running >= MAX_FARM_ACCOUNTS:
            raise CommandError(f"já há {running} contas rodando; o máximo é {MAX_FARM_ACCOUNTS}")
        if not acc.enabled:
            await self.store.set_account_enabled(acc.id, True)
            acc = self.accounts[acc.id] = replace(acc, enabled=True)
        if self._is_running(acc.id):
            return {"started": False, "detail": "já estava rodando"}
        self._start(acc)
        return {"started": True}

    async def _disable(self, acc: AccountRecord, _p: dict[str, Any]) -> dict[str, Any]:
        if acc.enabled:
            await self.store.set_account_enabled(acc.id, False)
            self.accounts[acc.id] = replace(acc, enabled=False)
        was_running = self._is_running(acc.id)
        await self._stop(acc.id)
        with contextlib.suppress(Exception):
            await self.store.set_status(acc.id, "offline")
        return {"stopped": was_running}

    async def _reconnect(self, acc: AccountRecord, _p: dict[str, Any]) -> dict[str, Any]:
        if not acc.enabled:
            raise CommandError("conta desligada; use account.enable")
        if self._is_running(acc.id):
            self.live[acc.id].session.reconnect()
            return {"mode": "reconnect"}
        # sessão em estado terminal (needs_login, rejected): sobe de novo, ex.: depois de token novo
        self._start(acc)
        return {"mode": "restart"}

    async def _plugin_set(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        try:
            p = PluginSetParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        cls = self.available.get(p.plugin)
        if cls is None:
            raise CommandError(f"plugin desconhecido: {p.plugin}")
        current = (await self.store.plugin_configs(acc.id)).get(p.plugin, (cls.always_on, {}))
        enabled = current[0] if p.enabled is None else p.enabled
        config = current[1] if p.config is None else p.config
        try:
            cls.config_model.model_validate(config)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(x) for x in first["loc"]) or "config"
            raise CommandError(f"config inválida em {where}: {first['msg']}") from exc
        await self.store.set_plugin_config(acc.id, p.plugin, enabled, config)
        applied = False
        if self._is_running(acc.id):
            applied = await self.live[acc.id].session.restart_plugin(p.plugin)
        return {"enabled": enabled, "applied": "agora" if applied else "na próxima conexão"}


class PluginSetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin: str
    enabled: bool | None = None
    config: dict[str, Any] | None = None


Handler = Callable[[Supervisor, AccountRecord, dict[str, Any]], Awaitable[dict[str, Any]]]
_HANDLERS: dict[str, Handler] = {
    "ping": Supervisor._ping,
    "account.enable": Supervisor._enable,
    "account.disable": Supervisor._disable,
    "session.reconnect": Supervisor._reconnect,
    "plugin.set": Supervisor._plugin_set,
}


class CommandLoop:
    """Busca e executa os comandos; um por vez, com limite por conta."""

    def __init__(
        self,
        supervisor: Supervisor,
        store: Store,
        *,
        poll_s: float = 5.0,
        timeout_s: float = 60.0,
        max_per_minute: int = 10,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sup = supervisor
        self.store = store
        self.poll_s = poll_s
        self.timeout_s = timeout_s
        self.max_per_minute = max_per_minute
        self.clock = clock
        self._recent: dict[UUID, deque[float]] = {}
        self._session_id = uuid4()  # agrupa os command.executed deste processo
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        with contextlib.suppress(Exception):
            n = await self.store.recover_commands(self.sup.holder)
            if n:
                log.warning("%d comando(s) interrompido(s) no último encerramento", n)
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception:
                log.exception("comandos: falha ao buscar; tento de novo")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_s)

    async def poll_once(self) -> int:
        ids = list(self.sup.accounts)
        if not ids:
            return 0
        cmds = await self.store.claim_commands(self.sup.holder, ids)
        for cmd in cmds:
            await self._execute(cmd)
        return len(cmds)

    def _rate_limited(self, account_id: UUID) -> bool:
        now = self.clock()
        q = self._recent.setdefault(account_id, deque())
        while q and now - q[0] >= 60.0:
            q.popleft()
        if len(q) >= self.max_per_minute:
            return True
        q.append(now)
        return False

    async def _execute(self, cmd: CommandRecord) -> None:
        start = self.clock()
        status, result, error = "done", None, None
        if self._rate_limited(cmd.account_id):
            status, error = "failed", "rate_limited: mais de 10 comandos por minuto"
        else:
            try:
                result = await asyncio.wait_for(self.sup.execute(cmd), self.timeout_s)
            except CommandError as exc:
                status, error = "failed", str(exc)
            except TimeoutError:
                status, error = "failed", f"timeout ({self.timeout_s:.0f} s)"
            except Exception as exc:  # bug num handler não derruba o loop
                log.exception("comando %s falhou", cmd.type)
                status, error = "failed", f"erro interno: {type(exc).__name__}"
        log.info("comando %s → %s%s", cmd.type, status, f" ({error})" if error else "")
        await self.store.finish_command(cmd.id, status, result, error)
        ev = Event(
            account_id=cmd.account_id,
            session_id=self._session_id,
            type="command.executed",
            data={
                "command_id": str(cmd.id),
                "command": cmd.type,
                "status": status,
                "error": error,
                "duration_ms": int((self.clock() - start) * 1000),
            },
        )
        with contextlib.suppress(Exception):
            await self.store.insert_events([ev.to_row()])


class FakeSession:
    """Sessão sem WebSocket, para `listen --fake`: testa o caminho dos comandos
    (painel → Supabase → worker → painel) sem conectar no jogo."""

    def __init__(self, account: AccountRecord, plugins: Any) -> None:
        from .session import State

        self.account = account
        self._plugins = plugins
        self.state = State.READY
        self._stopping = asyncio.Event()
        self.reconnects = 0

    @property
    def plugins(self) -> Any:
        return self._plugins

    async def run(self) -> Any:
        from .session import State

        self.state = State.READY
        await self._stopping.wait()
        self.state = State.DISCONNECTED
        return self.state

    def stop(self) -> None:
        self._stopping.set()

    def reconnect(self) -> None:
        self.reconnects += 1
        log.info("[%s] (fake) reconexão #%d", self.account.nick, self.reconnects)

    async def restart_plugin(self, name: str) -> bool:
        log.info("[%s] (fake) plugin %s recarregado", self.account.nick, name)
        return True
