"""Plugin daily: resgata o passe de batalha grátis uma vez por dia (docs/design/simulador-4-decisoes.md).

O passe (`passe-batalha.mjs`) é uma trilha de 30 dias com prêmio grátis por dia: Coins (250 mil a
5 milhões), boosts de XP (dias 3, 14 e 29) e de XP do pokémon (9 e 26), revives, bolas e um Boss
Token no dia 30. A sequência zera se um dia passar sem resgate. O dia vira às 03:00 UTC (meia-noite
de Brasília). Exige treinador nível 10.

- a cada evento confere `estado.passe.ultimo` contra o dia de hoje (relógio do servidor); se ainda
  não resgatou, manda `passe.resgatar`;
- confirma pelo `estado.passe` (o `ultimo` vira hoje): `daily.claimed`; sem confirmação em
  `confirm_s`, `daily.failed` e tenta de novo depois de `retry_min`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, PassClaim
from ..events import Event
from .base import Plugin, PluginContext

PASS_DAY_OFFSET_MS = 3 * 3600_000  # PASSE_FUSO_MS
DAY_MS = 86_400_000
PASS_MIN_LEVEL = 10


def pass_day(ms: float) -> int:
    """Dia do passe (diaDoPasse do jogo) para um instante em ms."""
    return int((ms - PASS_DAY_OFFSET_MS) // DAY_MS)


class DailyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_pass: bool = True
    confirm_s: float = Field(60.0, gt=0)
    retry_min: float = Field(30.0, gt=0)


class DailyPlugin(Plugin):
    name: ClassVar[str] = "daily"
    description: ClassVar[str] = "Resgata o passe de batalha grátis todo dia"
    config_model: ClassVar[type[BaseModel]] = DailyConfig
    subscribes: ClassVar[set[str]] = {"state.snapshot", "state.patch", "kill"}

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: DailyConfig = ctx.config  # type: ignore[assignment]
        self.sent: tuple[int, datetime] | None = None  # (dia, quando)
        self.retry_at: datetime | None = None
        await self._tick()

    async def on_event(self, event: Event) -> None:
        await self._tick()

    def _today(self) -> int:
        return pass_day(self.ctx.state.server_now(self.now()).timestamp() * 1000)

    async def _tick(self) -> None:
        if not self.cfg.claim_pass:
            return
        st = self.ctx.state
        bp: dict[str, Any] = st.battle_pass or {}
        if st.level is None or st.level < PASS_MIN_LEVEL or not st.battle_pass:
            return
        today, now = self._today(), self.now()
        if self.sent is not None:
            day, at = self.sent
            if bp.get("ultimo") == day:
                self.sent = None
                await self.ctx.actions.note(
                    "daily.claimed",
                    {"day": day, "step": bp.get("degrau"), "total": bp.get("total")},
                )
            elif now - at >= timedelta(seconds=self.cfg.confirm_s):
                self.sent = None
                self.retry_at = now + timedelta(minutes=self.cfg.retry_min)
                await self.ctx.actions.note(
                    "daily.failed", {"day": day, "reason": "sem_confirmacao"}
                )
            return
        if bp.get("ultimo") == today:
            return
        if self.retry_at is not None and now < self.retry_at:
            return
        try:
            await self.ctx.actions.submit(PassClaim(), source=self.name)
        except ActionBlocked as exc:
            self.retry_at = now + timedelta(minutes=self.cfg.retry_min)
            await self.ctx.actions.note("daily.failed", {"day": today, "reason": exc.reason})
            return
        self.sent = (today, now)
