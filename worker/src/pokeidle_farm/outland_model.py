"""Estimativa de gemas na Outland (nível 150; docs/design/outland-potencial.md).

Substitui o "potencial em pedras": as pedras ficam a 2 gemas com filas de semanas, então não rendem
gema de verdade antes do 150. Na Outland caem os fragmentos (Key, Shiny Stone, Bicycle), que vendem
de verdade, e o Bronze Boss Token.

gemas/h(hunt, tier) = abates/h previstos × Σ (chance do item × multiplicador do tier × preço mediano
das vendas reais × 0,85 de comissão)

- abates/h: o simulador de combate (camada 1) com o ativo no nível 150, já evoluído pela cadeia
  (o foco XP busca as pedras no caminho);
- chances (wiki do jogo, `pokepedia.mjs`, 17/11): Key, Shiny Stone e Bicycle Fragment 1 em 250 mil
  abates cada, Bronze Boss Token 1 em 10 mil; o tier da Outland multiplica os cinco drops raros
  (inclusive o Osso do Sacrifício, que fica de fora por não sabermos a chance). O tier depende do nível
  do treinador (`outlandTiers` nas regras: ×1 no 150, ×1,1 no 500, ×2 no 2.250, ×20 no 65.000); o
  selvagem é o mesmo em todos (mesmo mapa, nível 150);
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
FRAGMENT_CHANCE = 0.000004  # 1 em 250 mil (padrão da wiki: casas, shinyStone, bicicletas)
TOKEN_CHANCE = 0.0001  # 1 em 10 mil (chanceBossToken)
# (nome no Mercado, chance por abate na Outland 1, escala com o tier)
DROPS: tuple[tuple[str, float, bool], ...] = (
    ("Key Fragment", FRAGMENT_CHANCE, True),
    ("Shiny Stone Fragment", FRAGMENT_CHANCE, True),
    ("Bicycle Fragment", FRAGMENT_CHANCE, True),
    ("Bronze Boss Token", TOKEN_CHANCE, True),
)


@dataclass(frozen=True)
class OutlandOption:
    slug: str
    name: str | None
    level: int
    kills_per_hour: float
    gems_per_hour: float  # Outland 1
    gems_per_hour_top: float  # o maior tier liberado no nível do treinador (×1 até o 500)
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


def tier_mult_at(rules: dict[str, Any], level: int | None) -> tuple[float, str | None]:
    """(multiplicador, rótulo) do maior tier da Outland liberado nesse nível do treinador.
    Sem `outlandTiers` legível: ×1."""
    tiers = rules.get("outlandTiers")
    best: tuple[float, str | None] = (1.0, None)
    if not isinstance(tiers, list) or level is None:
        return best
    top = -1
    for t in tiers:
        if not isinstance(t, dict):
            continue
        lv, mult = t.get("nivel"), t.get("mult")
        if not isinstance(lv, int | float) or not isinstance(mult, int | float):
            continue
        if lv <= level and lv > top:
            top = lv
            best = (float(mult), str(t.get("rotulo") or "") or None)
    return best


ID_BASE_OUTLAND = 100  # shared/outland-tiers.mjs: o tier N tem id 100 + N
# degraus de antes de 16/11 (id 1–8) que o servidor ainda aceita: o nível de cada um vira o tier novo
# mais alto até ele (ehDegrauAntigo / fichaDoDegrauAntigo)
LEGACY_TIER_LEVEL = {
    1: 150,
    2: 1_000,
    3: 2_000,
    4: 4_000,
    5: 8_000,
    6: 16_000,
    7: 24_000,
    8: 36_000,
}


@dataclass(frozen=True)
class OutlandTier:
    tier: int  # o id que vai no `outland.tier` (101, 102...)
    number: int  # Outland N
    level: int  # nível do treinador que libera
    mult: float


def outland_tiers(rules: dict[str, Any]) -> list[OutlandTier]:
    """Os tiers das regras do welcome (`outlandTiers`), em ordem. Sem o `tier` (formato antigo), o id
    sai da posição, como no jogo."""
    raw = rules.get("outlandTiers")
    out: list[OutlandTier] = []
    if not isinstance(raw, list):
        return out
    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            continue
        lv, mult = t.get("nivel"), t.get("mult")
        if not isinstance(lv, int | float) or not isinstance(mult, int | float):
            continue
        tid = t.get("tier")
        num = t.get("numero")
        out.append(
            OutlandTier(
                tier=int(tid) if isinstance(tid, int) else ID_BASE_OUTLAND + i + 1,
                number=int(num) if isinstance(num, int) else i + 1,
                level=int(lv),
                mult=float(mult),
            )
        )
    return out


def current_tier(tiers: list[OutlandTier], tier: int | None) -> OutlandTier | None:
    """O tier que vale para o valor do `estado.outlandTier` (None ou desconhecido: o primeiro, que é o
    padrão do jogo; degrau antigo: o tier novo equivalente)."""
    if not tiers:
        return None
    if tier in LEGACY_TIER_LEVEL:
        lv = LEGACY_TIER_LEVEL[tier]
        return max((t for t in tiers if t.level <= lv), key=lambda t: t.level, default=tiers[0])
    return next((t for t in tiers if t.tier == tier), tiers[0])


def best_tier(tiers: list[OutlandTier], level: int | None) -> OutlandTier | None:
    """O maior tier liberado nesse nível do treinador (None abaixo do 150)."""
    if level is None:
        return None
    unlocked = [t for t in tiers if t.level <= level]
    return max(unlocked, key=lambda t: t.level, default=None)


def tier_upgrade(rules: dict[str, Any], level: int | None, tier: int | None) -> OutlandTier | None:
    """O tier para onde subir, ou None se a conta já está no melhor liberado (ou não sabemos)."""
    tiers = outland_tiers(rules)
    best = best_tier(tiers, level)
    now = current_tier(tiers, tier)
    if best is None or now is None:
        return None
    return best if best.level > now.level else None


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
    top_level: int | None = None,  # nível do treinador para o tier "seu" (o maior liberado)
    n_kills: int = 30,
) -> tuple[dict[str, Any], list[OutlandOption]]:
    """(o ativo projetado, as hunts da Outland por gemas/h no tier 1)."""
    proj = final_form(profile, raw, level)
    fighter = fighter_from_profile(proj, raw, rules_raw)
    if fighter is None or not rules_raw.get("tabelaTipos"):
        return proj, []
    rules = Rules.from_welcome(rules_raw)
    top, _label = tier_mult_at(rules_raw, max(level, top_level or level))
    per_kill, items_kill = item_value(prices, 1.0)
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


# --- foco Outland (plugin gems, objective "outland"; docs/design/foco-outland.md) --------------


def outland_prices(reference: dict[str, dict[str, Any]]) -> dict[str, float]:
    """Mediana das vendas reais (`market_reference`) dos drops da Outland, por nome do Mercado."""
    by_lower = {k.lower(): v for k, v in reference.items()}
    prices: dict[str, float] = {}
    for name, _c, _s in DROPS:
        r = by_lower.get(name.lower())
        if r and r.get("median"):
            prices[name] = float(r["median"])
    return prices


def is_outland(hunt: Any) -> bool:
    return str(getattr(hunt, "area", "") or "").lower() == "outland"


@dataclass(frozen=True)
class OutlandPick:
    slug: str
    name: str | None
    level: int
    kills_per_hour: float
    kph_source: str  # de onde veio o ritmo: medido, simulador, nível...
    gems_per_hour: float  # no tier atual da conta, líquido de comissão
    drops_per_day: float  # itens raros por dia a 24 h no tier atual


def outland_picks(
    hunts: Any,  # o catálogo de hunts (slug -> hunt com level, area, name, species_name)
    trainer_level: int,
    rate: dict[str, tuple[float, str]],  # slug -> (abates/h, fonte), o mesmo do foco XP
    prices: dict[str, float],
    mult: float,
    skip: set[str] | frozenset[str] = frozenset(),
) -> list[OutlandPick]:
    """As hunts da Outland alcançáveis, da que mais rende para a que menos.

    Os drops e o tier são os mesmos em todas as hunts da Outland, então quem decide é o ritmo de
    abates do ativo (o empate fica com o slug, para a escolha não oscilar)."""
    per_kill, items_kill = item_value(prices, mult)
    out: list[OutlandPick] = []
    for h in hunts.values():
        if not is_outland(h) or h.level > trainer_level or h.slug in skip or h.slug not in rate:
            continue
        kph, source = rate[h.slug]
        if kph <= 0:
            continue
        out.append(
            OutlandPick(
                slug=h.slug,
                name=getattr(h, "species_name", None) or getattr(h, "name", None),
                level=h.level,
                kills_per_hour=kph,
                kph_source=source,
                gems_per_hour=kph * per_kill,
                drops_per_day=kph * items_kill * 24,
            )
        )
    out.sort(key=lambda o: (-o.kills_per_hour, o.slug))
    return out


def outland_pick_dict(o: OutlandPick) -> dict[str, Any]:
    return {
        "slug": o.slug,
        "name": o.name,
        "level": o.level,
        "kills_per_hour": round(o.kills_per_hour, 1),
        "kph_source": o.kph_source,
        "gems_per_hour": round(o.gems_per_hour, 3),
        "drops_per_day": round(o.drops_per_day, 3),
    }
