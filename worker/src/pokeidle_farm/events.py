"""Eventos internos (formato nosso). Plugins só enxergam isto.

Ver docs/design/fase-2.md, seção "Eventos internos".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

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
    gold: int = 0
    gold_autosell: int = 0
    drops: list[Drop] = Field(default_factory=list)
    hunt_slug: str | None = None  # hunt atual no momento do abate (carimbada pelo tradutor)


class CaptureAttemptData(_Data):
    ball_id: Any = None
    success: bool | None = None
    shiny: bool | None = None
    chance: float | None = None
    hunt_slug: str | None = None


class HuntChangedData(_Data):
    slug: str | None = None
    name: str | None = None


class WildFledData(_Data):
    name: str | None = None
    level: int | None = None


class PokecenterData(_Data):
    reason: str | None = None


class StateSnapshotData(_Data):
    level: int | None = None
    hunt_slug: str | None = None
    items: dict[str, int] = Field(default_factory=dict)
    active_pokemon_id: Any = None


class StatePatchData(_Data):
    changed: dict[str, Any] = Field(default_factory=dict)
    pokemon_changed: list[Any] = Field(default_factory=list)
    pokemon_removed: list[Any] = Field(default_factory=list)


# Eventos de batalha que passam pelo barramento mas não são gravados.
NOT_PERSISTED = frozenset({"attack"})


class Translator:
    """Traduz mensagens do jogo em eventos internos para uma sessão."""

    def __init__(self, account_id: UUID, session_id: UUID) -> None:
        self.account_id = account_id
        self.session_id = session_id
        self.server_offset: timedelta | None = None  # servidor − local
        # Hunt atual, para carimbar abates e capturas (as métricas agregam por hunt).
        self.hunt_slug: str | None = None

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
            return [
                self._ev(
                    "state.snapshot",
                    StateSnapshotData(
                        level=st.level,
                        hunt_slug=st.hunt_slug,
                        items=st.items,
                        active_pokemon_id=st.active_id,
                    ),
                    raw,
                )
            ]
        if isinstance(msg, StatePatch):
            if raw.get("huntSlug"):
                self.hunt_slug = raw["huntSlug"]
            changed = {k: v for k, v in raw.items() if k not in ("t", "pkMud", "pkFora")}
            return [
                self._ev(
                    "state.patch",
                    StatePatchData(
                        changed=changed,
                        pokemon_changed=raw.get("pkMud") or [],
                        pokemon_removed=raw.get("pkFora") or [],
                    ),
                    raw,
                )
            ]
        if isinstance(msg, Battle):
            return [self._battle(ev.model_dump(by_alias=True)) for ev in msg.ev]
        if isinstance(msg, FieldInit):
            if msg.slug:
                self.hunt_slug = msg.slug
            return [self._ev("field.init", {"slug": msg.slug}, raw)]
        if isinstance(msg, UnknownMessage):
            return [self._ev("unknown", {"t": msg.t}, raw)]
        # SessionRenewed e GameError são tratados pela sessão (efeitos colaterais).
        return []

    def _battle(self, ev: dict[str, Any]) -> Event:
        k = ev.get("k")
        if k == "morte":
            data = KillData(
                wild_name=ev.get("nome"),
                xp=int(ev.get("xpTreinador", ev.get("xp", 0)) or 0),
                gold=int(ev.get("ouro", 0) or 0),
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
                success=ev.get("sucesso"),
                shiny=ev.get("shiny"),
                chance=ev.get("chance"),
                hunt_slug=self.hunt_slug,
            )
            return self._ev("capture_attempt", data, ev)
        if k == "hunt":
            if ev.get("slug"):
                self.hunt_slug = ev["slug"]
            return self._ev(
                "hunt.changed", HuntChangedData(slug=ev.get("slug"), name=ev.get("nome")), ev
            )
        if k == "fugiu":
            return self._ev(
                "wild_fled", WildFledData(name=ev.get("nome"), level=ev.get("level")), ev
            )
        if k == "centro":
            return self._ev("pokecenter", PokecenterData(reason=ev.get("motivo")), ev)
        if k == "ataque":
            return self._ev("attack", {"slot": ev.get("slot"), "hp": ev.get("hpAlvo")}, ev)
        return self._ev(f"battle.{k}", {}, ev)
