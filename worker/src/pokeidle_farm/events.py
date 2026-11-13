"""Eventos internos (formato nosso). Plugins só enxergam isto.

Ver docs/design/fase-2.md, seção "Eventos internos".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .catalog import ITEM_PRICES, ball_price
from .protocol.messages import (
    Battle,
    FieldInit,
    ServerMessage,
    StatePatch,
    UnknownMessage,
    Welcome,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Event(BaseModel):
    """Envelope imutável de todo evento interno."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    session_id: UUID
    type: str
    server_ts: datetime | None = None
    received_at: datetime = Field(default_factory=utcnow)
    data: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        """Linha para a tabela `events`."""
        return self.model_dump(mode="json")


# --- dados tipados por tipo de evento ---------------------------------------


class _Data(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Drop(_Data):
    name: str | None = None


class KillData(_Data):
    wild_name: str | None = None
    xp: int = 0
    xp_pokemon: int = 0
    gold: int = 0  # já inclui o gold_loot (ver docs/protocolo.md)
    gold_loot: int = 0
    loot_boost: bool = False
    gold_autosell: int = 0
    drops: list[Drop] = Field(default_factory=list)
    hunt_slug: str | None = None  # hunt atual no momento do abate (carimbada pelo tradutor)


class CaptureAttemptData(_Data):
    ball_id: Any = None
    ball_price: int | None = None  # custo da bola, para o ouro líquido
    success: bool | None = None
    shiny: bool | None = None
    chance: float | None = None
    hunt_slug: str | None = None


class CapturedData(_Data):
    """Pokémon capturado (mesmo formato do simulador e das métricas)."""

    species: str | None = None
    species_id: int | None = None
    level: int | None = None
    shiny: bool | None = None
    potency: int | None = None
    quality: float | None = None
    ivs: dict[str, int] = Field(default_factory=dict)
    iv_sum: int = 0
    pokemon_id: Any = None
    to_depot: bool | None = None
    hunt_slug: str | None = None


class HuntChangedData(_Data):
    slug: str | None = None
    name: str | None = None


class WildFledData(_Data):
    name: str | None = None
    level: int | None = None
    shiny: bool | None = None


class WildSpawnedData(_Data):
    name: str | None = None
    level: int | None = None
    max_hp: int | None = None
    species_id: int | None = None


class LevelUpData(_Data):
    who: str | None = None
    level: int | None = None


class FieldInitData(_Data):
    slug: str | None = None
    map: str | None = None
    is_center: bool = False


class ItemConsumedData(_Data):
    """Poção ou revive gasto: o estoque de `estado.items` caiu (compra só faz subir)."""

    item_id: int
    qty: int
    unit_price: int
    hunt_slug: str | None = None


class GlobalShinyData(_Data):
    """Anúncio global de shiny capturado por qualquer jogador. Não é captura nossa."""

    nick: str | None = None
    species: str | None = None
    level: int | None = None
    species_id: int | None = None


class PokecenterData(_Data):
    reason: str | None = None


class StateSnapshotData(_Data):
    level: int | None = None
    hunt_slug: str | None = None
    items: dict[str, int] = Field(default_factory=dict)
    active_pokemon_id: Any = None
    balls: dict[str, int] = Field(default_factory=dict)
    gold: int | None = None
    automation: dict[str, Any] | None = None


# Campos do patch `estado` que vão para `data` (o patch inteiro fica no `raw`).
PATCH_FIELDS = {
    "xp": "xp",
    "gold": "gold",
    "level": "level",
    "balls": "balls",
    "huntSlug": "hunt_slug",
    "centroLivreEm": "centro_livre_em",
    "items": "items",
    "automation": "automation",
}

# Mensagens de alto volume: viram evento no barramento, mas não são gravadas.
NOISE_TYPES = {
    "campo": "field.tick",
    "vivo": "keepalive",
    "chat": "chat",
    "chat.del": "chat",
    "chat.fixada": "chat",
}

# Eventos que passam pelo barramento mas não são gravados.
NOT_PERSISTED = frozenset({"attack", "wild.spawned", *NOISE_TYPES.values()})


class Translator:
    """Traduz mensagens do jogo em eventos internos para uma sessão."""

    def __init__(self, account_id: UUID, session_id: UUID) -> None:
        self.account_id = account_id
        self.session_id = session_id
        self.server_offset: timedelta | None = None  # servidor − local
        # Hunt atual, para carimbar abates e capturas (as métricas agregam por hunt).
        self.hunt_slug: str | None = None
        # Último estoque de itens conhecido, para detectar consumo de poções e revives.
        self.items: dict[str, int] = {}

    def _ev(self, type_: str, data: BaseModel | dict[str, Any], raw: dict[str, Any]) -> Event:
        now = utcnow()
        server_ts = now + self.server_offset if self.server_offset is not None else None
        payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
        return Event(
            account_id=self.account_id,
            session_id=self.session_id,
            type=type_,
            server_ts=server_ts,
            received_at=now,
            data=payload,
            raw=raw,
        )

    def system(self, type_: str, data: dict[str, Any] | None = None) -> Event:
        """Evento gerado pelo próprio worker (conexão, queda, rejeição...)."""
        return self._ev(type_, data or {}, {})

    def translate(self, msg: ServerMessage, raw: dict[str, Any]) -> list[Event]:
        if isinstance(msg, Welcome):
            st = msg.estado
            if st.servidor_agora is not None:
                server_now = datetime.fromtimestamp(st.servidor_agora / 1000, UTC)
                self.server_offset = server_now - utcnow()
            self.hunt_slug = st.hunt_slug
            self.items = dict(st.items)
            estado = raw.get("estado") or {}
            return [
                self._ev(
                    "state.snapshot",
                    StateSnapshotData(
                        level=st.level,
                        hunt_slug=st.hunt_slug,
                        items=st.items,
                        active_pokemon_id=st.active_id,
                        balls=estado.get("balls") or {},
                        gold=estado.get("gold"),
                        automation=st.automation,
                    ),
                    # só o estado da conta; as tabelas do jogo (hunts, mercado...) não são gravadas
                    {"t": raw.get("t"), "estado": estado},
                )
            ]
        if isinstance(msg, StatePatch):
            data = self._patch_data(raw)
            return [self._ev("state.patch", data, raw), *self._consumed(data.get("items"))]
        if isinstance(msg, Battle):
            return [self._battle(ev.model_dump(by_alias=True)) for ev in msg.ev]
        if isinstance(msg, FieldInit):
            is_center = bool(raw.get("centro")) or msg.slug == "centro"
            if msg.slug and not is_center:
                self.hunt_slug = msg.slug
            data = FieldInitData(slug=msg.slug, map=raw.get("mapa"), is_center=is_center)
            return [self._ev("field.init", data, raw)]
        if isinstance(msg, UnknownMessage):
            if msg.t in NOISE_TYPES:
                return [self._ev(NOISE_TYPES[msg.t], {}, raw)]
            if msg.t == "shiny.captura":
                pk = raw.get("pokemon") or {}
                data = GlobalShinyData(
                    nick=raw.get("nick"),
                    species=pk.get("nome"),
                    level=pk.get("level"),
                    species_id=pk.get("speciesId"),
                )
                return [self._ev("global.shiny_captured", data, raw)]
            return [self._ev("unknown", {"t": msg.t}, raw)]
        # SessionRenewed e GameError são tratados pela sessão (efeitos colaterais).
        return []

    def _patch_data(self, raw: dict[str, Any]) -> dict[str, Any]:
        # O formato real é aninhado ({t, estado: {...}}); o plano (no topo) ainda é aceito.
        estado = raw.get("estado")
        src = estado if isinstance(estado, dict) else raw
        if src.get("huntSlug"):
            self.hunt_slug = src["huntSlug"]
        data = {ours: src[theirs] for theirs, ours in PATCH_FIELDS.items() if theirs in src}
        data["pokemon_changed"] = [
            p.get("id") for p in src.get("pkMud") or [] if isinstance(p, dict)
        ]
        data["pokemon_removed"] = list(src.get("pkFora") or [])
        return data

    def _consumed(self, items: Any) -> list[Event]:
        if not isinstance(items, dict):
            return []
        out = []
        for key, new in items.items():
            old = self.items.get(key)
            price = ITEM_PRICES.get(int(key)) if str(key).isdigit() else None
            if price and isinstance(old, int) and isinstance(new, int) and new < old:
                data = ItemConsumedData(
                    item_id=int(key), qty=old - new, unit_price=price, hunt_slug=self.hunt_slug
                )
                out.append(self._ev("item.consumed", data, {}))
        self.items.update(items)
        return out

    def _battle(self, ev: dict[str, Any]) -> Event:
        k = ev.get("k")
        if k == "morte":
            data = KillData(
                wild_name=ev.get("nome"),
                xp=int(ev.get("xpTreinador", ev.get("xp", 0)) or 0),
                xp_pokemon=int(ev.get("xpPokemon", 0) or 0),
                gold=int(ev.get("ouro", 0) or 0),
                gold_loot=int(ev.get("ouroLoot", 0) or 0),
                loot_boost=bool(ev.get("lootBoost", False)),
                gold_autosell=int(ev.get("ouroVendaAuto", 0) or 0),
                drops=[
                    Drop(name=d.get("nome")) for d in ev.get("drops") or [] if isinstance(d, dict)
                ],
                hunt_slug=self.hunt_slug,
            )
            return self._ev("kill", data, ev)
        if k == "bola":
            data = CaptureAttemptData(
                ball_id=ev.get("ballId"),
                ball_price=ball_price(ev.get("ballId")),
                success=ev.get("sucesso"),
                shiny=ev.get("shiny"),
                chance=ev.get("chance"),
                hunt_slug=self.hunt_slug,
            )
            return self._ev("capture_attempt", data, ev)
        if k == "capturado":
            # a captura vem daqui, não do `bola` com sucesso (que só vira capture_attempt)
            pk = ev.get("pokemon") or {}
            ivs = pk.get("ivs") or {}
            data = CapturedData(
                species=pk.get("nome"),
                species_id=pk.get("speciesId"),
                level=pk.get("level"),
                shiny=pk.get("shiny"),
                potency=pk.get("potencia"),
                quality=pk.get("quality"),
                ivs=ivs,
                iv_sum=sum(v for v in ivs.values() if isinstance(v, int)),
                pokemon_id=pk.get("id"),
                to_depot=ev.get("paraDepot"),
                hunt_slug=self.hunt_slug,
            )
            return self._ev("pokemon.captured", data, ev)
        if k == "hunt":
            if ev.get("slug"):
                self.hunt_slug = ev["slug"]
            return self._ev(
                "hunt.changed", HuntChangedData(slug=ev.get("slug"), name=ev.get("nome")), ev
            )
        if k == "fugiu":
            return self._ev(
                "wild_fled",
                WildFledData(name=ev.get("nome"), level=ev.get("level"), shiny=ev.get("shiny")),
                ev,
            )
        if k == "spawn":
            data = WildSpawnedData(
                name=ev.get("nome"),
                level=ev.get("level"),
                max_hp=ev.get("maxHp"),
                species_id=ev.get("speciesId"),
            )
            return self._ev("wild.spawned", data, ev)
        if k == "levelup":
            return self._ev("level_up", LevelUpData(who=ev.get("quem"), level=ev.get("level")), ev)
        if k == "centro":
            return self._ev("pokecenter", PokecenterData(reason=ev.get("motivo")), ev)
        if k == "ataque":
            return self._ev("attack", {"slot": ev.get("slot"), "hp": ev.get("hpAlvo")}, ev)
        return self._ev(f"battle.{k}", {}, ev)
