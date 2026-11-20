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
    # ovos da chocadeira (shared/chocadeira.mjs, 20/11): P2, P3 e P4; o servidor pode mandar outro
    # preço em estado.itensCompraveis, e aí o jogo cobra o dele
    70091: 20_000_000,  # Mystery Egg P2 (choca em 6 h)
    70092: 120_000_000,  # Mystery Egg P3 (12 h)
    70093: 250_000_000,  # Mystery Egg P4 (24 h)
}
# ovo (id da chocadeira) -> item na mochila (shared/chocadeira.mjs e ovo-shiny.mjs)
EGG_ITEMS: dict[str, int] = {"p2": 70091, "p3": 70092, "p4": 70093, "shiny": 70094}


# Cura das poções (items.json: healAmount; Golden Potion: 50% do HP máximo)
POTION_HEAL: dict[int, int] = {200: 60, 201: 150, 202: 400, 203: 1_000, 204: 3_000}
POTION_HEAL_PCT: dict[int, float] = {70070: 0.5}
POTION_THRESHOLD = 0.3  # a automação do jogo bebe abaixo de 30% do HP (automation.hpLimiar)


def potion_useful_hp(potion_id: int, max_hp: float, threshold: float = POTION_THRESHOLD) -> float:
    """HP que a poção cura de fato: no máximo o que falta quando a automação bebe."""
    missing = max_hp * (1 - threshold)
    heal = POTION_HEAL.get(potion_id) or POTION_HEAL_PCT.get(potion_id, 0) * max_hp
    return min(heal, missing)


def best_potion(max_hp: float, threshold: float = POTION_THRESHOLD) -> tuple[int, float]:
    """A poção de menor ouro por HP útil para esse HP máximo: (id, ouro por HP)."""
    best: tuple[int, float] | None = None
    for pid in (*POTION_HEAL, *POTION_HEAL_PCT):
        useful = potion_useful_hp(pid, max_hp, threshold)
        if useful <= 0:
            continue
        cost = ITEM_PRICES[pid] / useful
        if best is None or cost < best[1]:
            best = (pid, cost)
    return best or (200, ITEM_PRICES[200] / 60)


def ball_price(ball_id: object) -> int | None:
    ball = BALLS.get(ball_id) if isinstance(ball_id, int) else None
    return ball.price if ball else None
