"""Plugin team_train: sobe a equipe inteira até um nível, trocando o pokémon ativo.

Só o ativo ganha XP cheio. Quando ele chega no `target_level`, o próximo a treinar é o membro mais
fraco abaixo do alvo; com todos no alvo, volta para o mais forte e para. Para os bosses, que pedem 5
pokémon no nível do boss (docs/design/foco-outland.md, docs/design/team-train.md).

Com o foco XP ligado (refatoracao-2026-11-20, 2.5), o plugin publica quem vai treinar em
`state.train_target`; o foco planeja a hunt para esse pokémon, e a troca do ativo só sai quando a
conta já está numa hunt segura para ele (nível da hunt <= nível dele + `max_over_active`, fora das
marcadas como perigosas pela vigia). Antes, a troca saía na hora e o pokémon fraco morria em loop na
hunt do forte (20/11: ~1,4 M de ouro em revives numa hora). Sem o foco XP, troca na hora (ninguém
mais muda a hunt).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionBlocked, TeamActive
from ..events import Event
from .base import Plugin, PluginContext

MAX_BACKOFF_S = 30 * 60.0


class TeamTrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_level: int = Field(300, ge=2, le=100_000)
    # com todos no alvo: volta o ativo para o mais forte (o que farma melhor)
    finish_on_strongest: bool = True
    confirm_s: float = Field(60.0, gt=0)  # sem o ativo mudar nesse prazo, conta como falha
    # hunt segura para quem vai treinar: nível <= o dele + isto (o mesmo do foco XP)
    max_over_active: int = Field(10, ge=0, le=1000)


class TeamTrainPlugin(Plugin):
    name: ClassVar[str] = "team_train"
    description: ClassVar[str] = "Sobe a equipe até um nível, trocando o pokémon ativo"
    config_model: ClassVar[type[BaseModel]] = TeamTrainConfig
    subscribes: ClassVar[set[str]] = {"state.snapshot", "state.patch", "kill", "hunt.changed"}

    def __init__(self) -> None:
        self.now = lambda: datetime.now(UTC)

    async def start(self, ctx: PluginContext) -> None:
        await super().start(ctx)
        self.cfg: TeamTrainConfig = ctx.config  # type: ignore[assignment]
        self._pending: tuple[int, datetime] | None = None  # (pokémon, quando pediu)
        self._blocked_until: datetime | None = None
        self._fails = 0
        self._done_noted = False
        self._waiting_noted: tuple[Any, Any] | None = None
        self._xp_focus = await self._xp_focus_on()
        await self.check()

    async def stop(self) -> None:
        if getattr(self.ctx.state, "train_target", None) is not None:
            self.ctx.state.train_target = None

    async def _xp_focus_on(self) -> bool:
        """O foco XP (gems com objective xp, agindo) leva a conta para a hunt de quem treina."""
        store = getattr(self.ctx, "store", None)
        if store is None:
            return False
        try:
            configs = await store.plugin_configs(self.ctx.account_id)
        except Exception:
            return False
        enabled, cfg = configs.get("gems", (False, {}))
        cfg = cfg or {}
        return bool(enabled) and cfg.get("objective") == "xp" and cfg.get("dry_run") is False

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

    def _hunt_safe_for(self, pid: int) -> bool:
        """A hunt de agora é segura para o pokémon (nível e a marca de perigo da vigia)."""
        st = self.ctx.state
        slug = st.hunt_slug
        mon = next((m for m in st.team or [] if m.get("id") == pid), None)
        level = (mon or {}).get("level")
        if not slug or not isinstance(level, int):
            return False
        danger = getattr(st, "is_dangerous", None)
        if danger is not None and danger(pid, slug, self.now()):
            return False
        catalog = getattr(self.ctx, "catalog", None)
        hunt = catalog.hunts.get(slug) if catalog is not None else None
        if hunt is None:
            return False  # sem saber o nível da hunt, não arrisca
        return hunt.level <= level + self.cfg.max_over_active

    async def check(self) -> None:
        now = self.now()
        active_id = (self.ctx.state.active_pokemon or {}).get("id")
        if self._pending is not None:
            pid, at = self._pending
            if active_id == pid:
                self._pending = None
                self._fails = 0
            elif now - at < timedelta(seconds=self.cfg.confirm_s):
                return
            else:
                # falhou: espera 1, 2, 4... min, até 30 min, antes de tentar de novo
                self._fails += 1
                wait = min(MAX_BACKOFF_S, 60.0 * 2 ** (self._fails - 1))
                self._blocked_until = now + timedelta(seconds=wait)
                await self.ctx.actions.note(
                    "team_train.failed", {"pokemon_id": pid, "retry_s": wait}
                )
                self._pending = None
        target_id, reason = self.choose()
        # quem treina agora: o escolhido para trocar ou, se o atual está treinando, ele mesmo
        training = (
            target_id if target_id is not None else (active_id if reason == "treinando" else None)
        )
        if self.ctx.state.train_target != training:
            self.ctx.state.train_target = training
        if self._blocked_until is not None and now < self._blocked_until:
            return
        if reason == "pronta" and target_id is None and not self._done_noted:
            self._done_noted = True
            await self.ctx.actions.note(
                "team_train.done", {"target_level": self.cfg.target_level, "team": self._summary()}
            )
        if target_id is None:
            return
        # o mais forte (fim do treino) aguenta qualquer hunt; o fraco espera a hunt dele
        st = self.ctx.state
        marked = st.is_dangerous(
            target_id, st.hunt_slug, now
        )  # a vigia viu ele morrer em loop aqui
        if reason == "proximo" and (
            marked or (self._xp_focus and not self._hunt_safe_for(target_id))
        ):
            key = (target_id, self.ctx.state.hunt_slug)
            if self._waiting_noted != key:
                self._waiting_noted = key
                await self.ctx.actions.note(
                    "team_train.waiting_hunt",
                    {"pokemon_id": target_id, "hunt_slug": self.ctx.state.hunt_slug},
                )
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
