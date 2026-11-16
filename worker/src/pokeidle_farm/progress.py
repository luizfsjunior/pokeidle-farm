"""Plano até o marco e evolução automática (foco XP; docs/design/simulador-2-progressao.md).

Usado pelo plugin gems com `objective: "xp"`:
- `maybe_plan`: roda a camada 2 (`model/progression.plan_to`) numa thread, no máximo a cada
  `plan_every_min` (e sempre na subida e ao evoluir), e grava `progress.plan` (fases, horas, ETA);
- `maybe_evolve`: quando o ativo chega no nível de evoluir e a pedra do tipo está na bolsa, manda
  `pokemon.evoluir` (uma tentativa por pokémon e espécie a cada `evolve_retry_min`).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .actions import ActionBlocked, PokemonEvolve
from .gems_model import STONE_BY_TYPE
from .model.progression import Account, Bonus, HuntRef, plan_to
from .plugins.base import PluginContext


def bonuses_from_state(xp_bonus: dict[str, Any] | None) -> tuple[Bonus, ...]:
    """`estado.bonusXp.partes` ([{id, tr, ate}]) -> bônus do treinador com a expiração."""
    out = []
    for p in (xp_bonus or {}).get("partes") or []:
        if not isinstance(p, dict):
            continue
        mult = float(p.get("tr") or 1)
        ate = p.get("ate")
        until = datetime.fromtimestamp(ate / 1000, UTC) if isinstance(ate, int | float) else None
        if mult > 0 and mult != 1:
            out.append(Bonus(mult, until))
    return tuple(out)


def farm_pct_from_event(event: dict[str, Any] | None, now: datetime) -> float:
    if not isinstance(event, dict):
        return 0.0
    end = event.get("terminaEm")
    if isinstance(end, int | float) and datetime.fromtimestamp(end / 1000, UTC) <= now:
        return 0.0
    return float(event.get("farmPct") or 0)


class Progress:
    def __init__(
        self,
        ctx: PluginContext,
        *,
        source: str,
        now: Callable[[], datetime],
        goal: int = 150,
        plan_every_min: float = 60.0,
        evolve_retry_min: float = 10.0,
    ) -> None:
        self.ctx = ctx
        self.source = source
        self.now = now
        self.goal = goal
        self.plan_every = timedelta(minutes=plan_every_min)
        self.evolve_retry = timedelta(minutes=evolve_retry_min)
        self.last_plan_at: datetime | None = None
        self.task: asyncio.Task[None] | None = None
        self.evolve_tries: dict[tuple[Any, Any], datetime] = {}
        self._stone_names: dict[int, str] | None = None

    async def stones(self) -> dict[str, int]:
        """Pedras na bolsa por nome (o catálogo de pedras é lido uma vez)."""
        if self._stone_names is None:
            try:
                self._stone_names = await self.ctx.store.stone_items()
            except Exception:
                return {}
        out: dict[str, int] = {}
        for key, qty in (self.ctx.state.items or {}).items():
            name = self._stone_names.get(int(key)) if str(key).isdigit() else None
            if name and isinstance(qty, int):
                out[name] = out.get(name, 0) + qty
        return out

    # --- evolução -----------------------------------------------------------------

    async def maybe_evolve(self) -> None:
        prof = self.ctx.state.active_pokemon
        species = self.ctx.species
        if not prof or species is None:
            return
        sid, level, pid = prof.get("speciesId"), prof.get("level"), prof.get("id")
        raw = (getattr(species, "raw", {}) or {}).get(sid) or {}
        to, evo_lv = raw.get("evolvesToId"), int(raw.get("evolveLevel") or 0)
        if pid is None or not to or to == sid or not evo_lv or not isinstance(level, int):
            return
        if level < evo_lv:
            return
        stone = STONE_BY_TYPE.get(str(raw.get("type1") or "").upper())
        if not stone or (await self.stones()).get(stone, 0) < 1:
            return
        now = self.now()
        key = (pid, sid)
        last = self.evolve_tries.get(key)
        if last is not None and now - last < self.evolve_retry:
            return
        self.evolve_tries[key] = now
        try:
            await self.ctx.actions.submit(
                PokemonEvolve(pokemon_id=pid, target_id=int(to)), source=self.source
            )
        except ActionBlocked:
            return
        await self.ctx.actions.note(
            "progress.evolve",
            {"pokemon_id": pid, "from": sid, "to": int(to), "level": level, "stone": stone},
        )

    # --- plano ----------------------------------------------------------------------

    def maybe_plan(self, reason: str) -> None:
        now = self.now()
        if self.task is not None and not self.task.done():
            return
        forced = reason in ("start", "level_up", "evolved")
        if (
            not forced
            and self.last_plan_at is not None
            and now - self.last_plan_at < self.plan_every
        ):
            return
        self.task = asyncio.get_running_loop().create_task(self._run(reason))

    async def _run(self, reason: str) -> None:
        st, cat, species = self.ctx.state, self.ctx.catalog, self.ctx.species
        prof = st.active_pokemon
        missing = [
            name
            for name, ok in (
                ("catalog", cat is not None),
                ("species", species is not None),
                ("active", bool(prof)),
                ("level", st.level is not None),
                ("rules", bool(getattr(cat, "rules", None))),
            )
            if not ok
        ]
        if missing:  # tenta de novo no próximo abate (o intervalo só conta planos gravados)
            self.ctx.log.info("progress: sem plano ainda, falta %s", ", ".join(missing))
            return
        now = self.now()
        self.last_plan_at = now
        account = Account(
            trainer_level=st.level,
            trainer_xp=float(st.trainer_xp or 0),
            active=prof,
            active_xp=float(prof.get("xp") or 0),
            stones=await self.stones(),
            bonuses=bonuses_from_state(st.xp_bonus),
            farm_pct=farm_pct_from_event(st.xp_event, now),
        )
        hunts = [HuntRef(h.slug, h.level, h.species_id) for h in cat.hunts.values()]
        try:
            plan = await asyncio.to_thread(
                plan_to, self.goal, account, hunts, species.raw, cat.rules, now
            )
        except Exception:
            self.ctx.log.exception("progress: o plano falhou")
            return
        data = plan.as_dict(now)
        raw = species.raw
        for ph in data["phases"]:
            ph["species"] = (raw.get(ph["species_id"]) or {}).get("name")
        for ev in data["evolutions"]:
            ev["to_name"] = (raw.get(ev["to"]) or {}).get("name")
        await self.ctx.actions.note(
            "progress.plan",
            {
                "reason": reason,
                "trainer_level": st.level,
                "active_level": prof.get("level"),
                "active_species_id": prof.get("speciesId"),
                **data,
            },
        )

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
