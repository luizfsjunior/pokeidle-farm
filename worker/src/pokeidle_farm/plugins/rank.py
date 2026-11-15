"""Plugin rank: escolhe a hunt do foco "rank semanal" (fase 3b, passos 4 e 5).

Ver docs/design/fase-3b-plugin-rank.md (ensaio) e docs/design/fase-3b-rank-ligado.md
(agindo de verdade). Resumo:
- monta a fila de hunts por tempo até a captura (`rank_queue.plan_queue`) com as
  espécies que já pontuaram na semana, o ritmo medido por hunt e a chance observada;
- grava um `rank.plan` a cada decisão e replaneja na captura, na virada da semana, ao
  subir de nível, ao trocar de bola e quando estoura o tempo na hunt alvo;
- com `dry_run` (padrão) não manda `hunt.select` nem `auto.set`: grava `rank.would`.
  O `topcatch.pedir` (só leitura) vai sempre, respeitando o `ACTION_MODE`;
- sem `dry_run`, e só com o `restock` em `focus: "rank"` (senão continua gravando
  `rank.would`): manda o `hunt.select` quando a trava de combate e o `trocaLivreEm`
  deixam, espera o `hunt.changed`, tenta de novo se falhar, mantém o Lançar até Capturar
  ligado enquanto há alvo e avisa o `restock` com `rank.mode` (active/fallback).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..actions import (
    ActionBlocked,
    ActionSpec,
    AutoSet,
    HuntSelect,
    RankingRequest,
    TopCatchRequest,
)
from ..catalog import BALLS
from ..events import Event
from ..pace import PaceBook, rates_for
from ..rank_queue import QueueItem, observed_chances, plan_queue
from .base import Plugin, PluginContext

BRT = timedelta(hours=-3)  # Brasília, sem horário de verão
HYSTERESIS = 0.10  # só troca de hunt se a nova for pelo menos 10% mais rápida (D-C)
SWITCH_FAILS_TO_SKIP = 3  # falhas seguidas de hunt.select até pular a espécie
RATE_DRIFT = 0.30  # replaneja quando o ritmo medido no alvo foge disso do previsto
PRIZED = 100  # premiados no Top Catch (PREMIADOS_TOP_CATCH do cliente; 11º-100º ganham 5 diamantes)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def week_start(now: datetime) -> str:
    """Domingo 00:00 de Brasília da semana de `now`, no formato do jogo ("2026-11-08")."""
    local = (now.astimezone(UTC) + BRT).date()
    return (local - timedelta(days=(local.weekday() + 1) % 7)).isoformat()


def week_start_utc(week: str) -> datetime:
    d = date.fromisoformat(week)
    return datetime(d.year, d.month, d.day, tzinfo=UTC) - BRT


class RankConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    rank_balls: list[int] = Field(default_factory=lambda: [4, 3, 2, 1], min_length=1)
    rank_ball_rule: Literal["se_paga", "fixa"] = "se_paga"
    window_kills: int = Field(200, ge=1)
    min_kills: int = Field(50, ge=1)
    max_hunt_factor: float = Field(3.0, gt=0)
    min_hunt_minutes: float = Field(10.0, ge=0)
    history_days: int = Field(14, ge=1)
    min_active_minutes: float = Field(5.0, ge=0)  # D-M: o rank passa ~8 min em cada hunt
    default_kills_per_hour: float = Field(300.0, gt=0)
    queue_preview: int = Field(10, ge=0)
    # passo 5 (docs/design/fase-3b-rank-ligado.md, seção 8)
    switch_margin_s: float = Field(0.5, ge=0)
    switch_confirm_s: float = Field(15.0, gt=0)
    switch_retry_s: float = Field(60.0, ge=0)
    max_switches_per_hour: int = Field(10, ge=1)
    retry_after_s: float = Field(60.0, ge=0)
    fallback_hunt: str | None = None


class RankPlugin(Plugin):
    name: ClassVar[str] = "rank"
    description: ClassVar[str] = "Foco rank semanal: fila de hunts até a captura"
    config_model: ClassVar[type[BaseModel]] = RankConfig
    subscribes: ClassVar[set[str]] = {
        "kill",
        "item.consumed",
        "rank.week",
        "rank.catch",
        "auto.catch_until_capture_off",
        "hunt.changed",
        "state.snapshot",
        "state.patch",
        "session.connected",
        "game.error",
        "rank.board",
    }

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)
        self.sleep = asyncio.sleep  # trocado nos testes

    # --- subida -------------------------------------------------------------

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: RankConfig = ctx.config  # type: ignore[assignment]
        self._ready = False
        self._week = week_start(self.now())
        self._scored: set[int] = set()
        self._skipped: list[int] = []
        self._pace = PaceBook(self.cfg.min_active_minutes)
        self._default_kph = self.cfg.default_kills_per_hour
        self._attempts: list[tuple[datetime, dict[str, Any]]] = []
        self._degraded: list[str] = []
        self._level = ctx.state.level or 0
        self._current = ctx.state.hunt_slug
        self._window: deque[list[float]] = deque(maxlen=self.cfg.window_kills)
        self._kills_since_ball = self.cfg.window_kills  # a primeira troca de bola é livre
        self._ball: int | None = None
        self._queue: list[QueueItem] = []
        self._target: QueueItem | None = None
        self._target_since: datetime | None = None
        self._sent: dict[str, dict[str, Any]] = {}
        self._catch_until_off_at: str | None = None
        # passo 6: espécies da semana pelo jogo (n) e a última posição gravada
        self._week_n: int | None = None
        self._position_key: tuple[Any, ...] | None = None
        # passo 5: troca de hunt de verdade
        self._acting = False  # sem dry_run e com o restock em focus "rank"
        self._want_slug: str | None = None  # hunt para onde a conta deve ir
        self._pending: tuple[str, datetime] | None = None  # hunt.select sem confirmação
        self._fails = 0  # falhas seguidas de hunt.select para o alvo atual
        self._retry_at: datetime | None = None
        self._switches: deque[datetime] = deque()  # hunt.select da última hora
        self._capped = False
        self._mode: dict[str, Any] | None = None  # último rank.mode publicado
        self._auto_sent: dict[str, Any] | None = None
        self._auto_sent_at: datetime | None = None
        # a trava de combate é renovada no mesmo frame do golpe que a fecha: esperar
        # o próximo evento nunca a encontra aberta, então um timer acorda quando ela acaba
        self._lock = asyncio.Lock()
        self._timer: asyncio.Task[None] | None = None
        self._timer_at: datetime | None = None
        self._board_due: datetime | None = None  # ranking.pedir barrado: sai quando o limite deixar
        if not self.cfg.dry_run:
            await self._check_restock()
        await self._try_boot()

    async def _check_restock(self) -> None:
        """D-F: só age com o restock em focus "rank" (senão os dois brigam pelo auto.set)."""
        try:
            configs = await self.ctx.store.plugin_configs(self.ctx.account_id)
        except Exception as exc:
            self.ctx.log.warning("rank: não consegui ler a config do restock (%s)", exc)
            configs = {}
        enabled, cfg = configs.get("restock", (False, {}))
        if enabled and (cfg or {}).get("focus") == "rank":
            self._acting = True
        else:
            self._degraded.append("restock_focus")

    async def _try_boot(self) -> None:
        cat = self.ctx.catalog
        if cat is None or not cat.hunts:
            await self.ctx.actions.note(
                "rank.plan",
                {"reason": "sem_catalogo", "dry_run": self.cfg.dry_run, "target": None},
            )
            return
        self._ready = True
        await self._load()
        await self._request_week()
        await self._request_board()
        self._ball = self._ball_choice()
        await self._replan("start")

    async def _load(self) -> None:
        store, acc = self.ctx.store, self.ctx.account_id
        since_week = week_start_utc(self._week)
        try:
            weeks = await store.recent_events(acc, "rank.week", since_week)
            catches = await store.recent_events(acc, "rank.catch", since_week)
        except Exception as exc:
            self.ctx.log.warning("rank: não consegui ler a semana (%s)", exc)
            self._degraded.append("week")
        else:
            base_at: datetime | None = None
            for at, data in weeks:
                if data.get("week_start") == self._week:
                    base_at = at
                    self._scored = _species_keys(data.get("species"))
                    self._note_n(data.get("week_species"))
            for at, data in catches:
                if (
                    data.get("scores") is True
                    and data.get("week_start") == self._week
                    and isinstance(data.get("species_id"), int)
                    and (base_at is None or at >= base_at)
                ):
                    self._scored.add(data["species_id"])
                    self._note_n(data.get("week_species"))
        await self._load_skipped()
        try:
            stats = await store.rank_hunt_stats(
                acc, self.now() - timedelta(days=self.cfg.history_days)
            )
        except Exception as exc:
            self.ctx.log.warning("rank: não consegui ler o ritmo por hunt (%s)", exc)
            self._degraded.append("stats")
            return
        # só hunts do catálogo: eventos do simulador (hunts "sim-*") não podem
        # entrar no ritmo padrão da conta
        hunts = self.ctx.catalog.hunts if self.ctx.catalog else {}
        stats = [s for s in stats if s.hunt_slug in hunts]
        total_kills = sum(s.kills for s in stats)
        total_min = sum(s.active_minutes for s in stats)
        if total_min > 0 and total_kills > 0:
            self._default_kph = total_kills / total_min * 60
        for s in stats:
            self._pace.load(s.hunt_slug, s.kills, s.active_minutes, s.avg_active_level)
            if s.last_chance is not None:
                self._attempts.append(
                    (
                        _EPOCH,
                        {
                            "chance": s.last_chance,
                            "hunt_slug": s.hunt_slug,
                            "ball_id": s.last_ball_id,
                        },
                    )
                )

    async def _load_skipped(self) -> None:
        """Espécies puladas nesta semana sobrevivem a reinícios do plugin (último rank.plan)."""
        since = max(week_start_utc(self._week), self.now() - timedelta(hours=12))
        try:
            plans = await self.ctx.store.recent_events(self.ctx.account_id, "rank.plan", since)
        except Exception:
            return  # a leitura da semana já marcou degraded se o banco caiu
        for _, data in reversed(plans):
            if data.get("week_start") == self._week and isinstance(data.get("skipped"), list):
                self._skipped = [s for s in data["skipped"] if isinstance(s, int)]
                return

    async def _request_week(self) -> None:
        try:
            await self.ctx.actions.submit(TopCatchRequest(), source=self.name)
        except ActionBlocked:
            pass  # o gateway já registrou o motivo

    async def _request_board(self) -> None:
        """Ranking da semana para a posição (passo 6); só leitura, vai mesmo com dry_run."""
        try:
            await self.ctx.actions.submit(RankingRequest(), source=self.name)
        except ActionBlocked as exc:
            if exc.wait_s is not None:
                # rate limit: sem isso a posição fica velha até a próxima espécie (passo 6)
                due = self.now() + timedelta(seconds=exc.wait_s)
                if self._board_due is None or due < self._board_due:
                    self._board_due = due
                self._schedule(self._board_due)
            return
        self._board_due = None

    def _note_n(self, n: Any) -> None:
        if isinstance(n, int) and (self._week_n is None or n > self._week_n):
            self._week_n = n

    async def _on_board(self, d: dict[str, Any]) -> None:
        """Posição no Top Catch, com a mesma regra da tela do jogo (`tcPosicaoCom`)."""
        n = self._week_n
        if d.get("week_start") != self._week or not n:
            return
        rows = [r for r in d.get("rows") or [] if isinstance(r, dict)]
        me, level = self.ctx.nick, self._level
        i_me = next((i for i, r in enumerate(rows) if r.get("nick") == me), -1)
        if i_me >= 0 and _num(rows[i_me].get("valor")) == n:
            above = rows[:i_me]
        else:
            above = [
                r
                for r in rows
                if r.get("nick") != me
                and (
                    _num(r.get("valor")) > n
                    or (_num(r.get("valor")) == n and _num(r.get("level")) >= level)
                )
            ]
        pos = len(above) + 1
        inside = pos <= PRIZED
        cutoff = _num(rows[-1].get("valor")) if rows else None
        missing = 0 if inside or cutoff is None else max(1, cutoff - n + 1)
        key = (pos if inside else None, n, cutoff)
        if key == self._position_key:
            return
        self._position_key = key
        last = above[-1] if above else None
        await self.ctx.actions.note(
            "rank.position",
            {
                "week_start": self._week,
                "species": n,
                "position": pos if inside else None,
                "inside": inside,
                "list_size": len(rows),
                "cutoff": cutoff,
                "missing": missing,
                "above": {"nick": last.get("nick"), "valor": _num(last.get("valor"))}
                if last
                else None,
            },
        )

    # --- eventos ------------------------------------------------------------

    async def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer
            self._timer = None

    async def on_event(self, event: Event) -> None:
        async with self._lock:
            await self._handle(event)

    async def _handle(self, event: Event) -> None:
        if not self._ready:
            if event.type == "state.snapshot":
                await self._try_boot()
            return
        d = event.data
        t = event.type
        if t == "session.connected":
            await self._request_week()
            await self._request_board()
        elif t == "game.error":
            if self._pending is not None:
                await self._switch_failed(str(d.get("key") or "erro"))
        elif t == "kill":
            await self._on_kill(d)
        elif t == "item.consumed" and self._window:
            self._window[-1][1] += (d.get("qty") or 0) * (d.get("unit_price") or 0)
        elif t == "rank.board":
            await self._on_board(d)
        elif t == "rank.week":
            await self._on_week(d)
        elif t == "rank.catch":
            await self._on_catch(d)
        elif t == "auto.catch_until_capture_off":
            self._catch_until_off_at = self.now().isoformat()
        elif t == "hunt.changed":
            self._current = d.get("slug") or self._current
            if self._pending is not None and self._current == self._pending[0]:
                self._pending = None
                self._fails = 0
            if self._acting and self._target and self._current == self._target.slug:
                self._target_since = self.now()
        elif t in ("state.snapshot", "state.patch"):
            if self.ctx.state.hunt_slug and t == "state.snapshot":
                self._current = self.ctx.state.hunt_slug
            level = self.ctx.state.level or 0
            if level > self._level:
                self._level = level
                await self._replan("level_up")
        if self._acting and t in ("kill", "state.patch", "state.snapshot", "hunt.changed"):
            await self._pump()

    async def _on_kill(self, d: dict[str, Any]) -> None:
        if week_start(self.now()) > self._week:
            self._week_n = None
            await self._rollover(week_start(self.now()), set(), "week_rollover")
            await self._request_week()
            return
        self._pace.add_kill(d.get("hunt_slug") or self._current, self.now(), d.get("active_level"))
        self._window.append([(d.get("gold") or 0) + (d.get("gold_autosell") or 0), 0.0])
        self._kills_since_ball += 1
        ball = self._ball_choice()
        if ball != self._ball and self._kills_since_ball >= self.cfg.window_kills:
            self._ball = ball
            self._kills_since_ball = 0
            await self._replan("ball_changed")
            return
        tgt, since = self._target, self._target_since
        if tgt is not None and since is not None:
            limit_h = max(self.cfg.max_hunt_factor * tgt.hours, self.cfg.min_hunt_minutes / 60)
            if self.now() - since > timedelta(hours=limit_h):
                # vai para o fim da fila; com alvo zerado, o tempo recomeça mesmo se
                # ela continuar sendo a única da fila
                self._skipped = [s for s in self._skipped if s != tgt.species_id]
                self._skipped.append(tgt.species_id)
                self._target = None
                await self._replan("timeout")
                return
        tgt = self._target
        if tgt is not None and self._current == tgt.slug:
            kph = self._pace.measured(tgt.slug)
            if kph is not None and abs(kph - tgt.kills_per_hour) > RATE_DRIFT * tgt.kills_per_hour:
                await self._replan("rate_measured")

    async def _on_week(self, d: dict[str, Any]) -> None:
        ws = d.get("week_start")
        if not isinstance(ws, str) or ws < self._week:
            return
        species = _species_keys(d.get("species"))
        if ws > self._week:
            self._week_n = None
            self._note_n(d.get("week_species"))
            await self._rollover(ws, species, "week")
            return
        self._note_n(d.get("week_species"))
        self._scored = species
        await self._replan("week")

    async def _on_catch(self, d: dict[str, Any]) -> None:
        ws, sp = d.get("week_start"), d.get("species_id")
        scores = d.get("scores") is True and isinstance(sp, int)
        if isinstance(ws, str) and ws > self._week:
            self._week_n = None
            self._note_n(d.get("week_species"))
            await self._rollover(ws, {sp} if scores else set(), "week_rollover")  # type: ignore[arg-type]
            await self._request_board()
            return
        if not scores or (isinstance(ws, str) and ws != self._week) or sp in self._scored:
            return
        self._note_n(d.get("week_species"))
        self._scored.add(sp)  # type: ignore[arg-type]
        await self._request_board()
        if self._target is not None and sp == self._target.species_id:
            await self._replan("captured")
        elif any(q.species_id == sp for q in self._queue):
            await self._replan("captured_other")

    async def _rollover(self, week: str, scored: set[int], reason: str) -> None:
        self._week = week
        self._scored = scored
        self._skipped = []
        await self._replan(reason)

    # --- bola ---------------------------------------------------------------

    def _price(self, ball_id: int) -> int | None:
        info = self.ctx.catalog.balls.get(ball_id) if self.ctx.catalog else None
        if info is not None and info.price is not None:
            return info.price
        ball = BALLS.get(ball_id)
        return ball.price if ball else None

    def _ball_choice(self) -> int:
        balls = self.cfg.rank_balls
        if self.cfg.rank_ball_rule == "se_paga" and len(self._window) >= self.cfg.min_kills:
            net = sum(g - c for g, c in self._window) / len(self._window)
            for b in balls:
                price = self._price(b)
                if price is not None and price <= net:
                    return b
            priced = [b for b in balls if self._price(b) is not None]
            return min(priced, key=lambda b: self._price(b) or 0) if priced else balls[0]
        stock = self.ctx.state.balls or {}
        return next((b for b in balls if int(stock.get(str(b), 0)) > 0), balls[0])

    # --- plano --------------------------------------------------------------

    async def _replan(self, reason: str) -> None:
        cat = self.ctx.catalog
        if self._ball is None:
            self._ball = self._ball_choice()
        ball = self._ball
        rates = rates_for(
            {s: h.level for s, h in cat.hunts.items()},
            self._pace,
            self._default_kph,
            self.ctx.state.active_level,
        )
        measured = {s: r for s, (r, src) in rates.items() if src == "measured"}
        estimated = {s: r for s, (r, src) in rates.items() if src in ("level", "near_level")}
        queue = plan_queue(
            cat,
            self.ctx.species,
            self._level,
            self._scored,
            ball,
            measured,
            self._default_kph,
            observed_chances(self._attempts, cat, ball),
            estimated,
        )
        skipped = [q for sid in self._skipped for q in queue if q.species_id == sid]
        queue = [q for q in queue if q.species_id not in self._skipped] + skipped
        self._queue = queue

        target = queue[0] if queue else None
        here = next((q for q in queue if q.slug == self._current), None)
        if (
            target is not None
            and here is not None
            and here is not target
            and here.species_id not in self._skipped
            and target.hours > here.hours * (1 - HYSTERESIS)
        ):
            target = here

        prev = self._target
        if target is None or prev is None or target.slug != prev.slug:
            self._sent.clear()  # alvo novo: as ações podem ser repetidas
            self._fails = 0
            self._retry_at = None
            if target is None:
                self._target_since = None
            elif not self._acting or self._current == target.slug:
                self._target_since = self.now()
            else:
                self._target_since = None
        self._target = target
        await self.ctx.actions.note("rank.plan", self._plan_data(reason))
        await self._act(reason)

    def _plan_data(self, reason: str) -> dict[str, Any]:
        target, queue = self._target, self._queue
        data: dict[str, Any] = {
            "reason": reason,
            "dry_run": self.cfg.dry_run,
            "week_start": self._week,
            "scored": len(self._scored),
            "trainer_level": self._level,
            "ball_id": self._ball,
            "current_hunt": self._current,
            "target": asdict(target) if target else None,
            "queue_len": len(queue),
            "queue": [asdict(q) for q in queue[: self.cfg.queue_preview]],
            "skipped": list(self._skipped),
            "degraded": list(self._degraded),
        }
        if self._catch_until_off_at:
            data["catch_until_off_at"] = self._catch_until_off_at
        return data

    def _desired_automation(self) -> dict[str, Any] | None:
        auto = self.ctx.state.automation
        if auto is None or self._ball is None:
            return None
        ids = [b for b in auto.get("ballIds") or [] if b != self._ball]
        return {
            **auto,
            "ballIds": [self._ball, *ids],
            "autoBallSemParar": False,
            "autoBallAteCapturar": True,
        }

    async def _act(self, reason: str) -> None:
        target = self._target
        if self._acting:
            await self._set_mode(target)
            self._want_slug = target.slug if target else self.cfg.fallback_hunt
            await self._pump()
            return
        if target is None:
            return
        if self._current != target.slug:
            await self._do(HuntSelect(slug=target.slug), reason)
        want = self._desired_automation()
        if want is not None and want != self.ctx.state.automation:
            await self._do(AutoSet(automation=want), reason)

    async def _do(self, action: ActionSpec, reason: str) -> None:
        """Ensaio (dry_run, ou o restock em outro foco): grava o que faria."""
        inp = action.model_dump(mode="json")
        if self._sent.get(action.name) == inp:
            return
        self._sent[action.name] = inp
        await self.ctx.actions.note(
            "rank.would", {"action": action.name, "input": inp, "reason": reason}
        )

    # --- passo 5: agindo de verdade -----------------------------------------

    async def _set_mode(self, target: QueueItem | None) -> None:
        """Avisa o restock (focus "rank") de quem cuida das flags de bola."""
        if target is not None:
            mode: dict[str, Any] = {"mode": "active", "ball_id": self._ball}
        else:
            mode = {"mode": "fallback", "reason": "queue_empty"}
        if mode != self._mode:
            self._mode = mode
            await self.ctx.actions.note("rank.mode", mode)

    async def _pump(self) -> None:
        """Confere a troca pendente, manda o hunt.select quando pode e religa o auto.set."""
        now = self.now()
        if self._pending is not None:
            slug, sent_at = self._pending
            if self._current == slug:
                self._pending = None
                self._fails = 0
            elif now - sent_at > timedelta(seconds=self.cfg.switch_confirm_s):
                await self._switch_failed("timeout")
                return
        if self._pending is None:
            await self._maybe_switch(now)
        if self._target is not None:
            await self._sync_automation(now)

    async def _maybe_switch(self, now: datetime) -> None:
        slug = self._want_slug
        if slug is None or slug == self._current:
            return
        if self._retry_at is not None and now < self._retry_at:
            return
        hour_ago = now - timedelta(hours=1)
        while self._switches and self._switches[0] <= hour_ago:
            self._switches.popleft()
        if len(self._switches) >= self.cfg.max_switches_per_hour:
            if not self._capped:
                self._capped = True
                await self.ctx.actions.note("rank.plan", self._plan_data("switch_cap"))
            return
        st = self.ctx.state
        locks = [t for t in (st.combat_free_at, st.switch_free_at) if t is not None]
        free_at = max(locks) + timedelta(seconds=self.cfg.switch_margin_s) if locks else None
        if free_at is not None and st.server_now(now) < free_at:
            # trava de combate ou trocaLivreEm: tenta de novo quando acabar
            self._schedule(now + (free_at - st.server_now(now)))
            return
        try:
            await self.ctx.actions.submit(HuntSelect(slug=slug), source=self.name)
        except ActionBlocked as exc:
            wait = exc.wait_s if exc.wait_s is not None else self.cfg.switch_retry_s
            self._retry_at = now + timedelta(seconds=wait)
            return
        self._pending = (slug, now)
        self._switches.append(now)
        self._capped = False

    def _schedule(self, at: datetime) -> None:
        """Acorda o plugin em `at` (relógio local) para tentar a troca de novo."""
        if self._timer is not None and not self._timer.done():
            if self._timer_at is not None and self._timer_at <= at:
                return  # já vai acordar antes
            self._timer.cancel()
        self._timer_at = at
        delay = max(0.0, (at - self.now()).total_seconds())
        self._timer = asyncio.get_running_loop().create_task(self._wake(delay))

    async def _wake(self, delay: float) -> None:
        await self.sleep(delay)
        async with self._lock:
            self._timer = None
            self._timer_at = None
            if self._acting:
                await self._pump()
            due = self._board_due
            if due is not None:
                if self.now() >= due:
                    self._board_due = None
                    await self._request_board()
                else:
                    self._schedule(due)

    async def _switch_failed(self, reason: str) -> None:
        assert self._pending is not None
        slug = self._pending[0]
        self._pending = None
        self._retry_at = self.now() + timedelta(seconds=self.cfg.switch_retry_s)
        await self.ctx.actions.note(
            "rank.failed", {"action": "hunt.select", "slug": slug, "reason": reason}
        )
        tgt = self._target
        if tgt is None or slug != tgt.slug:
            return
        self._fails += 1
        if self._fails >= SWITCH_FAILS_TO_SKIP:
            self._skipped = [s for s in self._skipped if s != tgt.species_id]
            self._skipped.append(tgt.species_id)
            self._target = None
            await self._replan("switch_failed")

    async def _sync_automation(self, now: datetime) -> None:
        """D-J: com alvo, o Lançar até Capturar fica ligado (o servidor desliga na captura)."""
        want = self._desired_automation()
        if want is None:
            return
        if want == self.ctx.state.automation:
            self._auto_sent = self._auto_sent_at = None  # refletiu: a próxima queda religa já
            return
        if (
            want == self._auto_sent
            and self._auto_sent_at is not None
            and now < self._auto_sent_at + timedelta(seconds=self.cfg.retry_after_s)
        ):
            return  # ainda esperando o estado refletir o último auto.set
        try:
            await self.ctx.actions.submit(AutoSet(automation=want), source=self.name)
        except ActionBlocked as exc:
            # rate limit: tenta de novo quando ele deixar; outro motivo: depois de retry_after_s
            wait = exc.wait_s if exc.wait_s is not None else self.cfg.retry_after_s
            self._auto_sent = want
            self._auto_sent_at = now + timedelta(seconds=wait - self.cfg.retry_after_s)
            return
        self._auto_sent, self._auto_sent_at = want, now


def _num(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _species_keys(species: Any) -> set[int]:
    out: set[int] = set()
    for k in species or {}:
        try:
            out.add(int(k))
        except (TypeError, ValueError):
            continue
    return out
