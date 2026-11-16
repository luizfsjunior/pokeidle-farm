"""Plugin gems: foco "gemas", fica na hunt que mais rende pedras de evolução em gemas.

Ver docs/design/foco-gemas-e-ritmo.md. Resumo:
- a cada `interval_min`, na subida, ao subir de nível e quando chegam preços novos, ordena as
  hunts alcançáveis por gemas/h (`gems_model.rank_options`) com o ritmo de cada hunt
  (`PaceBook`: medido, ou a mediana do mesmo nível, ou o padrão) e o teto de liquidez;
- troca de hunt só se a melhor render `hysteresis` a mais que a atual (`HuntSwitcher`);
- grava `gems.plan` a cada decisão; com `dry_run` (padrão) grava `gems.would` em vez de trocar;
- as bolas ficam com o `restock` em `gold_xp_drop` (o `focus.set` "gems" cuida disso);
- com várias contas no worker, cada uma desconta da liquidez o que as outras já tiram.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..events import Event
from ..gems_model import (
    STONE_BY_TYPE,
    STONE_CHANCE_BY_POSITION,
    StonePrice,
    option_dict,
    rank_options,
)
from ..hunt_switch import HuntSwitcher
from ..model.predict import ModelRates, season_adjust
from ..pace import PaceBook, rates_for
from ..progress import Progress
from ..xp_model import xp_option_dict, xp_options
from .base import Plugin, PluginContext


class GemsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    # o que maximizar: gemas das pedras (foco gemas) ou XP por hora (foco XP, docs/design/foco-xp.md)
    objective: Literal["gems", "xp"] = "gems"
    # ritmo das hunts não medidas pelo simulador de combate (docs/design/simulador-1-combate.md)
    use_model: bool = True
    # foco XP: plano até o marco (progress.plan) e evolução automática (docs/design/simulador-2-progressao.md)
    plan_goal: int = Field(150, ge=2)
    plan_every_min: float = Field(60.0, ge=5)
    auto_evolve: bool = True
    interval_min: float = Field(15.0, ge=1)
    max_market_share: float = Field(0.10, gt=0, le=1)
    hysteresis: float = Field(0.15, ge=0)
    min_active_minutes: float = Field(5.0, ge=0)
    history_days: int = Field(14, ge=1)
    default_kills_per_hour: float = Field(300.0, gt=0)
    preview: int = Field(5, ge=0)
    switch_margin_s: float = Field(0.5, ge=0)
    switch_confirm_s: float = Field(15.0, gt=0)
    switch_retry_s: float = Field(60.0, ge=0)
    max_switches_per_hour: int = Field(6, ge=1)


class GemsPlugin(Plugin):
    name: ClassVar[str] = "gems"
    description: ClassVar[str] = "Foco gemas: fica na hunt que mais rende pedras em gemas"
    config_model: ClassVar[type[BaseModel]] = GemsConfig
    subscribes: ClassVar[set[str]] = {
        "kill",
        "hunt.changed",
        "game.error",
        "state.snapshot",
        "state.patch",
        "market.prices",
    }

    # pedra -> unidades/semana que cada conta tira (para dividir a liquidez entre as contas)
    _claims: ClassVar[dict[UUID, dict[str, float]]] = {}

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: GemsConfig = ctx.config  # type: ignore[assignment]
        self._lock = asyncio.Lock()
        self._level = ctx.state.level or 0
        self._pace = PaceBook(self.cfg.min_active_minutes)
        self._xp: dict[str, tuple[float, float]] = {}  # slug -> (XP, abates), banco + sessão
        self._default_kph = self.cfg.default_kills_per_hour
        self._prices: dict[str, StonePrice] = {}
        self._chances = STONE_CHANCE_BY_POSITION
        self._by_type = STONE_BY_TYPE
        self._degraded: list[str] = []
        self._last_plan_at: datetime | None = None
        self._choice: str | None = None
        self._would: str | None = None
        self._acting = not self.cfg.dry_run
        self.switch = HuntSwitcher(
            ctx,
            source=self.name,
            now=lambda: self.now(),
            sleep=lambda s: self.sleep(s),
            locked=self._locked,
            margin_s=self.cfg.switch_margin_s,
            confirm_s=self.cfg.switch_confirm_s,
            retry_s=self.cfg.switch_retry_s,
            max_per_hour=self.cfg.max_switches_per_hour,
        )
        self.progress = Progress(
            ctx,
            source=self.name,
            now=lambda: self.now(),
            goal=self.cfg.plan_goal,
            plan_every_min=self.cfg.plan_every_min,
        )
        if self._acting:
            await self._check_rank()
        await self._load()
        await self._plan("start")
        if self.cfg.objective == "xp":
            self.progress.maybe_plan("start")

    async def stop(self) -> None:
        await self.switch.stop()
        await self.progress.stop()
        type(self)._claims.pop(self.ctx.account_id, None)

    async def _locked(self, fn: Callable[[], Awaitable[None]]) -> None:
        async with self._lock:
            await fn()

    async def _check_rank(self) -> None:
        """Com o rank agindo na mesma conta, os dois brigariam pelo hunt.select."""
        try:
            configs = await self.ctx.store.plugin_configs(self.ctx.account_id)
        except Exception:
            configs = {}
        enabled, cfg = configs.get("rank", (False, {}))
        if enabled and (cfg or {}).get("dry_run") is False:
            self._acting = False
            self._degraded.append("rank_acting")

    async def _load(self) -> None:
        store, acc = self.ctx.store, self.ctx.account_id
        try:
            stats = await store.rank_hunt_stats(
                acc, self.now() - timedelta(days=self.cfg.history_days)
            )
        except Exception as exc:
            self.ctx.log.warning("gems: não consegui ler o ritmo por hunt (%s)", exc)
            self._degraded.append("stats")
            stats = []
        hunts = self.ctx.catalog.hunts if self.ctx.catalog else {}
        stats = [s for s in stats if s.hunt_slug in hunts]
        for s in stats:
            self._pace.load(s.hunt_slug, s.kills, s.active_minutes, s.avg_active_level)
            self._xp[s.hunt_slug] = (s.xp, s.kills)
        total_k, total_m = sum(s.kills for s in stats), sum(s.active_minutes for s in stats)
        if total_k > 0 and total_m > 0:
            self._default_kph = total_k / total_m * 60
        await self._load_prices()
        try:
            loot = await store.get_catalog("loot_stones")
        except Exception:
            loot = None
        if loot is not None and isinstance(loot[1], dict):
            ch = loot[1].get("chance_by_position")
            if isinstance(ch, list) and len(ch) == 3:
                self._chances = (float(ch[0]), float(ch[1]), float(ch[2]))
            bt = loot[1].get("stone_by_type")
            if isinstance(bt, dict) and bt:
                self._by_type = {str(k).upper(): str(v) for k, v in bt.items()}

    async def _load_prices(self) -> None:
        try:
            rows = await self.ctx.store.latest_item_prices()
        except Exception as exc:
            self.ctx.log.warning("gems: não consegui ler os preços (%s)", exc)
            if "prices" not in self._degraded:
                self._degraded.append("prices")
            return
        self._prices = {
            name: StonePrice(
                gems=float(p["orb"]),
                sold_week=float(p.get("orb_units_week") or 0),
                min_ask=float(p["orb_min_ask"]) if p.get("orb_min_ask") is not None else None,
            )
            for name, p in rows.items()
            if p.get("orb") is not None
        }

    # --- eventos ------------------------------------------------------------

    async def on_event(self, event: Event) -> None:
        async with self._lock:
            await self._handle(event)

    async def _handle(self, event: Event) -> None:
        d, t = event.data, event.type
        if t == "kill":
            slug = d.get("hunt_slug") or self.switch.current
            if not self._season_hit(slug, d):  # o ritmo medido é o de dias normais
                self._pace.add_kill(slug, self.now(), d.get("active_level"))
            if slug:
                xp, kills = self._xp.get(slug, (0.0, 0.0))
                self._xp[slug] = (xp + float(d.get("xp") or 0), kills + 1)
            due = self._last_plan_at is None or self.now() - self._last_plan_at >= timedelta(
                minutes=self.cfg.interval_min
            )
            if self.cfg.objective == "xp":
                if self._acting and self.cfg.auto_evolve:
                    await self.progress.maybe_evolve()
                self.progress.maybe_plan("interval")
            if due:
                await self._plan("interval")
            else:
                await self.switch.pump()
        elif t == "hunt.changed":
            await self.switch.on_hunt_changed(d.get("slug"))
        elif t == "game.error":
            await self.switch.on_error(str(d.get("key") or "erro"))
        elif t == "market.prices":
            await self._load_prices()
            await self._plan("prices")
        elif t in ("state.snapshot", "state.patch"):
            if t == "state.snapshot" and self.ctx.state.hunt_slug:
                self.switch.current = self.ctx.state.hunt_slug
            level = self.ctx.state.level or 0
            prof = self.ctx.state.active_pokemon or {}
            species_now = prof.get("speciesId")
            evolved = (
                getattr(self, "_species_now", None) is not None and species_now != self._species_now
            )
            self._species_now = species_now
            if level > self._level:
                self._level = level
                await self._plan("level_up")
                if self.cfg.objective == "xp":
                    self.progress.maybe_plan("level_up")
            elif evolved and self.cfg.objective == "xp":
                await self._plan("evolved")
                self.progress.maybe_plan("evolved")

    # --- plano --------------------------------------------------------------

    def _others_taken(self) -> dict[str, float]:
        taken: dict[str, float] = {}
        for acc, claims in type(self)._claims.items():
            if acc == self.ctx.account_id:
                continue
            for stone, units in claims.items():
                taken[stone] = taken.get(stone, 0.0) + units
        return taken

    async def _plan(self, reason: str) -> None:
        self._last_plan_at = self.now()
        cat, species = self.ctx.catalog, self.ctx.species
        if cat is None or species is None or not cat.hunts:
            await self.ctx.actions.note("gems.plan", {"reason": "sem_catalogo", "target": None})
            return
        season = self.ctx.state.season_type()
        seasonal = await asyncio.to_thread(self._model_rates, cat, species, season)
        rate = rates_for(
            {s: h.level for s, h in cat.hunts.items()},
            self._pace,
            self._default_kph,
            self.ctx.state.active_level,
            seasonal,
        )
        if season and seasonal:  # o ritmo medido é de dias normais: corrige pelo simulador
            normal = await asyncio.to_thread(self._model_rates, cat, species, None)
            rate = season_adjust(rate, normal, seasonal)
        if self.cfg.objective == "xp":
            await self._plan_xp(reason, cat, rate)
            return
        options = rank_options(
            cat,
            species,
            self._level,
            rate,
            self._prices,
            max_share=self.cfg.max_market_share,
            taken_week=self._others_taken(),
            chances=self._chances,
            by_type=self._by_type,
        )
        best = options[0] if options and options[0].capped_gems_per_hour > 0 else None
        current = self.switch.current
        here = next((o for o in options if o.slug == current), None)
        target = best
        if (
            best is not None
            and here is not None
            and here is not best
            and best.capped_gems_per_hour <= here.capped_gems_per_hour * (1 + self.cfg.hysteresis)
        ):
            target = here
        if target is not None:
            type(self)._claims[self.ctx.account_id] = {
                s.name: s.counted_week for s in target.stones if s.counted_week > 0
            }
        data: dict[str, Any] = {
            "reason": reason,
            "dry_run": self.cfg.dry_run,
            "acting": self._acting,
            "trainer_level": self._level,
            "current_hunt": current,
            "target": option_dict(target) if target else None,
            "here": option_dict(here) if here and here is not target else None,
            "options": [option_dict(o) for o in options[: self.cfg.preview]],
            "prices": len(self._prices),
            "degraded": list(self._degraded),
            "month_gems_24h": round(target.capped_gems_per_hour * 24 * 30, 1) if target else 0,
        }
        await self.ctx.actions.note("gems.plan", data)
        await self._go(target.slug if target else None, current, reason)

    def _season_hit(self, slug: str | None, kill: dict[str, Any]) -> bool:
        """O tipo do dia sazonal no abate é do ativo ou da espécie da hunt (como o banco calcula)."""
        season = str(kill.get("season") or "").upper()
        species = getattr(self.ctx.species, "species", None) or {}
        if not season or not species:
            return False
        ids = [kill.get("active_species_id")]
        hunt = self.ctx.catalog.hunts.get(slug) if self.ctx.catalog and slug else None
        if hunt is not None:
            ids.append(hunt.species_id)
        for sid in ids:
            sp = species.get(sid)
            if sp is not None and season in {str(t or "").upper() for t in (sp.type1, sp.type2)}:
                return True
        return False

    def _model_rates(self, cat: Any, species: Any, season: str | None = None) -> dict[str, float]:
        """Previsão do simulador de combate para o ativo (vazia se faltar dado)."""
        if not self.cfg.use_model:
            return {}
        if not hasattr(self, "_model"):
            self._model = ModelRates()
        try:
            return self._model.rates(
                {s: (h.level, h.species_id) for s, h in cat.hunts.items()},
                self.ctx.state.active_pokemon,
                getattr(species, "raw", {}) or {},
                getattr(cat, "rules", {}) or {},
                max_level=self._level or None,
                season=season,
            )
        except Exception:  # o modelo nunca derruba o plano: cai no ritmo por nível
            self.ctx.log.exception("simulador de combate falhou")
            return {}

    async def _plan_xp(self, reason: str, cat: Any, rate: dict[str, tuple[float, str]]) -> None:
        """Foco XP: a hunt de maior XP/h projetada (ritmo pelo nível do ativo × XP por abate)."""
        options = xp_options(cat, self._level, rate, self._xp)
        best = options[0] if options and options[0].xp_per_hour > 0 else None
        current = self.switch.current
        here = next((o for o in options if o.slug == current), None)
        target = best
        if (
            best is not None
            and here is not None
            and here is not best
            and best.xp_per_hour <= here.xp_per_hour * (1 + self.cfg.hysteresis)
        ):
            target = here
        await self.ctx.actions.note(
            "gems.plan",
            {
                "objective": "xp",
                "reason": reason,
                "dry_run": self.cfg.dry_run,
                "acting": self._acting,
                "trainer_level": self._level,
                "active_level": self.ctx.state.active_level,
                "current_hunt": current,
                "target": xp_option_dict(target) if target else None,
                "here": xp_option_dict(here) if here and here is not target else None,
                "options": [xp_option_dict(o) for o in options[: self.cfg.preview]],
                "degraded": list(self._degraded),
            },
        )
        await self._go(target.slug if target else None, current, reason)

    async def _go(self, slug: str | None, current: str | None, reason: str) -> None:
        if slug is None or slug == current:
            await self.switch.go(slug)
            return
        if self._acting:
            await self.switch.go(slug)
        elif slug != self._would:
            self._would = slug
            await self.ctx.actions.note(
                "gems.would", {"action": "hunt.select", "input": {"slug": slug}, "reason": reason}
            )


async def compute_potential(
    ctx: PluginContext, now: datetime, *, preview: int = 10, max_share: float = 0.10
) -> dict[str, Any] | None:
    """Melhores hunts em gemas/h para a conta, qualquer que seja o foco (`gems.potential`)."""
    cat, species = ctx.catalog, ctx.species
    if cat is None or species is None or not cat.hunts:
        return None
    pace = PaceBook(5.0)
    stats = await ctx.store.rank_hunt_stats(ctx.account_id, now - timedelta(days=14))
    stats = [st for st in stats if st.hunt_slug in cat.hunts]
    for st in stats:
        pace.load(st.hunt_slug, st.kills, st.active_minutes, st.avg_active_level)
    total_k, total_m = sum(st.kills for st in stats), sum(st.active_minutes for st in stats)
    default = total_k / total_m * 60 if total_k > 0 and total_m > 0 else 300.0
    raw = await ctx.store.latest_item_prices()
    prices = {
        name: StonePrice(
            gems=float(p["orb"]),
            sold_week=float(p.get("orb_units_week") or 0),
            min_ask=float(p["orb_min_ask"]) if p.get("orb_min_ask") is not None else None,
        )
        for name, p in raw.items()
        if p.get("orb") is not None
    }
    level = ctx.state.level or 0
    rate = rates_for(
        {sl: h.level for sl, h in cat.hunts.items()}, pace, default, ctx.state.active_level
    )
    options = rank_options(cat, species, level, rate, prices, max_share=max_share)
    return {
        "trainer_level": level,
        "prices": len(prices),
        "max_share": max_share,
        "options": [option_dict(o) for o in options[:preview]],
    }
