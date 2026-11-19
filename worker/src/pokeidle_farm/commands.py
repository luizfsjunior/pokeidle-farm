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
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .actions import ActionBlocked, CenterGo, CenterHeal, HuntSelect, TeamActive, TeamMove
from .events import Event
from .plugins.base import Plugin
from .store.base import AccountRecord, CommandRecord, Store
from .team_apply import TEAM_SLOTS, Step, plan_moves, team_by_slot

log = logging.getLogger(__name__)

MAX_FARM_ACCOUNTS = 4  # Termos, seção 5: 4 por pessoa; a pessoal também roda no worker (ADR 0014)
# quanto o comando do painel espera o jogo mostrar o efeito (conta-v2.md, seção 2)
CONFIRM_TIMEOUT_S = 4.0
# comandos que demoram mais que o teto geral do CommandLoop
LONG_TIMEOUTS_S = {"team.apply": 300.0}
# o que ninguém além do team.apply manda enquanto ele monta a equipe
APPLY_HOLDS = ("hunt.select", "centro.ir", "centro.curar", "team.move", "team.active", "auto.set")
APPLY_OWNER = "team_apply"
# ir ao centro espera uma folga sem dano (estado.centroLivreEm, que cada golpe renova): entre ondas
CENTER_DEADLINE_S = 150.0
CENTER_MARGIN_S = 0.3


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

    async def _send_now(
        self,
        acc: AccountRecord,
        action: Any,
        confirm: Callable[[Any], bool] | None = None,
        timeout_s: float = CONFIRM_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Manda uma ação do painel pela sessão da conta (precisa estar conectada).

        Com `confirm(state_view)`, o comando só fica "feito" quando o estado que volta do jogo
        mostra o efeito; se o jogo responder com um aviso ou erro, falha com o texto dele
        (docs/design/conta-v2.md, seção 2).
        """
        live = self.live.get(acc.id)
        session = live.session if live else None
        gateway = getattr(session, "gateway", None)
        if not self._is_running(acc.id) or gateway is None:
            raise CommandError("a conta não está conectada")
        since = time.monotonic()
        try:
            await gateway.submit(action, source="panel")
        except ActionBlocked as exc:
            wait = f" (tente em {exc.wait_s:.0f} s)" if exc.wait_s else ""
            raise CommandError(f"bloqueado: {exc.reason}{wait}") from exc
        out: dict[str, Any] = {"sent": action.to_wire()}
        waiter = getattr(session, "confirm", None)
        if confirm is not None and waiter is not None:
            view = session.state_view
            problem = await waiter(lambda: confirm(view), since, timeout_s)
            if problem is not None:
                raise CommandError(f"o jogo não fez: {problem}")
            out["confirmed"] = True
        return out

    def _check_hunt_level(self, acc: AccountRecord, slug: str) -> None:
        """O jogo tranca hunt acima do nível do treinador: recusa antes de gravar a trava."""
        live = self.live.get(acc.id)
        session = live.session if live else None
        catalog = getattr(session, "catalog", None)
        view = getattr(session, "state_view", None)
        hunt = catalog.hunts.get(slug) if catalog is not None else None
        level = getattr(view, "level", None)
        if hunt is not None and isinstance(level, int) and hunt.level > level:
            raise CommandError(
                f"a hunt {slug} pede nível {hunt.level} e a conta está no {level}: o jogo tranca"
            )

    async def _team_active(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Troca o pokémon ativo (docs/design/team-train.md)."""
        try:
            p = TeamActiveParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        pid = p.pokemon_id
        return await self._send_now(
            acc,
            TeamActive(pokemon_id=pid),
            confirm=lambda v: (v.active_pokemon or {}).get("id") == pid,
        )

    async def _team_move(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Põe o pokémon num slot da equipe, ou tira (slot null)."""
        try:
            p = TeamMoveParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        pid, slot = p.pokemon_id, p.slot

        def done(v: Any) -> bool:
            team = {m.get("id"): m.get("slot") for m in (v.team or [])}
            return pid not in team if slot is None else team.get(pid) == slot

        return await self._send_now(acc, TeamMove(pokemon_id=pid, slot=slot), confirm=done)

    async def _center_heal(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Cura a equipe no Pokécenter (`centro.curar`); confirma quando a conta sai do centro."""
        return await self._send_now(
            acc, CenterHeal(), confirm=lambda v: v.in_center is False, timeout_s=8.0
        )

    async def _step(
        self,
        session: Any,
        action: Any,
        check: Callable[[Any], bool],
        *,
        within: float = CONFIRM_TIMEOUT_S,
        tries: int = 1,
    ) -> None:
        """Manda uma ação do team.apply e espera o efeito; espera o intervalo do gateway se preciso."""
        view = session.state_view
        problem: str | None = None
        attempt = 0
        while attempt < tries:
            since = time.monotonic()
            try:
                await session.gateway.submit(action, source=APPLY_OWNER)
            except ActionBlocked as exc:
                if exc.wait_s is not None and exc.wait_s <= 30:
                    await asyncio.sleep(exc.wait_s + 0.2)
                    continue
                raise CommandError(f"{action.name} bloqueado: {exc.reason}") from exc
            attempt += 1
            problem = await session.confirm(lambda: check(view), since, within)
            if problem is None:
                return
        raise CommandError(f"{action.name}: {problem}")

    async def _team_apply(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Aplica a equipe montada no painel: centro, trocas, ativo e volta à hunt (conta-v2.md, 3)."""
        try:
            p = TeamApplyParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        live = self.live.get(acc.id)
        session = live.session if live else None
        gateway = getattr(session, "gateway", None)
        view = getattr(session, "state_view", None)
        if not self._is_running(acc.id) or gateway is None or view is None:
            raise CommandError("a conta não está conectada")
        ids = [x for x in p.team if x is not None]
        if len(set(ids)) != len(ids):
            raise CommandError("o mesmo pokémon está em duas vagas")
        if p.active not in ids:
            raise CommandError("o ativo tem que estar na equipe")

        current = team_by_slot(view.team)
        active = (view.active_pokemon or {}).get("id")
        target = [*p.team, *[None] * (TEAM_SLOTS - len(p.team))]
        plan = plan_moves(current, active, target, p.active)
        if not plan:
            return {"steps": [], "detail": "a equipe já está assim"}

        back = view.hunt_slug if not view.in_center else None
        saved = {a: gateway.holds[a] for a in APPLY_HOLDS if a in gateway.holds}
        until = datetime.now(UTC) + timedelta(minutes=6)
        for a in APPLY_HOLDS:
            gateway.hold(a, until, APPLY_OWNER, "montar equipe")
        done: list[str] = []
        failure: str | None = None
        went = False
        try:
            await gateway.note("team.apply.started", {"steps": [s.label() for s in plan]})
            if not view.in_center:
                await self._go_to_center(session)
                went = True
                done.append("foi ao centro")
            for st in plan:
                await self._step(session, *self._apply_action(st), within=6.0, tries=2)
                done.append(st.label())
        except CommandError as exc:
            failure = str(exc)
        finally:
            if back and went:
                try:
                    await self._step(
                        session,
                        HuntSelect(slug=back),
                        lambda v: v.in_center is False,
                        within=8.0,
                        tries=4,
                    )
                    done.append(f"voltou para {back}")
                except CommandError as exc:
                    failure = failure or str(exc)
                    done.append(f"não voltou para {back}")
            gateway.release(APPLY_OWNER)
            gateway.holds.update(saved)
            await gateway.note("team.apply.finished", {"done": done, "failed": failure is not None})
        if failure is not None:
            raise CommandError(f"{failure}. Feito: {', '.join(done) or 'nada'}")
        return {"steps": done, "back": back}

    async def _go_to_center(self, session: Any) -> None:
        """`centro.ir` só vale numa folga sem tomar nem dar dano (o `centroLivreEm`, que cada golpe
        renova). Espera o fim da trava, manda e, se o jogo responder "em combate", espera a próxima
        folga (entre ondas ela aparece), até CENTER_DEADLINE_S."""
        view = session.state_view
        deadline = time.monotonic() + CENTER_DEADLINE_S
        problem = "sem folga no combate"
        while time.monotonic() < deadline:
            lock = getattr(view, "combat_free_at", None)
            if lock is not None:
                left = (lock - view.server_now()).total_seconds() + CENTER_MARGIN_S
                if left > 0:
                    await asyncio.sleep(min(left, 5.0))
                    continue
            since = time.monotonic()
            try:
                await session.gateway.submit(CenterGo(), source=APPLY_OWNER)
            except ActionBlocked as exc:
                if exc.wait_s is not None and exc.wait_s <= 30:
                    await asyncio.sleep(exc.wait_s + 0.05)
                    continue
                raise CommandError(f"centro.ir bloqueado: {exc.reason}") from exc
            got = await session.confirm(lambda: view.in_center is True, since, 3.0)
            if got is None:
                return
            problem = got
            await asyncio.sleep(0.5)
        raise CommandError(f"centro.ir: {problem} (tentei por {CENTER_DEADLINE_S:.0f} s)")

    @staticmethod
    def _apply_action(st: Step) -> tuple[Any, Callable[[Any], bool]]:
        pid, slot = st.pokemon_id, st.slot
        if st.kind == "active":
            return TeamActive(pokemon_id=pid), lambda v: (v.active_pokemon or {}).get("id") == pid

        def placed(v: Any) -> bool:
            team = team_by_slot(v.team)
            return pid not in team.values() if slot is None else team.get(slot) == pid

        return TeamMove(pokemon_id=pid, slot=slot), placed

    async def _hunt_select(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Hunt escolhida pelo painel, travada por `hours` (plugin hunt_hold; painel-fase-3.md)."""
        try:
            p = HuntSelectParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        self._check_hunt_level(acc, p.slug)
        until = datetime.now(UTC) + timedelta(hours=p.hours)
        out = await self._plugin_set(
            acc,
            {
                "plugin": "hunt_hold",
                "enabled": True,
                "config": {"slug": p.slug, "until": until.isoformat()},
            },
        )
        return {**out, "slug": p.slug, "until": until.isoformat()}

    async def _hunt_release(self, acc: AccountRecord, _p: dict[str, Any]) -> dict[str, Any]:
        if "hunt_hold" not in await self.store.plugin_configs(acc.id):
            return {"enabled": False, "applied": "nada a soltar"}
        return await self._plugin_set(acc, {"plugin": "hunt_hold", "enabled": False})

    async def _capture_start(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Capturar uma espécie (plugin capture_target; docs/design/captura-alvo.md)."""
        try:
            p = CaptureStartParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        self._check_hunt_level(acc, p.hunt_slug)
        now = datetime.now(UTC)
        until = now + timedelta(hours=p.hours) if p.hours else None
        config = {
            "species_id": p.species_id,
            "species_name": p.species_name,
            "hunt_slug": p.hunt_slug,
            "ball_id": p.ball_id,
            "count": p.count,
            "until": until.isoformat() if until else None,
            "started_at": now.isoformat(),
        }
        # a hunt escolhida antes (hunt_hold) sai: a captura cuida da hunt agora
        configs = await self.store.plugin_configs(acc.id)
        if configs.get("hunt_hold", (False, {}))[0]:
            await self._plugin_set(acc, {"plugin": "hunt_hold", "enabled": False})
        out = await self._plugin_set(
            acc, {"plugin": "capture_target", "enabled": True, "config": config}
        )
        return {**out, "species_id": p.species_id, "until": config["until"], "count": p.count}

    async def _capture_stop(self, acc: AccountRecord, _p: dict[str, Any]) -> dict[str, Any]:
        if "capture_target" not in await self.store.plugin_configs(acc.id):
            return {"enabled": False, "applied": "nada a parar"}
        return await self._plugin_set(acc, {"plugin": "capture_target", "enabled": False})

    async def _focus_set(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Foco da conta (captura, ouro-xp-drop, rank ou gemas): restock, rank e gems juntos.

        Ver docs/design/fase-3b-rank-ligado.md, seção 7, e docs/design/foco-gemas-e-ritmo.md.
        Valida as configs antes de gravar qualquer uma; preserva o resto da config de cada
        plugin. No foco gemas o restock fica em gold_xp_drop (sem bola) e o gems escolhe a hunt.
        """
        try:
            p = FocusSetParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        configs = await self.store.plugin_configs(acc.id)
        rank_fields = dict(p.rank or {})
        fallback_focus = rank_fields.pop("fallback_focus", None)

        # gemas e XP: o restock só cuida de poções (bolas desligadas); o gems escolhe a hunt
        restock_focus = "gold_xp_drop" if p.focus in ("gems", "xp") else p.focus
        restock_cfg = {**configs.get("restock", (True, {}))[1], "focus": restock_focus}
        # foco XP: poção sem teto por hora (o ouro é só para sobreviver; decisão de 16/11)
        if p.focus == "xp":
            restock_cfg["potions_uncapped"] = True
        else:
            restock_cfg.pop("potions_uncapped", None)
        if p.focus == "rank" and fallback_focus is not None:
            restock_cfg["fallback_focus"] = fallback_focus
        writes: list[tuple[str, bool, dict[str, Any]]] = [("restock", True, restock_cfg)]
        if p.focus == "rank":
            rank_cfg = {**configs.get("rank", (False, {}))[1], **rank_fields, "dry_run": False}
            writes.append(("rank", True, rank_cfg))
        elif "rank" in configs:
            writes.append(("rank", False, configs["rank"][1]))
        # gems depois do rank: ao subir, ele confere se o rank ainda está agindo
        if p.focus in ("gems", "xp"):
            gems_cfg = {
                **configs.get("gems", (False, {}))[1],
                **(p.gems or {}),
                "dry_run": False,
                "objective": p.focus,
            }
            writes.append(("gems", True, gems_cfg))
        elif "gems" in configs:
            writes.append(("gems", False, configs["gems"][1]))

        for name, _, cfg in writes:
            cls = self.available.get(name)
            if cls is None:
                raise CommandError(f"plugin desconhecido: {name}")
            try:
                cls.config_model.model_validate(cfg)
            except ValidationError as exc:
                first = exc.errors()[0]
                where = ".".join(str(x) for x in first["loc"]) or "config"
                raise CommandError(f"config inválida em {name}.{where}: {first['msg']}") from exc

        for name, enabled, cfg in writes:
            await self.store.set_plugin_config(acc.id, name, enabled, cfg)
        applied = False
        if self._is_running(acc.id):
            session = self.live[acc.id].session
            applied = True
            for name, _, _ in writes:  # restock antes: o rank confere o foco dele ao subir
                applied = await session.restart_plugin(name) and applied
        return {"focus": p.focus, "applied": "agora" if applied else "na próxima conexão"}


class TeamActiveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pokemon_id: int = Field(gt=0)


class TeamMoveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pokemon_id: int = Field(gt=0)
    slot: int | None = Field(None, ge=0, le=5)


class TeamApplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team: list[int | None] = Field(min_length=1, max_length=TEAM_SLOTS)  # ids por vaga, da 1 à 5
    active: int = Field(gt=0)


class HuntSelectParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=64)
    hours: float = Field(2.0, ge=0.25, le=24)


class CaptureStartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    species_id: int
    species_name: str | None = Field(None, max_length=64)
    hunt_slug: str = Field(min_length=1, max_length=64)
    ball_id: int = Field(4, ge=1, le=4)
    count: int | None = Field(None, ge=1, le=10_000)
    hours: float | None = Field(None, ge=0.25, le=72)


class FocusSetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: Literal["capture", "gold_xp_drop", "rank", "gems", "xp"]
    # campos do rank (rank_balls, rank_ball_rule, fallback_hunt...) e o fallback_focus do restock
    rank: dict[str, Any] | None = None
    # campos do gems (max_market_share, hysteresis...)
    gems: dict[str, Any] | None = None


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
    "focus.set": Supervisor._focus_set,
    "hunt.select": Supervisor._hunt_select,
    "hunt.release": Supervisor._hunt_release,
    "capture.start": Supervisor._capture_start,
    "capture.stop": Supervisor._capture_stop,
    "team.active": Supervisor._team_active,
    "team.move": Supervisor._team_move,
    "center.heal": Supervisor._center_heal,
    "team.apply": Supervisor._team_apply,
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
        limit = LONG_TIMEOUTS_S.get(cmd.type, self.timeout_s)
        if self._rate_limited(cmd.account_id):
            status, error = "failed", "rate_limited: mais de 10 comandos por minuto"
        else:
            try:
                result = await asyncio.wait_for(self.sup.execute(cmd), limit)
            except CommandError as exc:
                status, error = "failed", str(exc)
            except TimeoutError:
                status, error = "failed", f"timeout ({limit:.0f} s)"
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
