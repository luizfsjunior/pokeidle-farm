"""Loja do NPC: preços em ouro e chance das bolas.

Fonte: `catalogoBolas` do `welcome` e prints da loja (12/11/2026, ver docs/protocolo.md).
Os ids 203, 204 e 206 foram deduzidos pela ordem na loja (a confirmar).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ball:
    id: int
    name: str
    price: int
    catch_rate: int  # multiplicador de chance do jogo (×1 a ×4)


BALLS: dict[int, Ball] = {
    b.id: b
    for b in (
        Ball(1, "Poke Ball", 5, 1),
        Ball(2, "Great Ball", 20, 2),
        Ball(3, "Super Ball", 50, 3),
        Ball(4, "Ultra Ball", 130, 4),
    )
}

# Poções e revives (kind "item" no shop.buy)
ITEM_PRICES: dict[int, int] = {
    200: 50,  # Small Potion (+60 HP)
    201: 150,  # Great Potion (+150 HP)
    202: 400,  # Ultra Potion (+400 HP)
    203: 800,  # Hyper Potion (+1.000 HP)
    204: 1_500,  # Ultimate Potion (+3.000 HP)
    70070: 2_500,  # Golden Potion (50% do HP)
    205: 600,  # Revive (10% do HP)
    206: 5_000,  # Max Revive (100% do HP)
}


def ball_price(ball_id: object) -> int | None:
    ball = BALLS.get(ball_id) if isinstance(ball_id, int) else None
    return ball.price if ball else None
