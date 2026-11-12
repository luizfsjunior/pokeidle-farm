"""Modelos das mensagens do jogo (ver docs/protocolo.md).

Baseado no mapeamento do DiuleJR/pokeidle-manager-online, ainda não
confirmado no DevTools. Todos os modelos aceitam campos extras: o que ainda
não modelamos continua disponível no `raw` dos eventos.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Msg(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# --- cliente → servidor -----------------------------------------------------


class Hello(_Msg):
    t: Literal["hello"] = "hello"
    nick: str
    token: str
    delta: int = 1  # função desconhecida; valor observado na referência
    dispositivo: str


# --- servidor → cliente -----------------------------------------------------


class AccountState(_Msg):
    """`estado` do welcome (parcial: só os campos que usamos)."""

    nick: str | None = None
    level: int | None = None
    hunt_slug: str | None = Field(default=None, alias="huntSlug")
    active_id: Any = Field(default=None, alias="activeId")
    items: dict[str, int] = Field(default_factory=dict)
    automation: dict[str, Any] | None = None
    centro_livre_em: int | None = Field(default=None, alias="centroLivreEm")
    servidor_agora: int | None = Field(default=None, alias="servidorAgora")


class Welcome(_Msg):
    t: Literal["welcome"]
    estado: AccountState = Field(default_factory=AccountState)


class StatePatch(_Msg):
    t: Literal["estado"]


class BattleEvent(_Msg):
    """Item de `batalha.ev[]`; o tipo vem em `k`."""

    k: str


class Battle(_Msg):
    t: Literal["batalha"]
    ev: list[BattleEvent] = Field(default_factory=list)


class SessionRenewed(_Msg):
    t: Literal["sessao.renovada"]
    token: str


class GameError(_Msg):
    t: Literal["erro"]
    chave: str | None = None
    motivo_ban: str | None = Field(default=None, alias="motivoBan")


class FieldInit(_Msg):
    t: Literal["campo.init"]
    slug: str | None = None


class UnknownMessage(_Msg):
    """Qualquer mensagem que não reconhecemos (ou que veio malformada)."""

    t: str | None = None


ServerMessage = (
    Welcome | StatePatch | Battle | SessionRenewed | GameError | FieldInit | UnknownMessage
)


# --- chaves de erro e close codes -------------------------------------------

NEEDS_LOGIN_KEYS = frozenset({"auth.sessaoInvalida", "auth.precisaLogin"})
REJECTED_KEYS = frozenset(
    {"auth.contaBanida", "auth.ipBanido", "auth.provedorBanido", "auth.contaExcluida"}
)
ONLINE_LIMIT_KEYS = frozenset({"login.limiteOnlineIp", "login.limiteOnlineIpLista"})
NEEDS_NICK_KEYS = frozenset({"login.precisaNick"})

CLOSE_EXTERNAL_LOGIN = 4001  # mesmo token aberto em outro lugar
CLOSE_REJECTED = frozenset({4003, 1008})
