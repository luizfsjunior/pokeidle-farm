"""Estimativa de gemas na Outland (nível 150; docs/design/outland-potencial.md).

Substitui o "potencial em pedras": as pedras ficam a 2 gemas com filas de semanas, então não rendem
gema de verdade antes do 150. Na Outland caem os fragmentos (Key, Shiny Stone, Bicycle), que vendem
de verdade, e o Bronze Boss Token.

gemas/h(hunt, tier) = abates/h previstos × Σ (chance do item × multiplicador do tier × preço mediano
das vendas reais × 0,85 de comissão)

- abates/h: o simulador de combate (camada 1) com o ativo no nível 150, já evoluído pela cadeia
  (o foco XP busca as pedras no caminho);
- chances (análise de 15/11, código público do jogo): cada fragmento 1 em 200 mil abates, ×1,25 a ×8
  nos tiers 2 a 8; Boss Token 0,05% por abate (sem multiplicador de tier);
- preço: a mediana das vendas reais (`market_reference`), sem anúncios inflados.

Puro (sem rede).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model.combat import Rules, SpeciesData, simulate_hunt
from .model.predict import fighter_from_profile

GOAL_LEVEL = 150
COMMISSION = 0.15
FRAGMENT_CHANCE = 1 / 200_000
TOKEN_CHANCE = 0.0005
# (nome no Mercado, chance por abate no tier 1, escala com o tier)
DROPS: tuple[tuple[str, float, bool], ...] = (
    ("Key Fragment", FRAGMENT_CHANCE, True),
    ("Shiny Stone Fragment", FRAGMENT_CHANCE, True),
    ("Bicycle Fragment", FRAGMENT_CHANCE, True),
    ("Bronze Boss Token", TOKEN_CHANCE, False),
)
TOP_TIER_MULT = 8.0


@dataclass(frozen=True)
class OutlandOption:
    slug: str
    name: str | None
    level: int
    kills_per_hour: float
    gems_per_hour: float  # tier 1
    gems_per_hour_top: float  # tier 8
    drops_per_day: float  # itens por dia a 24 h, tier 1


def final_form(
    profile: dict[str, Any], raw: dict[int, dict[str, Any]], level: int
) -> dict[str, Any]:
    """O perfil do ativo nesse nível, evoluído pela cadeia até onde o nível alcança."""
    out = dict(profile)
    out["level"] = level
    sid, seen = out.get("speciesId"), set()
    while isinstance(sid, int) and sid in raw and sid not in seen:
        seen.add(sid)
        sp = raw[sid]
        to, lv = sp.get("evolvesToId"), int(sp.get("evolveLevel") or 0)
        if not to or to == sid or to not in raw or not lv or lv > level:
            break
        sid = int(to)
    out["speciesId"] = sid
    return out


def tier_mults(rules: dict[str, Any]) -> tuple[float, float]:
    """(tier 1, tier mais alto). Lê `outlandTiers` quando tem um multiplicador de drop reconhecível;
    senão 1 e 8 (o que a análise do código do jogo mostrou)."""
    tiers = rules.get("outlandTiers")
    vals: list[float] = []
    if isinstance(tiers, list):
        for t in tiers:
            if isinstance(t, int | float) and not isinstance(t, bool):
                vals.append(float(t))
            elif isinstance(t, dict):
                for k, v in t.items():
                    lk = str(k).lower()
                    if isinstance(v, int | float) and (
                        "drop" in lk or "loot" in lk or "mult" in lk
                    ):
                        vals.append(float(v))
                        break
    vals = [v for v in vals if v > 0]
    if len(vals) >= 2 and min(vals) >= 1:
        return min(vals), max(vals)
    return 1.0, TOP_TIER_MULT


def item_value(prices: dict[str, float], mult: float) -> tuple[float, float]:
    """(gemas líquidas por abate, itens por abate) com o multiplicador do tier."""
    gems = items = 0.0
    for name, chance, scales in DROPS:
        c = chance * (mult if scales else 1.0)
        items += c
        price = prices.get(name)
        if price:
            gems += c * price * (1 - COMMISSION)
    return gems, items


def outland_options(
    hunts: list[tuple[str, str | None, int, int]],  # (slug, nome, nível, espécie)
    profile: dict[str, Any],
    raw: dict[int, dict[str, Any]],
    rules_raw: dict[str, Any],
    prices: dict[str, float],
    *,
    level: int = GOAL_LEVEL,
    n_kills: int = 30,
) -> tuple[dict[str, Any], list[OutlandOption]]:
    """(o ativo projetado, as hunts da Outland por gemas/h no tier 1)."""
    proj = final_form(profile, raw, level)
    fighter = fighter_from_profile(proj, raw, rules_raw)
    if fighter is None or not rules_raw.get("tabelaTipos"):
        return proj, []
    rules = Rules.from_welcome(rules_raw)
    low, top = tier_mults(rules_raw)
    per_kill, items_kill = item_value(prices, low)
    per_kill_top, _ = item_value(prices, top)
    out: list[OutlandOption] = []
    for slug, name, lv, sid in hunts:
        if sid not in raw:
            continue
        r = simulate_hunt(fighter, SpeciesData.from_raw(raw[sid]), lv, rules, n_kills=n_kills)
        kph = r.kills_per_hour
        if kph <= 0:
            continue
        out.append(
            OutlandOption(
                slug=slug,
                name=name,
                level=lv,
                kills_per_hour=kph,
                gems_per_hour=kph * per_kill,
                gems_per_hour_top=kph * per_kill_top,
                drops_per_day=kph * items_kill * 24,
            )
        )
    out.sort(key=lambda o: (-o.gems_per_hour, o.slug))
    return proj, out


def outland_dict(o: OutlandOption) -> dict[str, Any]:
    return {
        "slug": o.slug,
        "name": o.name,
        "level": o.level,
        "kills_per_hour": round(o.kills_per_hour, 1),
        "gems_per_hour": round(o.gems_per_hour, 2),
        "gems_per_hour_top": round(o.gems_per_hour_top, 2),
        "drops_per_day": round(o.drops_per_day, 2),
    }
