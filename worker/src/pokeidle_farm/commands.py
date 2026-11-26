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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .actions import (
    ActionBlocked,
    CenterGo,
    CenterHeal,
    CollectionMove,
    HuntSelect,
    IncubatorPut,
    MarketCancel,
    MarketCreate,
    OutlandTierSelect,
    SellDepot,
    ShopBuy,
    TeamActive,
    TeamMove,
)
from .catalog import BALLS, EGG_ITEMS, ITEM_PRICES
from .events import Event
from .outland_model import best_tier, current_tier, outland_tiers
from .plugins.base import Plugin
from .profile import set_travado
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

    def _check_hunt_species(self, acc: AccountRecord, slug: str, species_id: int) -> None:
        """Capturar o X numa hunt que não é dele gasta bola à toa (20/11: Totodile na `larvitar`)."""
        live = self.live.get(acc.id)
        catalog = getattr(live.session if live else None, "catalog", None)
        hunt = catalog.hunts.get(slug) if catalog is not None else None
        if hunt is not None and hunt.species_id != species_id:
            raise CommandError(f"a hunt {slug} não é da espécie {species_id}")

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

        out = await self._send_now(acc, TeamMove(pokemon_id=pid, slot=slot), confirm=done)
        if slot is None and p.to is not None:
            try:
                out["moved_to"] = await self._set_place(acc, {pid: p.to}) and p.to
            except CommandError as exc:  # saiu da equipe; só a marca de Coleção/Depot falhou
                out["place_error"] = str(exc)
        return out

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
        # só o `team.move` pede o Pokécenter; trocar só o ativo o jogo aceita na hunt (26/11: as
        # trocas de ativo pelo "Aplicar" iam ao centro e voltavam sem precisar)
        needs_center = any(st.kind != "active" for st in plan)
        until = datetime.now(UTC) + timedelta(minutes=6)
        for a in APPLY_HOLDS:
            gateway.hold(a, until, APPLY_OWNER, "montar equipe")
        done: list[str] = []
        failure: str | None = None
        went = False
        try:
            await gateway.note("team.apply.started", {"steps": [s.label() for s in plan]})
            if needs_center and not view.in_center:
                await self._go_to_center(session)
                went = True
                done.append("foi ao centro")
            for st in plan:
                await self._step(session, *self._apply_action(st), within=6.0, tries=2)
                done.append(st.label())
            left = {pid: p.left_to.get(str(pid)) for pid in current.values() if pid not in ids}
            places = {pid: to for pid, to in left.items() if to is not None}
            for pid in await self._set_place(acc, places):
                done.append(f"{pid} {'na Coleção' if places[pid] == 'colecao' else 'no Depot'}")
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
            gateway.release(APPLY_OWNER)  # as travas dos outros (hunt_hold, captura) ficam
            await gateway.note("team.apply.finished", {"done": done, "failed": failure is not None})
        if failure is not None:
            raise CommandError(f"{failure}. Feito: {', '.join(done) or 'nada'}")
        return {"steps": done, "back": back if went else None}

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

    def _profile(self, acc: AccountRecord) -> Any:
        """O ProfileState do plugin profile (pokémons e a Coleção), ou None antes do welcome."""
        live = self.live.get(acc.id)
        plugins = getattr(live.session, "plugins", None) if live else None
        prof = getattr(plugins, "running", {}).get("profile") if plugins is not None else None
        state = getattr(prof, "profile", None)
        return state if state is not None and state.ready else None

    def _mons(self, acc: AccountRecord) -> dict[Any, dict[str, Any]] | None:
        """Todos os pokémons da conta como o jogo manda (equipe, Depot e Coleção), do plugin profile."""
        state = self._profile(acc)
        return getattr(state, "pokemons", None) if state is not None else None

    async def _set_place(self, acc: AccountRecord, places: dict[int, str]) -> list[int]:
        """Marca cada pokémon como da Coleção ("colecao") ou do Depot ("depot"), quem sai da equipe.
        Devolve os que mudaram (quem já estava no lugar pedido fica como está)."""
        mons = self._mons(acc) or {}
        state = self._profile(acc)
        moved: list[int] = []
        for pid, to in places.items():
            mon = mons.get(pid)
            want = to == "colecao"
            if mon is None or state is None or state.in_collection(pid) == want:
                continue
            if moved:  # o gateway segura 1 s entre marcações: espera em vez de falhar
                await asyncio.sleep(CollectionMove.min_interval_s + 0.05)
            await self._mark_place(acc, mons, pid, want)
            moved.append(pid)
        return moved

    async def _collection_move(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Põe o pokémon na Coleção (fica) ou devolve ao Depot (vai na próxima venda)."""
        try:
            p = CollectionMoveParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        mons = self._mons(acc)
        if mons is None:
            raise CommandError("a coleção ainda não carregou; tente em alguns segundos")
        if p.pokemon_ids:  # em lote, pela tabela do painel (refatoracao-2026-11-20, 4.2)
            missing = [pid for pid in p.pokemon_ids if pid not in mons]
            if missing:
                raise CommandError(f"pokémon não encontrado na conta: {missing[:5]}")
            moved = await self._set_place(acc, {pid: p.to for pid in p.pokemon_ids})
            return {"moved": len(moved), "to": p.to}
        assert p.pokemon_id is not None
        mon = mons.get(p.pokemon_id)
        if mon is None:
            raise CommandError("pokémon não encontrado na conta")
        want = p.to == "colecao"
        if self._profile(acc).in_collection(p.pokemon_id) == want:
            return {"detail": "já estava assim"}
        return await self._mark_place(acc, mons, p.pokemon_id, want)

    async def _mark_place(
        self, acc: AccountRecord, mons: dict[Any, dict[str, Any]], pid: int, want: bool
    ) -> dict[str, Any]:
        """Uma marca de Coleção/Depot. A Coleção do jogo é a lista `automation.pokemonTravado`; ele
        responde `batalha` k "colecao" (`id`, `naColecao`) e só manda a lista depois. Esperar a lista
        dava "sem confirmação" numa marcação feita (19 e 20/11, no fim do team.apply)."""
        session = self.live[acc.id].session
        state = self._profile(acc)
        since = time.monotonic()

        def confirmed(_v: Any) -> bool:
            reply = _replied(session, "colecao", since)
            if reply is not None:
                return "naColecao" not in reply or bool(reply["naColecao"]) == want
            return state is not None and state.in_collection(pid) == want

        out = await self._send_now(
            acc,
            CollectionMove(pokemon_id=pid, to="colecao" if want else "depot"),
            confirm=confirmed,
        )
        # a marca já vale para os próximos comandos, para a coleção do painel e para o auto.set (que
        # manda a automation inteira: com a lista velha, apagaria a marca)
        if state is not None:
            state.set_collection(pid, want)
        view = getattr(session, "state_view", None)
        set_travado(getattr(view, "automation", None), pid, want)
        return out

    async def _depot_sell(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Vende o Depot inteiro. Recusa se ele cresceu desde o que o painel mostrou, ou se tem
        shiny e o pedido não liberou."""
        try:
            p = DepotSellParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        mons = self._mons(acc)
        if mons is None:
            raise CommandError("a coleção ainda não carregou; tente em alguns segundos")
        state = self._profile(acc)
        depot = [
            m for pid, m in mons.items() if m.get("slot") is None and not state.in_collection(pid)
        ]
        if not depot:
            return {"sold": 0, "detail": "o Depot está vazio"}
        if len(depot) > p.expected:
            raise CommandError(
                f"o Depot tem {len(depot)} e o painel mostrou {p.expected}: confira e venda de novo"
            )
        shinies = [m for m in depot if m.get("shiny")]
        if shinies and not p.allow_shiny:
            raise CommandError(f"há {len(shinies)} shiny no Depot: mova para a Coleção antes")
        ids = {m.get("id") for m in depot}
        session = self.live[acc.id].session
        since = time.monotonic()

        def sold() -> dict[str, Any] | None:
            return _replied(session, "venda", since)

        # o jogo confirma com um `batalha` k "venda" (qtd, ganho) e só tira os pokémons do estado
        # depois: esperar eles sumirem dava "sem confirmação" numa venda feita (20/11: 305 por 16 M)
        out = await self._send_now(
            acc,
            SellDepot(),
            confirm=lambda _v: sold() is not None or not (ids & set(mons)),
            timeout_s=10.0,
        )
        sale = sold() or {}
        for pid in ids:  # vendidos: fora da coleção que os próximos comandos leem
            mons.pop(pid, None)
        return {**out, "sold": sale.get("qtd", len(ids)), "gold": sale.get("ganho")}

    async def _hunt_select(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Hunt escolhida pelo painel, travada por `hours` (plugin hunt_hold; painel-fase-3.md)."""
        try:
            p = HuntSelectParams.model_validate(params)
        except ValidationError as exc:
            raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc
        self._check_hunt_level(acc, p.slug)
        until = datetime.now(UTC) + timedelta(hours=p.hours)
        # um desvio por vez (refatoracao-2026-11-20, 3): a hunt manual encerra a captura
        configs = await self.store.plugin_configs(acc.id)
        if configs.get("capture_target", (False, {}))[0]:
            await self._plugin_set(acc, {"plugin": "capture_target", "enabled": False})
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
        self._check_hunt_species(acc, p.hunt_slug, p.species_id)
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

    # --- loja e Mercado pelo painel (refatoracao-2026-11-20, seção 5) -------------------------

    def _view(self, acc: AccountRecord) -> Any:
        live = self.live.get(acc.id)
        return getattr(live.session if live else None, "state_view", None)

    async def _shop_buy(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Compra na loja do NPC. Confere o ouro antes e confirma pelo estoque que volta do jogo."""
        p = _parse(ShopBuyParams, params)
        price = BALLS[p.id].price if p.kind == "ball" and p.id in BALLS else ITEM_PRICES.get(p.id)
        if price is None:
            raise CommandError(f"a loja não vende o {p.kind} {p.id}")
        view = self._view(acc)
        gold = getattr(view, "gold", None)
        cost = price * p.qty
        if isinstance(gold, int | float) and cost > gold:
            raise CommandError(f"custa {cost} de ouro e a conta tem {int(gold)}")
        key = str(p.id)

        def stock(v: Any) -> int:
            bag = (v.balls if p.kind == "ball" else v.items) or {}
            return int(bag.get(key, 0) or 0)

        before = stock(view) if view is not None else 0
        out = await self._send_now(
            acc, ShopBuy(kind=p.kind, id=p.id, qty=p.qty), confirm=lambda v: stock(v) > before
        )
        return {**out, "cost": cost}

    async def _market_sell(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Anuncia um item no Mercado. Confirma pelo item saindo da mochila."""
        p = _parse(MarketSellParams, params)
        view = self._view(acc)
        key = str(p.item_id)
        have = int(((getattr(view, "items", None) or {}).get(key, 0)) or 0)
        if view is not None and have < p.qty:
            raise CommandError(f"a mochila tem {have} desse item, menos que {p.qty}")
        return await self._send_now(
            acc,
            MarketCreate(itemId=p.item_id, qtd=p.qty, preco=p.price, moeda=p.currency),
            confirm=lambda v: int(((v.items or {}).get(key, 0)) or 0) < have,
        )

    async def _incubator_put(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Põe um ovo da mochila numa vaga livre da chocadeira (estado.chocadeira {total, ovos})."""
        p = _parse(IncubatorPutParams, params)
        view = self._view(acc)
        items = getattr(view, "items", None) or {}
        if int(items.get(str(EGG_ITEMS[p.egg]), 0) or 0) < 1:
            raise CommandError(f"a mochila não tem o ovo {p.egg}")
        state = self._profile(acc)
        choc = (state.estado.get("chocadeira") if state is not None else None) or {}
        total = int(choc.get("total") or 1)
        busy = {o.get("slot") for o in choc.get("ovos") or [] if isinstance(o, dict)}
        slot = p.slot
        if slot is None:
            slot = next((s for s in range(total) if s not in busy), None)
            if slot is None:
                raise CommandError(f"a chocadeira está cheia ({total} vagas)")
        elif slot >= total or slot in busy:
            raise CommandError(f"a vaga {slot + 1} não está livre")
        session = self.live[acc.id].session
        since = time.monotonic()
        out = await self._send_now(
            acc,
            IncubatorPut(slot=slot, ovo=p.egg),
            confirm=lambda _v: _replied(session, "ovoColocado", since) is not None,
        )
        reply = _replied(session, "ovoColocado", since) or {}
        return {**out, "slot": slot, "egg": p.egg, "hatches_at": reply.get("fim")}

    async def _market_cancel(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Cancela um anúncio da conta. O jogo não responde: o item volta pela mochila."""
        p = _parse(MarketCancelParams, params)
        return await self._send_now(acc, MarketCancel(id=p.listing_id))

    async def _outland_tier(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Escolhe o tier da Outland pelo número (1 a 40); sem número, o maior liberado. Recusa tier
        acima do nível do treinador (o jogo cairia no maior liberado). Confirma pelo estado.outlandTier."""
        p = _parse(OutlandTierParams, params)
        live = self.live.get(acc.id)
        catalog = getattr(live.session if live else None, "catalog", None)
        tiers = outland_tiers(getattr(catalog, "rules", None) or {})
        if not tiers:
            raise CommandError("as regras da Outland ainda não chegaram (espere o welcome)")
        view = self._view(acc)
        level = getattr(view, "level", None)
        if p.number is None:
            target = best_tier(tiers, level)
            if target is None:
                raise CommandError(
                    f"a Outland pede nível {tiers[0].level}; a conta está no {level}"
                )
        else:
            target = next((t for t in tiers if t.number == p.number), None)
            if target is None:
                raise CommandError(f"não existe a Outland {p.number} (vai de 1 a {len(tiers)})")
            if isinstance(level, int) and target.level > level:
                raise CommandError(
                    f"a Outland {p.number} pede nível {target.level} e a conta está no {level}"
                )
        now = current_tier(tiers, getattr(view, "outland_tier", None))
        if now is not None and now.tier == target.tier and view.outland_tier is not None:
            return {"tier": target.tier, "number": target.number, "detail": "já estava nesse tier"}
        out = await self._send_now(
            acc,
            OutlandTierSelect(tier=target.tier),
            confirm=lambda v: getattr(v, "outland_tier", None) == target.tier,
        )
        result = {**out, "tier": target.tier, "number": target.number, "mult": target.mult}
        top = best_tier(tiers, level)
        if top is not None and target.level < top.level:
            result["warning"] = (
                f"a Outland {top.number} está liberada: o plugin outland_tier sobe de novo; "
                "desligue o active dele para ficar neste tier"
            )
        return result

    async def _focus_set(self, acc: AccountRecord, params: dict[str, Any]) -> dict[str, Any]:
        """Foco da conta (captura, ouro-xp-drop, rank, gemas, XP ou Outland): restock, rank e gems juntos.

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

        # "bola em tudo" (catch_all) é uma opção de qualquer modo, não um foco (refatoracao, 3):
        # o restock com focus "capture". O foco "capture" antigo vira ouro e drop + bola em tudo.
        # Sem catch_all no comando, mantém o que estava.
        current_restock = configs.get("restock", (True, {}))[1]
        catch_all = p.catch_all
        if catch_all is None:
            catch_all = p.focus == "capture" or current_restock.get("focus") == "capture"
        if p.focus == "rank":
            restock_focus = "rank"  # o rank escolhe a bola; o fallback_focus vale sem alvo
        else:
            restock_focus = "capture" if catch_all else "gold_xp_drop"
        restock_cfg = {**current_restock, "focus": restock_focus}
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
        if p.focus in ("gems", "xp", "outland"):
            gems_cfg = {
                **configs.get("gems", (False, {}))[1],
                **(p.gems or {}),
                "dry_run": False,
                "objective": p.focus,
            }
            writes.append(("gems", True, gems_cfg))
        elif "gems" in configs:
            writes.append(("gems", False, configs["gems"][1]))
        # treinar a equipe é opção do XP (o foco leva a conta para a hunt de quem treina, 2.5);
        # fora dele o team_train desliga: trocaria o ativo sem ninguém mudar a hunt
        if p.focus == "xp" and p.train is not None:
            train_cfg = {**configs.get("team_train", (False, {}))[1]}
            if p.train.target_level is not None:
                train_cfg["target_level"] = p.train.target_level
            writes.append(("team_train", p.train.enabled, train_cfg))
        elif p.focus != "xp" and configs.get("team_train", (False, {}))[0]:
            writes.append(("team_train", False, configs["team_train"][1]))

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


def _replied(session: Any, kind: str, since: float) -> dict[str, Any] | None:
    """A resposta `batalha` desse tipo depois de `since` (sessões de teste sem o registro: None)."""
    replied = getattr(session, "replied", None)
    return replied(kind, since) if replied is not None else None


def _parse[M: BaseModel](model: type[M], params: dict[str, Any]) -> M:
    try:
        return model.model_validate(params)
    except ValidationError as exc:
        raise CommandError(f"params inválidos: {exc.errors()[0]['msg']}") from exc


class ShopBuyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ball", "item"]
    id: int = Field(gt=0)
    qty: int = Field(ge=1, le=10_000)


class MarketSellParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int = Field(gt=0)
    qty: int = Field(ge=1, le=100_000)
    price: int = Field(ge=1, le=100_000_000)  # por unidade
    currency: Literal["orb", "gold"] = "orb"


class IncubatorPutParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    egg: Literal["p2", "p3", "p4", "shiny"]
    slot: int | None = Field(None, ge=0, le=5)  # None: a primeira vaga livre


class OutlandTierParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int | None = Field(None, ge=1, le=40)  # Outland N; None: o maior liberado


class MarketCancelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: int | str


class TeamActiveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pokemon_id: int = Field(gt=0)


class TeamMoveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pokemon_id: int = Field(gt=0)
    slot: int | None = Field(None, ge=0, le=5)
    # ao tirar (slot null): para onde vai. None deixa a marca como está
    to: Literal["colecao", "depot"] | None = None


class TeamApplyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team: list[int | None] = Field(min_length=1, max_length=TEAM_SLOTS)  # ids por vaga, da 1 à 5
    active: int = Field(gt=0)
    # quem sai da equipe: id -> "colecao" ou "depot". Quem não está aqui fica com a marca de antes
    left_to: dict[str, Literal["colecao", "depot"]] = Field(default_factory=dict)


class CollectionMoveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pokemon_id: int | None = Field(None, gt=0)
    pokemon_ids: list[int] | None = Field(None, min_length=1, max_length=100)
    to: Literal["colecao", "depot"] = "colecao"

    @model_validator(mode="after")
    def _one_of(self) -> CollectionMoveParams:
        if (self.pokemon_id is None) == (self.pokemon_ids is None):
            raise ValueError("mande pokemon_id ou pokemon_ids")
        return self


class DepotSellParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: int = Field(ge=0)  # quantos o painel mostrou: não vende se o Depot cresceu
    allow_shiny: bool = False


class HuntSelectParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=64)
    hours: float = Field(2.0, ge=0.25, le=24)


class CaptureStartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    species_id: int
    species_name: str | None = Field(None, max_length=64)
    hunt_slug: str = Field(min_length=1, max_length=64)
    # None: a que vale a pena; 5 é a Beast Ball (só do estoque, não se compra)
    ball_id: int | None = Field(None, ge=1, le=5)
    count: int | None = Field(None, ge=1, le=10_000)
    hours: float | None = Field(None, ge=0.25, le=72)


class TrainParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    target_level: int | None = Field(None, ge=2, le=100_000)


class FocusSetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: Literal["capture", "gold_xp_drop", "rank", "gems", "xp", "outland"]
    # campos do rank (rank_balls, rank_ball_rule, fallback_hunt...) e o fallback_focus do restock
    rank: dict[str, Any] | None = None
    # campos do gems (max_market_share, hysteresis...)
    gems: dict[str, Any] | None = None
    catch_all: bool | None = None  # jogar a melhor bola que se paga em todo selvagem
    train: TrainParams | None = None  # só no foco XP


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
    "shop.buy": Supervisor._shop_buy,
    "market.sell": Supervisor._market_sell,
    "market.cancel": Supervisor._market_cancel,
    "incubator.put": Supervisor._incubator_put,
    "outland.tier": Supervisor._outland_tier,
    "hunt.select": Supervisor._hunt_select,
    "hunt.release": Supervisor._hunt_release,
    "capture.start": Supervisor._capture_start,
    "capture.stop": Supervisor._capture_stop,
    "team.active": Supervisor._team_active,
    "team.move": Supervisor._team_move,
    "center.heal": Supervisor._center_heal,
    "team.apply": Supervisor._team_apply,
    "collection.move": Supervisor._collection_move,
    "depot.sell": Supervisor._depot_sell,
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
        self.battle_replies: dict[str, tuple[float, dict[str, Any]]] = {}

    def replied(self, kind: str, since: float) -> dict[str, Any] | None:
        got = self.battle_replies.get(kind)
        return got[1] if got is not None and got[0] >= since else None

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
