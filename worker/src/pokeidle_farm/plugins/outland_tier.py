"""Plugin outland_tier: mantém a conta no maior tier da Outland que o nível do treinador libera.

O jogo não sobe o tier sozinho quando o treinador sobe de nível (regras-do-jogo.md, Outland). O tier
só multiplica os cinco drops raros (Boss Token, fragmentos de Chave, Shiny Stone e Bicicleta, Osso do
Sacrifício); mapa, selvagens, XP e ouro são iguais em todos, então o maior liberado nunca é pior.

- a cada `state.snapshot`/`state.patch` compara o tier atual (`estado.outlandTier`) com o maior liberado
  (`outlandTiers` das regras do welcome, `outland_model.tier_upgrade`);
- se der para subir, manda `outland.tier` e grava `outland.tier_set`;
- confirma pelo `estado.outlandTier`: `outland.tier_changed`; sem confirmação em `confirm_s`,
  `outland.tier_failed` e tenta de novo depois de `retry_min`.

Sempre ligado; `active: false` na config desliga a troca (para escolher o tier à mão).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, OutlandTierSelect
from ..events import Event
from ..outland_model import OutlandTier, current_tier, outland_tiers, tier_upgrade
from .base import Plugin, PluginContext


class OutlandTierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool = True
    confirm_s: float = Field(60.0, gt=0)
    retry_min: float = Field(30.0, gt=0)


class OutlandTierPlugin(Plugin):
    name: ClassVar[str] = "outland_tier"
    description: ClassVar[str] = "Põe a conta no maior tier da Outland liberado pelo nível"
    config_model: ClassVar[type[BaseModel]] = OutlandTierConfig
    subscribes: ClassVar[set[str]] = {"state.snapshot", "state.patch"}
    always_on: ClassVar[bool] = True

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: OutlandTierConfig = ctx.config  # type: ignore[assignment]
        self.sent: tuple[OutlandTier, datetime] | None = None
        self.retry_at: datetime | None = None
        await self._tick()

    async def on_event(self, event: Event) -> None:
        await self._tick()

    async def _tick(self) -> None:
        if not self.cfg.active:
            return
        rules = getattr(self.ctx.catalog, "rules", None) or {}
        st = self.ctx.state
        now = self.now()
        if self.sent is not None:
            target, at = self.sent
            got = current_tier(outland_tiers(rules), st.outland_tier)
            if got is not None and got.level >= target.level:
                self.sent = None
                await self.ctx.actions.note(
                    "outland.tier_changed",
                    {"tier": target.tier, "number": target.number, "mult": target.mult},
                )
            elif now - at >= timedelta(seconds=self.cfg.confirm_s):
                self.sent = None
                self.retry_at = now + timedelta(minutes=self.cfg.retry_min)
                await self.ctx.actions.note(
                    "outland.tier_failed", {"tier": target.tier, "reason": "sem_confirmacao"}
                )
            return
        if self.retry_at is not None and now < self.retry_at:
            return
        target = tier_upgrade(rules, st.level, st.outland_tier)
        if target is None:
            return
        try:
            await self.ctx.actions.submit(OutlandTierSelect(tier=target.tier), source=self.name)
        except ActionBlocked as exc:
            self.retry_at = now + timedelta(minutes=self.cfg.retry_min)
            await self.ctx.actions.note(
                "outland.tier_failed", {"tier": target.tier, "reason": exc.reason}
            )
            return
        self.sent = (target, now)
        await self.ctx.actions.note(
            "outland.tier_set",
            {
                "tier": target.tier,
                "number": target.number,
                "mult": target.mult,
                "from": st.outland_tier,
                "level": st.level,
            },
        )
