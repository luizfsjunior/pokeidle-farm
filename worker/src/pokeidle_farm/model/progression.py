"""Simulador, camada 2: progressão nível a nível até um marco (docs/design/simulador-2-progressao.md).

Para cada nível do treinador, escolhe a hunt de maior XP/h para o ativo (camada 1) entre as que se
pagam em ouro (ouro dos abates − poções ≥ 0), aplica a XP ao treinador e ao ativo (a mesma por abate),
evolui o ativo quando o nível chega e há pedra do tipo, e soma o tempo. Os bônus de XP (VIP, evento...)
valem até a hora em que expiram, no relógio simulado.

Puro (sem rede); recebe a Pokedex crua, as regras do `welcome` e as hunts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..catalog import best_potion, potion_useful_hp
from ..gems_model import STONE_BY_TYPE
from ..xp_model import base_xp, total_xp
from .combat import Fighter, Rules, SpeciesData, combat_hp, simulate_hunt
from .predict import fighter_from_profile

GOLD_KILL_LEVEL_1 = 36
GOLD_KILL_EXP = 0.6007  # ln(6000/36)/ln(5000) (sell-value.mjs)
LOOT_BONUS = 0.15  # bônus de loot até o nível 25.000
# troca de hunt: a trava de combate, o pedido engolido e a primeira onda (medido em 16/11: 1–5 min)
SWITCH_OVERHEAD_H = 2 / 60
# desempenho: a cada nível só entram na busca os 3 níveis de hunt mais altos liberados e as
# `KEEP_BEST` melhores do nível anterior (no primeiro nível, todas)
TOP_TIERS = 3
KEEP_BEST = 8
HYSTERESIS = 0.15  # como o foco XP: fica na hunt atual se a melhor não render 15% a mais


def gold_per_kill(level: int, farm_pct: float = 0.0) -> float:
    base = GOLD_KILL_LEVEL_1 * max(1, level) ** GOLD_KILL_EXP
    return base * (1 + LOOT_BONUS * (1 + farm_pct / 100))


@dataclass(frozen=True)
class HuntRef:
    slug: str
    level: int
    species_id: int


@dataclass(frozen=True)
class Bonus:
    mult: float
    until: datetime | None  # None: permanente


@dataclass
class Account:
    trainer_level: int
    trainer_xp: float
    active: dict[str, Any]  # perfil do ativo (speciesId, level, ivs, quality, potencia, shiny)
    active_xp: float
    stones: dict[str, int] = field(default_factory=dict)  # nome da pedra -> quantidade
    bonuses: tuple[Bonus, ...] = ()
    farm_pct: float = 0.0


@dataclass(frozen=True)
class Phase:
    from_level: int
    to_level: int  # exclusivo
    hunt: str
    species_id: int
    hours: float
    kills_per_hour: float
    xp_per_hour: float
    potions_per_hour: float
    net_gold_per_hour: float
    potion_id: int = 200


@dataclass
class Plan:
    goal: int
    hours: float
    phases: list[Phase]
    evolutions: list[dict[str, Any]]
    stuck_at: int | None = None  # nível sem hunt que se pague (o plano para ali)

    def as_dict(self, now: datetime | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "goal": self.goal,
            "hours": round(self.hours, 2),
            "stuck_at": self.stuck_at,
            "evolutions": self.evolutions,
            "phases": [
                {k: (round(v, 1) if isinstance(v, float) else v) for k, v in asdict(p).items()}
                for p in self.phases
            ],
        }
        if now is not None and self.stuck_at is None:
            d["eta"] = (now + timedelta(hours=self.hours)).isoformat()
        return d


def _level_of(xp: float, floor: int) -> int:
    lv = max(1, floor)
    while total_xp(lv + 1) <= xp:
        lv += 1
    return lv


def _bonus_at(bonuses: tuple[Bonus, ...], t: datetime) -> float:
    m = 1.0
    for b in bonuses:
        if b.until is None or t < b.until:
            m *= b.mult
    return m


class _Cache:
    def __init__(self, rules: Rules, n_kills: int) -> None:
        self.rules = rules
        self.n_kills = n_kills
        self.data: dict[Any, Any] = {}

    def sim(self, f: Fighter, wild: SpeciesData, level: int) -> Any:
        key = (f.species.id, f.level, wild.id, level)
        if key not in self.data:
            self.data[key] = simulate_hunt(f, wild, level, self.rules, n_kills=self.n_kills)
        return self.data[key]


def plan_to(
    goal: int,
    account: Account,
    hunts: list[HuntRef],
    raw_species: dict[int, dict[str, Any]],
    rules_raw: dict[str, Any],
    now: datetime,
    *,
    n_kills: int = 40,
    evolve: bool = True,
) -> Plan:
    rules = Rules.from_welcome(rules_raw)
    cache = _Cache(rules, n_kills)
    wild = {
        h.species_id: SpeciesData.from_raw(raw_species[h.species_id])
        for h in hunts
        if h.species_id in raw_species
    }
    tiers = sorted({h.level for h in hunts})
    profile = dict(account.active)
    stones = dict(account.stones)
    t_xp, p_xp = float(account.trainer_xp), float(account.active_xp)
    level = account.trainer_level
    clock = now
    hours = 0.0
    phases: list[Phase] = []
    evolutions: list[dict[str, Any]] = []
    stuck: int | None = None
    keep: set[str] | None = None  # None: avalia todas as hunts liberadas
    while level < goal:
        p_level = _level_of(p_xp, int(profile.get("level") or 1))
        profile["level"] = p_level
        sid = int(profile["speciesId"])
        sp = raw_species.get(sid, {})
        to = sp.get("evolvesToId")
        evo_lv = int(sp.get("evolveLevel") or 0)
        if evolve and to and to != sid and to in raw_species and evo_lv and p_level >= evo_lv:
            stone = STONE_BY_TYPE.get(str(sp.get("type1") or "").upper())
            if stone and stones.get(stone, 0) > 0:
                stones[stone] -= 1
                profile["speciesId"] = int(to)
                evolutions.append({"level": p_level, "from": sid, "to": int(to), "stone": stone})
                continue
        fighter = fighter_from_profile(profile, raw_species, rules_raw)
        if fighter is None:
            stuck = level
            break
        allowed = [lv for lv in tiers if lv <= level][-TOP_TIERS:]
        bonus = _bonus_at(account.bonuses, clock)
        # a poção de menor custo por HP útil para o HP do ativo (como o restock compra)
        max_hp = combat_hp(fighter.stats()["hp"])
        potion_id, gold_per_hp = best_potion(max_hp)
        useful_hp = potion_useful_hp(potion_id, max_hp) or 1.0
        best = None
        ranked: list[tuple[float, str]] = []
        candidates: list[Any] = []
        for h in hunts:
            if h.level > level or h.species_id not in wild:
                continue
            if keep is not None and h.level not in allowed and h.slug not in keep:
                continue
            r = cache.sim(fighter, wild[h.species_id], h.level)
            if r.kills_per_hour <= 0:
                continue
            potions = r.damage_per_hour / useful_hp
            net = r.kills_per_hour * gold_per_kill(h.level, account.farm_pct) - (
                r.damage_per_hour * gold_per_hp
            )
            if net < 0:
                continue
            xph = r.kills_per_hour * base_xp(h.level) * bonus
            ranked.append((xph, h.slug))
            candidates.append((xph, h, r, potions, net))
            if best is None or xph > best[0]:
                best = (xph, h, r, potions, net)
        if best is None:
            stuck = level
            break
        if phases and best[1].slug != phases[-1].hunt:
            cur = next((c for c in candidates if c[1].slug == phases[-1].hunt), None)
            if cur is not None and best[0] <= cur[0] * (1 + HYSTERESIS):
                best = cur
        xph, h, r, potions, net = best
        keep = {slug for _, slug in sorted(ranked, reverse=True)[:KEEP_BEST]}
        need = total_xp(level + 1) - t_xp
        dt = need / xph
        t_xp += need
        p_xp += need
        hours += dt
        clock += timedelta(hours=dt)
        last = phases[-1] if phases else None
        if last is not None and last.hunt != h.slug:
            dt += SWITCH_OVERHEAD_H
            hours += SWITCH_OVERHEAD_H
            clock += timedelta(hours=SWITCH_OVERHEAD_H)
        if last and last.hunt == h.slug and last.species_id == fighter.species.id:
            tot = last.hours + dt
            phases[-1] = Phase(
                last.from_level,
                level + 1,
                h.slug,
                fighter.species.id,
                tot,
                (last.kills_per_hour * last.hours + r.kills_per_hour * dt) / tot,
                (last.xp_per_hour * last.hours + xph * dt) / tot,
                (last.potions_per_hour * last.hours + potions * dt) / tot,
                (last.net_gold_per_hour * last.hours + net * dt) / tot,
                potion_id,
            )
        else:
            phases.append(
                Phase(
                    level,
                    level + 1,
                    h.slug,
                    fighter.species.id,
                    dt,
                    r.kills_per_hour,
                    xph,
                    potions,
                    net,
                    potion_id,
                )
            )
        level += 1
    return Plan(goal=goal, hours=hours, phases=phases, evolutions=evolutions, stuck_at=stuck)
