"""Plugin watchdog (vigia): a conta não fica parada (docs/design/conta-v2.md, seção 5).

Sempre ligado. Resolve o que deixou a luizfsjunior_1 parada a noite de 18 para 19/11:

- **Pokécenter com a equipe caída.** O jogo leva a conta para o Pokécenter quando a equipe cai e
  não volta sozinho se faltarem itens (`autoHuntSemItens`). Com poção e revive na bolsa, a vigia
  pede `centro.curar`. Com a equipe já de pé, manda `hunt.select` da hunt de antes: o jogo nem
  sempre volta sozinho depois da cura (19/11: curada às 10:15, parada no centro até 11:00, com a
  vigia curando de novo a cada minuto).
- **O ativo trocado pela morte.** Na morte, o jogo põe no ativo o próximo da equipe que estiver de
  pé (um Magikarp nv 3 no lugar do Venusaur nv 397). Fora do Pokécenter, a vigia devolve o ativo
  de antes da morte, se ele estiver vivo. Só isso: não mexe num ativo que o usuário ou o
  `team_train` escolheu.
- **Mortes repetidas na mesma hunt.** Duas mortes em `deadly_window_s` viram o alerta
  `watchdog.dangerous_hunt`, para o painel e para a escolha de hunt (seção 6).
- **Sem abates.** Fora do Pokécenter e sem abater por `no_kills_s`, alerta `watchdog.no_kills`.

A conexão aberta e muda é da sessão (`Settings.silent_after_s`), não deste plugin.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, CenterHeal, HuntSelect, TeamActive
from ..events import Event
from .base import Plugin, PluginContext

# poções e revives da automação do jogo (estado.automation.potionIds / reviveIds)
POTIONS = {200, 201, 202, 203, 204, 70070}
REVIVES = {205, 206}


class WatchdogConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool = True
    heal_after_s: float = Field(20.0, ge=0)  # no Pokécenter há mais que isso: cura
    heal_every_s: float = Field(60.0, ge=10)  # uma tentativa de cura por minuto
    tick_s: float = Field(30.0, ge=1)
    deadly_window_s: float = Field(30 * 60.0, ge=60)
    no_kills_s: float = Field(10 * 60.0, ge=60)
    restore_active: bool = True


class WatchdogPlugin(Plugin):
    name: ClassVar[str] = "watchdog"
    description: ClassVar[str] = (
        "Vigia: cura no Pokécenter, devolve o ativo depois da morte e avisa quando a conta para"
    )
    config_model: ClassVar[type[BaseModel]] = WatchdogConfig
    subscribes: ClassVar[set[str]] = {
        "kill",
        "pokecenter",
        "field.init",
        "hunt.changed",
        "state.snapshot",
        "state.patch",
        "battle.autoHuntSemItens",
    }
    always_on: ClassVar[bool] = True

    def __init__(self) -> None:
        self.clock: Callable[[], float] = time.monotonic
        self.sleep: Callable[[float], Any] = asyncio.sleep
        self._timer: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self.center_since: float | None = None
        self.last_heal = -1e9
        self.last_kill: float | None = None
        self.no_kills_noted = False
        self.active_before_death: Any = None
        self.last_active: Any = None
        self.deaths: deque[tuple[float, str | None]] = deque(maxlen=10)
        self.dangerous_noted: set[str] = set()

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: WatchdogConfig = ctx.config  # type: ignore[assignment]
        self.last_kill = self.clock()
        self._timer = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timer

    async def _tick_loop(self) -> None:
        while True:
            await self.sleep(self.cfg.tick_s)
            async with self._lock:
                await self.check()

    async def on_event(self, event: Event) -> None:
        if not self.cfg.active:
            return
        now = self.clock()
        t = event.type
        if t == "kill":
            self.last_kill = now
            self.no_kills_noted = False
            # quem abate é o ativo de verdade; nas trocas da morte ninguém abate
            if self._active_id() is not None and self.active_before_death is None:
                self.last_active = self._active_id()
        elif t == "pokecenter" and event.data.get("reason") == "morte":
            # o ativo antes da morte: o último que a vigia viu fora do Pokécenter
            self.active_before_death = self.last_active
            hunt = self.ctx.state.hunt_slug
            self.deaths.append((now, hunt))
            await self._maybe_dangerous(now, hunt)
        elif t == "battle.autoHuntSemItens":
            await self.ctx.actions.note(
                "watchdog.no_items", {"hunt_slug": self.ctx.state.hunt_slug}
            )
        async with self._lock:
            await self.check()

    # --- regras ------------------------------------------------------------------------------

    def _team(self) -> list[dict[str, Any]]:
        return list(self.ctx.state.team or [])

    def _active_id(self) -> Any:
        return (self.ctx.state.active_pokemon or {}).get("id")

    def _has_survival_items(self) -> bool:
        items = self.ctx.state.items or {}
        has = lambda ids: any(int(items.get(str(i), 0) or 0) > 0 for i in ids)  # noqa: E731
        return has(POTIONS) and has(REVIVES)

    async def check(self) -> None:
        if not self.cfg.active:
            return
        now = self.clock()
        state = self.ctx.state
        if state.in_center:
            self.center_since = self.center_since or now
            if (
                now - self.center_since >= self.cfg.heal_after_s
                and now - self.last_heal >= self.cfg.heal_every_s
            ):
                if self._team_down():
                    if self._has_survival_items():
                        await self._heal()
                else:
                    await self._back_to_hunt()
            return
        self.center_since = None
        await self._maybe_restore_active()
        if (
            self.last_kill is not None
            and now - self.last_kill >= self.cfg.no_kills_s
            and not self.no_kills_noted
        ):
            self.no_kills_noted = True
            await self.ctx.actions.note(
                "watchdog.no_kills",
                {"minutes": round((now - self.last_kill) / 60), "hunt_slug": state.hunt_slug},
            )

    async def _heal(self) -> None:
        self.last_heal = self.clock()
        try:
            await self.ctx.actions.submit(CenterHeal(), source=self.name)
        except ActionBlocked as exc:
            await self.ctx.actions.note("watchdog.heal_blocked", {"reason": exc.reason})
            return
        await self.ctx.actions.note("watchdog.heal", {"hunt_slug": self.ctx.state.hunt_slug})

    def _team_down(self) -> bool:
        """Ninguém de pé na equipe (hp conhecido e zero em todos)."""
        hps = [m.get("hp") for m in self._team() if isinstance(m.get("hp"), int | float)]
        return not hps or all(hp <= 0 for hp in hps)

    async def _back_to_hunt(self) -> None:
        self.last_heal = self.clock()
        slug = self.ctx.state.hunt_slug
        if not slug or slug == "centro":
            return
        try:
            # a trava da hunt (hunt_hold, capture_target) deixa passar a volta para a mesma hunt
            await self.ctx.actions.submit(HuntSelect(slug=slug), source=self.name)
        except ActionBlocked as exc:
            await self.ctx.actions.note("watchdog.back_blocked", {"reason": exc.reason})
            return
        await self.ctx.actions.note("watchdog.back_to_hunt", {"hunt_slug": slug})

    async def _maybe_restore_active(self) -> None:
        want = self.active_before_death
        if not self.cfg.restore_active or want is None:
            return
        active = self._active_id()
        if active == want:
            self.active_before_death = None
            return
        member = next((m for m in self._team() if m.get("id") == want), None)
        if member is None:  # saiu da equipe: não insiste
            self.active_before_death = None
            return
        if isinstance(member.get("hp"), int | float) and member["hp"] <= 0:
            return  # ainda caído: espera a cura
        try:
            await self.ctx.actions.submit(TeamActive(pokemon_id=want), source=self.name)
        except ActionBlocked:
            return  # o gateway segura (20 s entre trocas); tenta no próximo tick
        await self.ctx.actions.note("watchdog.restore_active", {"pokemon_id": want, "was": active})
        self.active_before_death = None

    async def _maybe_dangerous(self, now: float, hunt: str | None) -> None:
        if not hunt or hunt in self.dangerous_noted:
            return
        recent = [h for t, h in self.deaths if h == hunt and now - t <= self.cfg.deadly_window_s]
        if len(recent) >= 2:
            self.dangerous_noted.add(hunt)
            await self.ctx.actions.note(
                "watchdog.dangerous_hunt",
                {"hunt_slug": hunt, "deaths": len(recent), "active_id": self.active_before_death},
            )
