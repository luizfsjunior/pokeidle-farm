"""Interface de plugin (ver docs/design/fase-2.md, seção 2).

Regras:
- Plugins não falam com o WebSocket; ações só pelo `ctx.actions`.
- A config é validada pelo `config_model`; config inválida desliga o plugin.
- Um plugin novo é um módulo mais uma linha em [project.entry-points] do
  pyproject.toml.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel

from ..actions import ActionGateway
from ..bus import EventBus
from ..events import Event
from ..store.base import Store


class EmptyConfig(BaseModel):
    pass


@dataclass
class AccountStateView:
    """Último estado conhecido da conta (somente leitura para plugins).

    A sessão chama `apply` com cada evento antes de publicá-lo, então um plugin
    que recebe um `state.patch` já enxerga o estado atualizado.
    """

    level: int | None = None
    hunt_slug: str | None = None
    items: dict[str, int] | None = None
    balls: dict[str, int] | None = None
    gold: int | None = None
    automation: dict[str, Any] | None = None
    # trava de combate (estado.centroLivreEm) e intervalo entre trocas (trocaLivreEm),
    # no relógio do servidor; a sessão copia o server_offset do tradutor
    combat_free_at: datetime | None = None
    switch_free_at: datetime | None = None
    server_offset: timedelta | None = None  # servidor − local
    active_level: int | None = None  # nível do pokémon ativo (do último abate)
    # o pokémon ativo como vem no `estado` (speciesId, level, ivs, quality, potencia, shiny);
    # a sessão copia do tradutor. Usado pelo simulador de combate.
    active_pokemon: dict[str, Any] | None = None
    # a equipe por slot ([{id, speciesId, level, slot}]); a sessão copia do tradutor
    team: list[dict[str, Any]] | None = None
    # para o plano até o marco: XP total do treinador, estado.bonusXp e estado.evento
    trainer_xp: float | None = None
    xp_bonus: dict[str, Any] | None = None
    xp_event: dict[str, Any] | None = None
    season: dict[str, Any] | None = None  # estado.diaSazonal ({tipo, fim, chave})
    battle_pass: dict[str, Any] | None = None  # estado.passe ({degrau, ultimo, total...})
    # no Pokécenter (estado.noCentro / campo do centro): a caça está parada até curar e voltar
    in_center: bool | None = None
    # tier escolhido da Outland (estado.outlandTier; id 101–140 ou degrau antigo 1–8, ver outland_model)
    outland_tier: int | None = None
    # quem o team_train quer treinar (id): o foco XP planeja a hunt para ele (refatoracao-2026-11-20, 2.5)
    train_target: int | None = None
    # captura ativa do painel ({species_id, species_name, ball_id}; ball_id None = a que vale a pena),
    # publicada pelo capture_target; o ball_thrower joga nos corpos dela (captura-manual.md)
    capture: dict[str, Any] | None = None
    # a bola que vale a pena (a mais forte que o ouro líquido por abate paga), calculada pelo restock;
    # None enquanto não há abates suficientes
    worth_ball: int | None = None
    # "bola em tudo" (restock no foco capture): o ball_thrower joga a worth_ball em todo corpo, porque o
    # shiny é sorteado no arremesso (wiki do jogo) e só sai jogando bola; publicado pelo restock
    catch_all: bool = False
    # (pokémon, hunt) -> até quando é perigoso (tempestade de revive vista pela vigia, 2.4)
    danger: dict[tuple[Any, str], datetime] = field(default_factory=dict)

    def is_dangerous(self, pokemon_id: Any, slug: str | None, now: datetime | None = None) -> bool:
        if not slug:
            return False
        until = self.danger.get((pokemon_id, slug))
        return until is not None and until > (now or datetime.now(UTC))

    def mon(self, pokemon_id: Any) -> dict[str, Any] | None:
        """O perfil de um membro da equipe (o ativo, se for ele: tem o nível mais novo)."""
        active = self.active_pokemon or {}
        if active.get("id") == pokemon_id:
            return active
        return next((m for m in self.team or [] if m.get("id") == pokemon_id), None)

    def season_type(self, now: datetime | None = None) -> str | None:
        """O tipo do dia sazonal se ainda vale (no relógio do servidor)."""
        s = self.season or {}
        end = s.get("fim")
        if not isinstance(s.get("tipo"), str) or not isinstance(end, int | float):
            return None
        return s["tipo"].upper() if self.server_now(now).timestamp() * 1000 < end else None

    def server_now(self, now: datetime | None = None) -> datetime:
        """Relógio do servidor (o local, se o offset ainda não é conhecido)."""
        now = now or datetime.now(UTC)
        return now + self.server_offset if self.server_offset is not None else now

    def apply(self, event: Event) -> None:
        d = event.data
        if event.type == "kill":
            if isinstance(d.get("active_level"), int):
                self.active_level = d["active_level"]
            return
        if event.type == "hunt.changed":
            free = _as_datetime(d.get("switch_free_at"))
            if free is not None:
                self.switch_free_at = free
            self.in_center = False
            return
        if event.type == "field.init":
            self.in_center = bool(d.get("is_center"))
            return
        if event.type not in ("state.snapshot", "state.patch"):
            return
        lock = d.get("centro_livre_em")
        if isinstance(lock, int | float):
            self.combat_free_at = datetime.fromtimestamp(lock / 1000, UTC)
        for name in ("level", "hunt_slug", "gold", "automation", "in_center", "outland_tier"):
            if d.get(name) is not None:
                setattr(self, name, d[name])
        # bolas e itens: merge, porque um patch pode trazer só parte do mapa
        for name in ("items", "balls"):
            if isinstance(d.get(name), dict):
                setattr(self, name, {**(getattr(self, name) or {}), **d[name]})


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


@dataclass
class PluginContext:
    account_id: UUID
    nick: str
    config: BaseModel
    bus: EventBus
    actions: ActionGateway
    state: AccountStateView
    store: Store
    settings: Any
    log: logging.Logger
    catalog: Any = None  # HuntCatalog do último welcome (fase 3b)
    species: Any = None  # SpeciesCatalog (Pokedex), compartilhado pelo worker


class Plugin(ABC):
    name: ClassVar[str]
    description: ClassVar[str] = ""
    config_model: ClassVar[type[BaseModel]] = EmptyConfig
    subscribes: ClassVar[set[str] | Literal["*"]] = "*"
    excludes: ClassVar[set[str]] = set()
    queue_size: ClassVar[int] = 1000
    # Plugins "core" sobem sempre; os outros só se ligados em strategy_configs.
    always_on: ClassVar[bool] = False

    ctx: PluginContext

    async def start(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    @abstractmethod
    async def on_event(self, event: Event) -> None: ...

    async def stop(self) -> None:  # noqa: B027 - opcional para subclasses
        pass
