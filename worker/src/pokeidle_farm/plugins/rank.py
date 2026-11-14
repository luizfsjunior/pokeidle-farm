"""Plugin rank: escolhe a hunt do foco "rank semanal" (fase 3b, passo 4).

Ver docs/design/fase-3b-plugin-rank.md. Resumo:
- monta a fila de hunts por tempo até a captura (`rank_queue.plan_queue`) com as
  espécies que já pontuaram na semana, o ritmo medido por hunt e a chance observada;
- grava um `rank.plan` a cada decisão e replaneja na captura, na virada da semana, ao
  subir de nível, ao trocar de bola e quando estoura o tempo na hunt alvo;
- com `dry_run` (padrão) não manda `hunt.select` nem `auto.set`: grava `rank.would`.
  O `topcatch.pedir` (só leitura) vai sempre, respeitando o `ACTION_MODE`.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, ActionSpec, AutoSet, HuntSelect, TopCatchRequest
from ..catalog import BALLS
from ..events import Event
from ..rank_queue import QueueItem, observed_chances, plan_queue
from .base import Plugin, PluginContext

BRT = timedelta(hours=-3)  # Brasília, sem horário de verão
HYSTERESIS = 0.10  # só troca de hunt se a nova for pelo menos 10% mais rápida (D-C)
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
    min_active_minutes: float = Field(30.0, ge=0)
    default_kills_per_hour: float = Field(300.0, gt=0)
    queue_preview: int = Field(10, ge=0)


class RankPlugin(Plugin):
    name: ClassVar[str] = "rank"
    description: ClassVar[str] = "Foco rank semanal: fila de hunts até a captura (ensaio)"
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
    }

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)

    # --- subida -------------------------------------------------------------

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: RankConfig = ctx.config  # type: ignore[assignment]
        self._ready = False
        self._week = week_start(self.now())
        self._scored: set[int] = set()
        self._skipped: list[int] = []
        self._kph: dict[str, float] = {}
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
        await self._try_boot()

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
            for at, data in catches:
                if (
                    data.get("scores") is True
                    and data.get("week_start") == self._week
                    and isinstance(data.get("species_id"), int)
                    and (base_at is None or at >= base_at)
                ):
                    self._scored.add(data["species_id"])
        try:
            stats = await store.rank_hunt_stats(
                acc, self.now() - timedelta(days=self.cfg.history_days)
            )
        except Exception as exc:
            self.ctx.log.warning("rank: não consegui ler o ritmo por hunt (%s)", exc)
            self._degraded.append("stats")
            return
        total_kills = sum(s.kills for s in stats)
        total_min = sum(s.active_minutes for s in stats)
        if total_min > 0 and total_kills > 0:
            self._default_kph = total_kills / total_min * 60
        for s in stats:
            if s.active_minutes >= self.cfg.min_active_minutes and s.kills > 0 and s.active_minutes:
                self._kph[s.hunt_slug] = s.kills / s.active_minutes * 60
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

    async def _request_week(self) -> None:
        try:
            await self.ctx.actions.submit(TopCatchRequest(), source=self.name)
        except ActionBlocked:
            pass  # o gateway já registrou o motivo

    # --- eventos ------------------------------------------------------------

    async def on_event(self, event: Event) -> None:
        if not self._ready:
            if event.type == "state.snapshot":
                await self._try_boot()
            return
        d = event.data
        t = event.type
        if t == "session.connected":
            await self._request_week()
        elif t == "kill":
            await self._on_kill(d)
        elif t == "item.consumed" and self._window:
            self._window[-1][1] += (d.get("qty") or 0) * (d.get("unit_price") or 0)
        elif t == "rank.week":
            await self._on_week(d)
        elif t == "rank.catch":
            await self._on_catch(d)
        elif t == "auto.catch_until_capture_off":
            self._catch_until_off_at = self.now().isoformat()
        elif t == "hunt.changed":
            self._current = d.get("slug") or self._current
            if not self.cfg.dry_run and self._target and self._current == self._target.slug:
                self._target_since = self.now()
        elif t in ("state.snapshot", "state.patch"):
            if self.ctx.state.hunt_slug and t == "state.snapshot":
                self._current = self.ctx.state.hunt_slug
            level = self.ctx.state.level or 0
            if level > self._level:
                self._level = level
                await self._replan("level_up")

    async def _on_kill(self, d: dict[str, Any]) -> None:
        if week_start(self.now()) > self._week:
            await self._rollover(week_start(self.now()), set(), "week_rollover")
            await self._request_week()
            return
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

    async def _on_week(self, d: dict[str, Any]) -> None:
        ws = d.get("week_start")
        if not isinstance(ws, str) or ws < self._week:
            return
        species = _species_keys(d.get("species"))
        if ws > self._week:
            await self._rollover(ws, species, "week")
            return
        self._scored = species
        await self._replan("week")

    async def _on_catch(self, d: dict[str, Any]) -> None:
        ws, sp = d.get("week_start"), d.get("species_id")
        scores = d.get("scores") is True and isinstance(sp, int)
        if isinstance(ws, str) and ws > self._week:
            await self._rollover(ws, {sp} if scores else set(), "week_rollover")  # type: ignore[arg-type]
            return
        if not scores or (isinstance(ws, str) and ws != self._week) or sp in self._scored:
            return
        self._scored.add(sp)  # type: ignore[arg-type]
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
        queue = plan_queue(
            cat,
            self.ctx.species,
            self._level,
            self._scored,
            ball,
            self._kph,
            self._default_kph,
            observed_chances(self._attempts, cat, ball),
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
            if target is None:
                self._target_since = None
            elif self.cfg.dry_run or self._current == target.slug:
                self._target_since = self.now()
            else:
                self._target_since = None
        self._target = target

        data: dict[str, Any] = {
            "reason": reason,
            "dry_run": self.cfg.dry_run,
            "week_start": self._week,
            "scored": len(self._scored),
            "trainer_level": self._level,
            "ball_id": ball,
            "current_hunt": self._current,
            "target": asdict(target) if target else None,
            "queue_len": len(queue),
            "queue": [asdict(q) for q in queue[: self.cfg.queue_preview]],
            "skipped": list(self._skipped),
            "degraded": list(self._degraded),
        }
        if self._catch_until_off_at:
            data["catch_until_off_at"] = self._catch_until_off_at
        await self.ctx.actions.note("rank.plan", data)
        await self._act(reason)

    async def _act(self, reason: str) -> None:
        target = self._target
        if target is None:
            return
        if self._current != target.slug:
            await self._do(HuntSelect(slug=target.slug), reason)
        auto = self.ctx.state.automation
        if auto is not None and self._ball is not None:
            ids = [b for b in auto.get("ballIds") or [] if b != self._ball]
            want = {
                **auto,
                "ballIds": [self._ball, *ids],
                "autoBallSemParar": False,
                "autoBallAteCapturar": True,
            }
            if want != auto:
                await self._do(AutoSet(automation=want), reason)

    async def _do(self, action: ActionSpec, reason: str) -> None:
        inp = action.model_dump(mode="json")
        if self._sent.get(action.name) == inp:
            return
        self._sent[action.name] = inp
        if self.cfg.dry_run:
            await self.ctx.actions.note(
                "rank.would", {"action": action.name, "input": inp, "reason": reason}
            )
            return
        try:
            await self.ctx.actions.submit(action, source=self.name)
        except ActionBlocked as exc:
            if exc.reason.startswith(("rate_limit", "not_connected")):
                self._sent.pop(action.name, None)  # tenta de novo no próximo plano


def _species_keys(species: Any) -> set[int]:
    out: set[int] = set()
    for k in species or {}:
        try:
            out.add(int(k))
        except (TypeError, ValueError):
            continue
    return out
