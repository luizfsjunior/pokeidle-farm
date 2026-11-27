"""Plugin boss: luta contra o boss lendário do prêmio escolhido enquanto houver Boss Token (épico C4).

Ver docs/design/protegidos-e-bosses.md. A cada `check_s` (e a cada mudança de estado):

1. escolhe o boss (`boss_model.choose`): o do prêmio de hoje pedido em `prize`, na região mais alta
   em que o treinador entra e a equipe aguenta (`max_mult`: 1 = os 5 no nível do boss);
2. se dá para lutar e o jogo ainda não repete esse boss, liga a repetição (`boss.auto`) nele; se a
   conta não está na arena, entra (`boss.entrar`), no máximo uma vez a cada `enter_every_s`;
3. se a equipe deixou de aguentar (ou o treinador mudou de região) e a repetição que nós ligamos
   continua, desliga. Sem token o próprio jogo para.

O prêmio do trio gira às 18:00 de Brasília: na virada, o boss escolhido muda e o plugin troca a
repetição para o novo.

Desligado por padrão e, ligado, começa em `dry_run` (grava `boss.would` em vez de mandar): o
protocolo do boss foi lido do app.js e nunca mandado (épico C3). Grava `boss.plan` quando a escolha
muda e `boss.auto_set`/`boss.entered`/`boss.auto_off` quando manda.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, ActionSpec, BossAuto, BossEnter
from ..boss_model import Choice, Prize, choose
from ..events import Event
from .base import Plugin, PluginContext


class BossConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prize: Prize = "mega"
    region: Literal[
        "auto", "kanto", "johto", "hoenn", "sinnoh", "unova", "kalos", "alola", "galar", "paldea"
    ] = "auto"
    max_mult: float = Field(1.0, ge=1.0, le=27.0)
    min_tokens: int = Field(1, ge=1)
    dry_run: bool = True
    check_s: float = Field(60.0, ge=10)
    enter_every_s: float = Field(180.0, ge=30)


class BossPlugin(Plugin):
    name: ClassVar[str] = "boss"
    description: ClassVar[str] = "Luta no boss do prêmio escolhido enquanto houver Boss Token"
    config_model: ClassVar[type[BaseModel]] = BossConfig
    subscribes: ClassVar[set[str]] = {"state.snapshot", "state.patch"}

    def __init__(self) -> None:
        self.clock = time.monotonic
        self.now = lambda: datetime.now(UTC)
        self.boss_state: dict[str, Any] = {}  # estado.boss {auto, autoKey, arena, vitorias, pontos}
        self._last_check = -1e9
        self._last_enter = -1e9
        self._plan: tuple[str | None, str] | None = None
        self._ours: str | None = None  # a key cuja repetição nós ligamos

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: BossConfig = ctx.config  # type: ignore[assignment]

    async def on_event(self, event: Event) -> None:
        estado = event.raw.get("estado")
        if isinstance(estado, dict) and isinstance(estado.get("boss"), dict):
            if event.type == "state.snapshot":
                self.boss_state = dict(estado["boss"])
            else:
                self.boss_state.update(estado["boss"])
        if self.clock() - self._last_check >= self.cfg.check_s:
            await self.tick()

    def team_levels(self) -> list[int]:
        st = self.ctx.state
        out = []
        for m in st.team or []:
            fresh = st.mon(m.get("id")) or m
            lv = fresh.get("level")
            if isinstance(lv, int | float):
                out.append(int(lv))
        return out

    def decide(self) -> Choice:
        st = self.ctx.state
        season = st.season if isinstance(st.season, dict) else {}
        return choose(
            getattr(self.ctx.catalog, "rules", None),
            trainer_level=st.level,
            team_levels=self.team_levels(),
            items=st.items,
            prize=self.cfg.prize,
            region=self.cfg.region,
            max_mult=self.cfg.max_mult,
            min_tokens=self.cfg.min_tokens,
            now=self.now(),
            season_key=season.get("chave") if isinstance(season.get("chave"), str) else None,
        )

    async def tick(self) -> None:
        self._last_check = self.clock()
        if getattr(self.ctx.catalog, "rules", None) is None or self.ctx.state.level is None:
            return
        c = self.decide()
        key = c.boss.key if c.boss else None
        if self._plan != (key, c.reason):
            self._plan = (key, c.reason)
            await self.ctx.actions.note(
                "boss.plan",
                {
                    "key": key,
                    "name": c.boss.name if c.boss else None,
                    "reason": c.reason,
                    "mult": round(c.mult, 2) if c.mult is not None else None,
                    "tokens": c.tokens,
                    "prize": self.cfg.prize,
                    "dry_run": self.cfg.dry_run,
                },
            )
        auto = bool(self.boss_state.get("auto"))
        auto_key = self.boss_state.get("autoKey")
        if c.ok and c.boss is not None:
            if not auto or auto_key != c.boss.key:
                if await self._send(BossAuto(key=c.boss.key, ativo=True), "boss.auto_set"):
                    self._ours = c.boss.key
            if self.boss_state.get("arena") is None and (
                self.clock() - self._last_enter >= self.cfg.enter_every_s
            ):
                self._last_enter = self.clock()
                await self._send(BossEnter(key=c.boss.key), "boss.entered")
            return
        # não dá mais: desliga a repetição que nós ligamos (sem token o jogo para sozinho)
        if c.reason != "sem_token" and auto and self._ours is not None and auto_key == self._ours:
            if await self._send(BossAuto(key=self._ours, ativo=False), "boss.auto_off"):
                self._ours = None

    async def _send(self, action: ActionSpec, step: str) -> bool:
        wire = action.to_wire()
        if self.cfg.dry_run:
            await self.ctx.actions.note("boss.would", {"step": step, "wire": wire})
            # no ensaio o estado não muda: finge que mudou para não repetir a cada tick
            if isinstance(action, BossAuto):
                self.boss_state.update({"auto": action.ativo, "autoKey": action.key})
            elif isinstance(action, BossEnter):
                self.boss_state["arena"] = {"key": action.key, "ensaio": True}
            return True
        try:
            await self.ctx.actions.submit(action, source=self.name)
        except ActionBlocked as exc:
            await self.ctx.actions.note("boss.blocked", {"step": step, "reason": exc.reason})
            return False
        await self.ctx.actions.note(step, wire)
        return True
