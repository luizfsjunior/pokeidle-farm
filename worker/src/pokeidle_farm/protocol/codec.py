"""Conversão JSON ↔ modelos do protocolo."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from .messages import (
    Battle,
    FieldInit,
    GameError,
    ServerMessage,
    SessionRenewed,
    StatePatch,
    UnknownMessage,
    Welcome,
)

_BY_TYPE: dict[str, type[BaseModel]] = {
    "welcome": Welcome,
    "estado": StatePatch,
    "batalha": Battle,
    "sessao.renovada": SessionRenewed,
    "erro": GameError,
    "campo.init": FieldInit,
}


def decode(text: str | bytes) -> tuple[ServerMessage, dict[str, Any]]:
    """Decodifica um frame. Retorna (mensagem, json_original).

    Nunca levanta exceção: frame inválido ou desconhecido vira UnknownMessage,
    para que uma mudança no protocolo não derrube a sessão.
    """
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return UnknownMessage(t=None), {"_invalid_json": str(text)[:2000]}
    if not isinstance(raw, dict):
        return UnknownMessage(t=None), {"_non_object": raw}

    model = _BY_TYPE.get(str(raw.get("t")))
    if model is None:
        return UnknownMessage.model_validate(raw), raw
    try:
        return model.model_validate(raw), raw  # type: ignore[return-value]
    except ValidationError:
        return UnknownMessage.model_validate(raw), raw


def encode(message: BaseModel) -> str:
    return message.model_dump_json(by_alias=True, exclude_none=True)


def encode_raw(payload: dict[str, Any]) -> str:
    """Codifica um payload já no formato do protocolo (vindo de ActionSpec.to_wire)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
