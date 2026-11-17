"""Plugin team_train: sobe a equipe inteira até um nível, trocando o pokémon ativo.

Só o ativo ganha XP cheio. Quando ele chega no `target_level`, o plugin troca o ativo
(`team.active`) para o membro da equipe mais fraco abaixo do alvo; com todos no alvo, volta para o
mais forte e para. O foco XP (`gems`) replaneja a hunt quando o ativo muda. Para os bosses, que
pedem 5 pokémon no nível do boss (docs/design/foco-outland.md, docs/design/team-train.md).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, TeamActive
from ..events import Event
from .base import Plugin, PluginContext


class TeamTrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_level: int = Field(300, ge=2, le=100_000)
    # com todos no alvo: volta o ativo para o mais forte (o que farma melhor)
    finish_on_strongest: bool = True
    confirm_s: float = Field(60.0, gt=0)  # sem o ativo mudar nesse prazo, tenta de novo


class TeamTrainPlugin(Plugin):
    name: ClassVar[str] = "team_train"
    description: ClassVar[str] = "Sobe a equipe até um nível, trocando o pokémon ativo"
    config_model: ClassVar[type[BaseModel]] = TeamTrainConfig
    subscribes: ClassVar[set[str]] = {"state.snapshot", "state.patch", "kill"}

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: TeamTrainConfig = ctx.config  # type: ignore[assignment]
        self._pending: tuple[int, datetime] | None = None  # (pokémon, quando pediu)
        self._blocked_until: datetime | None = None
        self._done_noted = False
        await self.check()

    async def on_event(self, event: Event) -> None:
        await self.check()

    def choose(self) -> tuple[int | None, str]:
        """(pokémon que deve ser o ativo, motivo). None: o atual está bom."""
        team = [p for p in (self.ctx.state.team or []) if isinstance(p.get("level"), int)]
        if not team:
            return None, "sem_equipe"
        active = self.ctx.state.active_pokemon or {}
        aid, alevel = active.get("id"), active.get("level")
        target = self.cfg.target_level
        below = [p for p in team if p["level"] < target]
        in_team = any(p["id"] == aid for p in team)
        if below:
            if in_team and isinstance(alevel, int) and alevel < target:
                return None, "treinando"
            nxt = min(below, key=lambda p: (p["level"], p["slot"]))
            return (nxt["id"] if nxt["id"] != aid else None), "proximo"
        if not self.cfg.finish_on_strongest:
            return None, "pronta"
        best = max(team, key=lambda p: (p["level"], -p["slot"]))
        return (best["id"] if best["id"] != aid else None), "pronta"

    async def check(self) -> None:
        now = self.now()
        active_id = (self.ctx.state.active_pokemon or {}).get("id")
        if self._pending is not None:
            pid, at = self._pending
            if active_id == pid:
                self._pending = None
            elif now - at < timedelta(seconds=self.cfg.confirm_s):
                return
            else:
                await self.ctx.actions.note("team_train.failed", {"pokemon_id": pid})
                self._pending = None
        if self._blocked_until is not None and now < self._blocked_until:
            return
        target_id, reason = self.choose()
        if reason == "pronta" and target_id is None and not self._done_noted:
            self._done_noted = True
            await self.ctx.actions.note(
                "team_train.done", {"target_level": self.cfg.target_level, "team": self._summary()}
            )
        if target_id is None:
            return
        try:
            await self.ctx.actions.submit(TeamActive(pokemon_id=target_id), source=self.name)
        except ActionBlocked as exc:
            self._blocked_until = now + timedelta(seconds=exc.wait_s or 30.0)
            return
        self._pending = (target_id, now)
        await self.ctx.actions.note(
            "team_train.switch",
            {
                "from": active_id,
                "to": target_id,
                "reason": reason,
                "target_level": self.cfg.target_level,
                "team": self._summary(),
            },
        )

    def _summary(self) -> list[dict[str, Any]]:
        return [
            {"id": p["id"], "speciesId": p.get("speciesId"), "level": p.get("level")}
            for p in self.ctx.state.team or []
        ]
