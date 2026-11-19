"""AccountSession: uma conexão WebSocket por conta.

Estados (docs/design/fase-2.md, seção 3):

    DISCONNECTED → CONNECTING → HANDSHAKING → READY
                                      ↘ NEEDS_LOGIN | REJECTED  (terminais)

O token é tratado como segredo: nunca é logado nem vai para eventos.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from .actions import ActionGateway, ActionMode
from .bus import EventBus
from .config import Settings
from .events import Translator
from .gamedata import (
    HuntCatalog,
    SpeciesCatalog,
    item_rows_from_welcome,
    save_hunt_catalog,
    save_items,
)
from .plugins.base import AccountStateView, PluginContext
from .plugins.registry import PluginHost
from .protocol import codec
from .protocol.messages import (
    CLOSE_EXTERNAL_LOGIN,
    CLOSE_REJECTED,
    NEEDS_LOGIN_KEYS,
    NEEDS_NICK_KEYS,
    ONLINE_LIMIT_KEYS,
    REJECTED_KEYS,
    GameError,
    Hello,
    SessionRenewed,
    Welcome,
)
from .store.base import AccountRecord, Store

log = logging.getLogger(__name__)


class State(StrEnum):
    DISCONNECTED = "disconnected"
    LEASE_BUSY = "lease_busy"
    CONNECTING = "connecting"
    HANDSHAKING = "handshaking"
    READY = "ready"
    NEEDS_LOGIN = "needs_login"
    REJECTED = "rejected"


# estado da sessão → accounts.status no banco. LEASE_BUSY não grava: a conta é de outro worker, e é ele
# quem diz o status (em 17/11 um worker antigo gravava "offline" por cima do "ready" do VPS a cada minuto)
DB_STATUS: dict[State, str] = {
    State.DISCONNECTED: "offline",
    State.CONNECTING: "connecting",
    State.HANDSHAKING: "connecting",
    State.READY: "ready",
    State.NEEDS_LOGIN: "needs_login",
    State.REJECTED: "rejected",
}


class _Stop(Exception):
    """Encerra a sessão de vez (estado terminal)."""

    def __init__(self, state: State, reason: str) -> None:
        super().__init__(reason)
        self.state = state
        self.reason = reason


# avisos do jogo que não são resposta a uma ação (a próxima onda, praça cheia)
AMBIENT_NOTICES = frozenset({"hunt.ondaEspera", "praca.cheia"})


class _Retry(Exception):
    """Reconectar depois de `delay` segundos (None = backoff padrão)."""

    def __init__(self, reason: str, delay: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.delay = delay


class AccountSession:
    def __init__(
        self,
        account: AccountRecord,
        store: Store,
        settings: Settings,
        plugins: PluginHost,
        species: Callable[[], SpeciesCatalog | None] | None = None,
    ) -> None:
        self.account = account
        self.store = store
        self.settings = settings
        self.plugins = plugins
        self.state = State.DISCONNECTED
        self.state_view = AccountStateView()
        self.bus = EventBus(on_error=plugins.mark_degraded)
        self.gateway = ActionGateway(
            account_id=str(account.id),
            mode=ActionMode(settings.action_mode),
            record=self._record_action,
        )
        self._translator = Translator(account.id, uuid4())
        self._has_lease = False
        self._stopping = asyncio.Event()
        # respostas recentes do jogo a ações (aviso e erro), para confirmar comandos do painel
        self.replies: deque[tuple[float, str]] = deque(maxlen=20)
        self._last_frame = time.monotonic()
        self._silent = False
        self._wake = asyncio.Event()  # acorda o backoff (reconexão pedida)
        self._reconnect_requested = False
        self._online_limit_retries = 0
        self._backoff = settings.reconnect_min_s
        self._ws: ClientConnection | None = None
        self.catalog: HuntCatalog | None = None
        self._species = species or (lambda: None)
        self._bg: set[asyncio.Task[Any]] = set()

    # --- ciclo principal ----------------------------------------------------

    async def run(self) -> State:
        """Roda até um estado terminal ou `stop()`. Retorna o estado final."""
        # Plugins "always_on" (ex.: telemetria) vivem a sessão inteira, para
        # registrar também quedas e rejeições. Os demais sobem no primeiro READY.
        await self.plugins.start_all(self.bus, {}, self._make_ctx, only_always_on=True)
        try:
            while not self._stopping.is_set():
                if not await self._ensure_lease():
                    await self._sleep(self.settings.lease_busy_retry_s)
                    continue
                try:
                    await self._connect_once()
                except _Stop as stop:
                    await self._set_state(stop.state, stop.reason)
                    return stop.state
                except _Retry as retry:
                    await self._disconnected(retry.reason, will_retry=True)
                    delay = retry.delay if retry.delay is not None else self._next_backoff()
                    await self._sleep(delay)
            return self.state
        finally:
            await self.plugins.stop_all()
            await self.bus.close()
            await self._release_lease()

    async def confirm(
        self, check: Callable[[], bool], since: float, within: float = 4.0
    ) -> str | None:
        """Espera o estado mostrar o efeito de uma ação mandada em `since` (time.monotonic).

        None quando confirmou; senão, o motivo: a resposta do jogo (aviso ou erro) ou "sem
        confirmação". Um aviso só derruba se o efeito não aparecer logo depois dele (0,5 s),
        porque o jogo também manda avisos que não têm a ver com a ação.
        """
        deadline = since + within
        reply_at: float | None = None
        while True:
            if check():
                return None
            now = time.monotonic()
            reply = next(((t, m) for t, m in reversed(self.replies) if t >= since), None)
            if reply is not None:
                reply_at = reply_at or now
                if now - reply_at >= 0.5:
                    return reply[1]
            if now >= deadline:
                return reply[1] if reply else "sem confirmação do jogo"
            await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._stopping.set()
        if self._ws is not None:
            asyncio.get_running_loop().create_task(self._ws.close())

    def reconnect(self) -> None:
        """Derruba a conexão e reconecta logo (comando session.reconnect)."""
        self._reconnect_requested = True
        self._wake.set()
        if self._ws is not None:
            asyncio.get_running_loop().create_task(self._ws.close())

    async def restart_plugin(self, name: str) -> bool:
        """Relê a config do plugin e o reinicia. False se a sessão não está pronta
        (aí a config nova vale na próxima conexão)."""
        if self.state != State.READY:
            return False
        log.info("[%s] reiniciando plugin %s", self.account.nick, name)
        configs = await self.store.plugin_configs(self.account.id)
        await self.plugins.restart(name, self.bus, configs, self._make_ctx)
        return True

    def _copy_progress(self) -> None:
        tr, sv = self._translator, self.state_view
        sv.trainer_xp, sv.xp_bonus, sv.xp_event = tr.trainer_xp, tr.xp_bonus, tr.xp_event
        sv.season, sv.battle_pass = tr.season, tr.battle_pass
        self._share_species()

    def _share_species(self) -> None:
        """A Pokedex carrega em segundo plano e pode ficar pronta depois do welcome: entrega aos
        plugins que ainda estão sem ela (senão o gems ficaria em `sem_catalogo` até reconectar)."""
        species = self._species()
        if species is None:
            return
        for plugin in self.plugins.running.values():
            if plugin.ctx.species is None:
                plugin.ctx.species = species

    async def _connect_once(self) -> None:
        token = await self.store.get_token(self.account.id)
        if token is None:
            raise _Stop(State.NEEDS_LOGIN, "sem token cadastrado")

        self._reconnect_requested = False
        await self._set_state(State.CONNECTING)
        self._translator = Translator(self.account.id, uuid4())
        try:
            ws = await connect(
                self.settings.ws_url,
                max_size=None,  # o welcome é grande
                ping_interval=self.settings.ping_interval_s,
                ping_timeout=self.settings.ping_timeout_s,
                open_timeout=self.settings.welcome_timeout_s,
                # Só o proxy do jogo (ADR 0013); None ignora HTTPS_PROXY do ambiente.
                proxy=self.settings.game_proxy,
            )
        except InvalidStatus as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise _Stop(State.NEEDS_LOGIN, f"HTTP {status} no upgrade") from exc
            raise _Retry(f"HTTP {status} no upgrade") from exc
        except (OSError, TimeoutError) as exc:
            raise _Retry(f"falha ao conectar: {exc!r}") from exc

        self._ws = ws
        self._last_frame = time.monotonic()
        self._silent = False
        lease_task = asyncio.create_task(self._renew_lease_loop(ws))
        silence_task = asyncio.create_task(self._silence_watch(ws))
        try:
            await self._handshake(ws, token.token, token.device_id)
            await self._on_ready(ws)
            await self._receive_loop(ws)
            if self._silent:
                raise _Retry(f"conexão muda há {self.settings.silent_after_s:.0f} s", delay=1.0)
            if self._reconnect_requested:
                raise _Retry("reconexão pedida", delay=1.0)
            if not self._stopping.is_set():
                raise _Retry("conexão encerrada pelo servidor")
        except ConnectionClosed as exc:
            if self._silent:
                raise _Retry(
                    f"conexão muda há {self.settings.silent_after_s:.0f} s", delay=1.0
                ) from exc
            if self._reconnect_requested:
                raise _Retry("reconexão pedida", delay=1.0) from exc
            if not self._stopping.is_set():
                self._raise_for_close(exc)
        finally:
            for task in (lease_task, silence_task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self.gateway.send = None
            self._ws = None
            await ws.close()

    async def _handshake(self, ws: ClientConnection, token: str, device_id: str) -> None:
        await self._set_state(State.HANDSHAKING)
        hello = Hello(nick=self.account.nick, token=token, dispositivo=device_id)
        await ws.send(codec.encode(hello))

        deadline = asyncio.get_running_loop().time() + self.settings.welcome_timeout_s
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise _Retry("timeout esperando welcome")
            try:
                frame = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except TimeoutError as exc:
                raise _Retry("timeout esperando welcome") from exc
            msg, raw = codec.decode(frame)
            if isinstance(msg, GameError):
                self._raise_for_error(msg)
                continue
            if isinstance(msg, Welcome):
                self._apply_state(msg)
                self._load_catalog(raw)
                for ev in self._translator.translate(msg, raw):
                    self.state_view.apply(ev)
                    self.state_view.server_offset = self._translator.server_offset
                    self.state_view.active_pokemon = self._translator.active_profile()
                    self.state_view.team = self._translator.team()
                    self._copy_progress()
                    await self.bus.publish(ev)
                return
            # frames antes do welcome são ignorados (comportamento da referência)

    async def _on_ready(self, ws: ClientConnection) -> None:
        self._backoff = self.settings.reconnect_min_s
        self._online_limit_retries = 0

        async def send(payload: dict[str, Any]) -> None:
            await ws.send(codec.encode_raw(payload))

        self.gateway.send = send
        await self._set_state(State.READY)
        offset = self._translator.server_offset
        await self.bus.publish(
            self._translator.system(
                "session.connected",
                {
                    "level": self.state_view.level,
                    "hunt_slug": self.state_view.hunt_slug,
                    "server_offset_ms": int(offset.total_seconds() * 1000) if offset else None,
                    "holder": self.settings.worker_holder,
                },
            )
        )
        configs = await self.store.plugin_configs(self.account.id)
        await self.plugins.start_all(self.bus, configs, self._make_ctx)

    async def _silence_watch(self, ws: ClientConnection) -> None:
        """Fecha a conexão que ficou aberta e muda (o jogo parou de mandar), para reconectar."""
        limit = self.settings.silent_after_s
        while True:
            await asyncio.sleep(min(30.0, limit / 4))
            quiet = time.monotonic() - self._last_frame
            if quiet >= limit:
                log.warning("[%s] conexão muda há %.0f s: reconectando", self.account.nick, quiet)
                self._silent = True
                await ws.close()
                return

    async def _receive_loop(self, ws: ClientConnection) -> None:
        async for frame in ws:
            self._last_frame = time.monotonic()
            if self._stopping.is_set():
                return
            msg, raw = codec.decode(frame)
            if isinstance(msg, SessionRenewed):
                # grava o token novo ANTES de qualquer outra coisa
                device = await self.store.get_token(self.account.id)
                await self.store.set_token(
                    self.account.id, msg.token, device.device_id if device else ""
                )
                await self.bus.publish(self._translator.system("session.token_renewed"))
                log.info("[%s] token renovado e salvo", self.account.nick)
                continue
            if isinstance(msg, GameError):
                self._raise_for_error(msg)
                self.replies.append((time.monotonic(), f"erro do jogo: {msg.chave}"))
                await self.bus.publish(self._translator.system("game.error", {"key": msg.chave}))
                continue
            events = self._translator.translate(msg, raw)
            for ev in events:
                self.state_view.apply(ev)
                if ev.type == "game.notice" and isinstance(ev.data.get("msg"), str):
                    if ev.data["msg"] not in AMBIENT_NOTICES:
                        self.replies.append((time.monotonic(), ev.data["msg"]))
            self.state_view.server_offset = self._translator.server_offset
            self.state_view.active_pokemon = self._translator.active_profile()
            self.state_view.team = self._translator.team()
            self._copy_progress()
            # o tradutor sabe a hunt atual (hunt, patch, campo.init); os plugins leem daqui
            self.state_view.hunt_slug = self._translator.hunt_slug
            for ev in events:
                await self.bus.publish(ev)

    # --- tratamento de erros e fechamento -----------------------------------

    def _raise_for_error(self, err: GameError) -> None:
        key = err.chave or ""
        if key in NEEDS_LOGIN_KEYS:
            raise _Stop(State.NEEDS_LOGIN, key)
        if key in REJECTED_KEYS:
            reason = f"{key}: {err.motivo_ban}" if err.motivo_ban else key
            raise _Stop(State.REJECTED, reason)
        if key in NEEDS_NICK_KEYS:
            raise _Stop(State.NEEDS_LOGIN, key)
        if key in ONLINE_LIMIT_KEYS:
            self._online_limit_retries += 1
            if self._online_limit_retries > self.settings.online_limit_max_retries:
                raise _Stop(State.REJECTED, f"{key} (limite de tentativas)")
            raise _Retry(key, delay=self.settings.online_limit_retry_s)
        # outros erros (ex.: recusa de ação) não derrubam a sessão

    def _raise_for_close(self, exc: ConnectionClosed) -> None:
        code = exc.rcvd.code if exc.rcvd else None
        if code == CLOSE_EXTERNAL_LOGIN:
            raise _Stop(State.NEEDS_LOGIN, "close 4001: conta aberta em outro lugar")
        if code in CLOSE_REJECTED:
            raise _Stop(State.REJECTED, f"close {code}")
        raise _Retry(f"conexão fechada (code={code})")

    # --- lease --------------------------------------------------------------

    async def _ensure_lease(self) -> bool:
        ok = await self.store.acquire_lease(
            self.account.id, self.settings.worker_holder, self.settings.lease_ttl_s
        )
        if not ok:
            log.warning("[%s] lease com outra instância; aguardando", self.account.nick)
            await self._set_state(State.LEASE_BUSY, "lease ocupado")
        self._has_lease = ok
        return ok

    async def _renew_lease_loop(self, ws: ClientConnection) -> None:
        while True:
            await asyncio.sleep(self.settings.lease_renew_s)
            if not await self._ensure_lease():
                log.error("[%s] lease perdido; desconectando", self.account.nick)
                await ws.close()
                return

    async def _release_lease(self) -> None:
        if self._has_lease:
            with contextlib.suppress(Exception):
                await self.store.release_lease(self.account.id, self.settings.worker_holder)
            self._has_lease = False

    # --- utilidades ---------------------------------------------------------

    def _apply_state(self, welcome: Welcome) -> None:
        st = welcome.estado
        self.state_view.level = st.level
        self.state_view.hunt_slug = st.hunt_slug
        self.state_view.items = dict(st.items)
        self.state_view.balls = None  # o snapshot traz o mapa inteiro de novo

    def _load_catalog(self, raw: dict[str, Any]) -> None:
        catalog = HuntCatalog.from_welcome(raw)
        if not catalog.hunts:
            return  # welcome sem catálogo: mantém o anterior
        self.catalog = catalog
        species = self._species()
        for plugin in self.plugins.running.values():  # plugins seguem vivos entre reconexões
            plugin.ctx.catalog = catalog
            # os sempre ligados (ex.: market_prices) sobem antes da Pokedex terminar de carregar
            if plugin.ctx.species is None and species is not None:
                plugin.ctx.species = species
        task = asyncio.get_running_loop().create_task(self._save_catalog(catalog))
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)
        items = item_rows_from_welcome(raw)
        if items:  # fase 7: itens próprios do servidor, para dar preço aos drops
            task = asyncio.get_running_loop().create_task(self._save_items(items))
            self._bg.add(task)
            task.add_done_callback(self._bg.discard)

    async def _save_items(self, rows: list[dict[str, Any]]) -> None:
        try:
            await save_items(self.store, "welcome", rows)
        except Exception:
            log.exception("[%s] falha ao gravar os itens do welcome", self.account.nick)

    async def _save_catalog(self, catalog: HuntCatalog) -> None:
        try:
            if await save_hunt_catalog(self.store, catalog):
                log.info(
                    "[%s] catálogo de hunts gravado (%d hunts)",
                    self.account.nick,
                    len(catalog.hunts),
                )
        except Exception:
            log.exception("[%s] falha ao gravar o catálogo de hunts", self.account.nick)

    def _make_ctx(self, cls: Any, cfg: Any) -> PluginContext:
        return PluginContext(
            account_id=self.account.id,
            nick=self.account.nick,
            config=cfg,
            bus=self.bus,
            actions=self.gateway,
            state=self.state_view,
            store=self.store,
            settings=self.settings,
            log=logging.getLogger(f"plugin.{cls.name}.{self.account.nick}"),
            catalog=self.catalog,
            species=self._species(),
        )

    async def _record_action(self, type_: str, data: dict[str, Any]) -> None:
        await self.bus.publish(self._translator.system(type_, data))

    async def _set_state(self, state: State, reason: str | None = None) -> None:
        self.state = state
        if reason:
            log.info("[%s] estado=%s (%s)", self.account.nick, state.name, reason)
        else:
            log.info("[%s] estado=%s", self.account.nick, state.name)
        status = DB_STATUS.get(state)
        if status is not None:
            with contextlib.suppress(Exception):
                await self.store.set_status(self.account.id, status)
        if state in (State.NEEDS_LOGIN, State.REJECTED):
            await self.bus.publish(
                self._translator.system(
                    "session.rejected", {"state": state.value, "reason": reason}
                )
            )
            await self.bus.drain()

    async def _disconnected(self, reason: str, *, will_retry: bool) -> None:
        log.warning("[%s] desconectado: %s", self.account.nick, reason)
        await self.bus.publish(
            self._translator.system(
                "session.disconnected", {"reason": reason, "will_retry": will_retry}
            )
        )
        await self._set_state(State.DISCONNECTED)

    def _next_backoff(self) -> float:
        delay = self._backoff
        self._backoff = min(self._backoff * 2, self.settings.reconnect_max_s)
        return delay * random.uniform(0.8, 1.2)

    async def _sleep(self, seconds: float) -> None:
        """Espera `seconds`, ou menos se pedirem para parar ou reconectar."""
        self._wake.clear()
        stop = asyncio.ensure_future(self._stopping.wait())
        wake = asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait({stop, wake}, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
            wake.cancel()
