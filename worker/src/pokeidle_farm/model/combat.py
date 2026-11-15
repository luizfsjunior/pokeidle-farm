"""Simulador, camada 1: combate (abates por hora de um pokémon numa hunt).

Ver docs/design/simulador-1-combate.md. Regras do jogo (código público v1.420.0, wiki e o `welcome`):

- stat = arred((base + 2·IV) × nível/100 × qualidade^expoente × multiplicador), expoente 0,95 para
  HP e Velocidade e 0,8 para os outros; multiplicador = (1 + bônus da potência) × shiny × lendário;
- HP de combate = máx(24, arred(hp × 12)); o selvagem tem × `multHpSelvagem` (5);
- dano = ((2·nível/5 + 2) × poder × atk/def)/50 + 2, × 1,5 (STAB) × efetividade × aleatório
  (0,85–1,00; média 0,925). Físico usa Atk/Def; especial, Sp.Atk/Sp.Def;
- efetividade "na hunt": v > 1 vira 1 + (v − 1)·ampliação; v < 1 vira v/ampliação (ampliação 1,5);
- golpes: recarga própria (o Speed base desconta até 7%, proporcional ao IV de SPD); a cada ataque
  usa o golpe pronto de maior dano esperado; com todos em recarga, a Investida (poder 30, física,
  no tipo do pokémon, a cada 2 s − 10 ms por ponto de IV de SPD); no mínimo 0,9 s entre golpes;
- ondas: os selvagens vêm em ondas; entre um abate e o próximo o pokémon anda até o selvagem, e
  quando a onda acaba a seguinte entra depois de uma espera. Tamanho da onda, caminhada e espera
  são medidos (ver `WaveModel`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

STATS = ("hp", "atk", "def", "spAtk", "spDef", "speed")
BASE_KEYS = {
    "hp": "baseHp",
    "atk": "baseAtk",
    "def": "baseDef",
    "spAtk": "baseSpAtk",
    "spDef": "baseSpDef",
    "speed": "baseSpeed",
}
QUALITY_EXP = {"hp": 0.95, "speed": 0.95, "atk": 0.8, "def": 0.8, "spAtk": 0.8, "spDef": 0.8}
RANDOM_MEAN = 0.925  # aleatório(0,85–1,00)
MIN_HIT_INTERVAL_S = 0.9
BASIC_POWER = 30
BASIC_INTERVAL_S = 2.0
SPEED_CAP_PCT = 7.0
# faixas de qualidade do sorteio (wiki, Stats): (mínimo, máximo, chance em %)
QUALITY_BANDS = (
    (0.8, 0.9, 5),
    (0.9, 1.0, 5),
    (1.0, 1.1, 34.03846),
    (1.1, 1.2, 20),
    (1.2, 1.3, 10),
    (1.3, 1.4, 10),
    (1.4, 1.5, 10),
    (1.5, 1.6, 5),
    (1.7, 1.8, 0.67308),
    (1.8, 1.8, 0.28846),
)
DIAGONAL = {
    "FIRE": 0.5,
    "WATER": 0.5,
    "ELECTRIC": 0.5,
    "GRASS": 0.5,
    "ICE": 0.5,
    "POISON": 0.5,
    "PSYCHIC": 0.5,
    "DARK": 0.5,
    "STEEL": 0.5,
    "GHOST": 2,
    "DRAGON": 2,
}


@dataclass(frozen=True)
class Move:
    name: str
    power: float
    type: str
    category: str  # "PHYSICAL" | "SPECIAL"
    cooldown_ms: float
    learn_level: int = 1


@dataclass(frozen=True)
class SpeciesData:
    id: int
    name: str | None
    types: tuple[str, ...]
    base: dict[str, float]
    moves: tuple[Move, ...] = ()

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> SpeciesData:
        moves = []
        for a in raw.get("attacks") or []:
            if not isinstance(a, dict) or not a.get("power"):
                continue
            moves.append(
                Move(
                    name=str(a.get("name")),
                    power=float(a["power"]),
                    type=str(a.get("type") or "NORMAL").upper(),
                    category=str(a.get("category") or "PHYSICAL").upper(),
                    cooldown_ms=float(a.get("cooldownMs") or cooldown_of_power(a["power"])),
                    learn_level=int(a.get("learnLevel") or 1),
                )
            )
        types = tuple(t.upper() for t in (raw.get("type1"), raw.get("type2")) if t)
        return cls(
            id=int(raw.get("pokeId") or 0),
            name=raw.get("name"),
            types=types or ("NORMAL",),
            base={k: float(raw.get(src) or 0) for k, src in BASE_KEYS.items()},
            moves=tuple(moves),
        )


@dataclass(frozen=True)
class Fighter:
    species: SpeciesData
    level: int
    ivs: dict[str, int] = field(default_factory=lambda: {s: 16 for s in STATS})
    quality: float = 1.0
    multiplier: float = 1.0  # (1 + bônus da potência) × shiny × lendário

    def stats(self) -> dict[str, int]:
        out = {}
        for s in STATS:
            raw = (self.species.base[s] + 2 * self.ivs.get(s, 16)) * self.level / 100
            out[s] = round(raw * self.quality ** QUALITY_EXP[s] * self.multiplier)
        return out


def cooldown_of_power(power: float) -> float:
    """Recarga do golpe pelo poder (cooldown-golpes.mjs), em ms."""
    p = max(15.0, float(power))
    seg = 10 + (p - 15) * 20 / 85 if p <= 100 else 30 + (p - 100) * 30 / 500
    return round(seg * 10) * 100


def speed_discount_pct(speed_base: float, iv_speed: int) -> float:
    s = max(0.0, speed_base)
    pct = s / 20 if s <= 120 else 6 + (s - 120) / 40
    return min(SPEED_CAP_PCT, pct) * (min(32, max(1, iv_speed)) / 32)


def combat_hp(hp_stat: int) -> int:
    return max(24, round(hp_stat * 12))


def hunt_effectiveness(value: float, amplification: float) -> float:
    if value in (0, 1):
        return value
    return 1 + (value - 1) * amplification if value > 1 else value / amplification


def effectiveness(
    move_type: str,
    def_types: tuple[str, ...],
    table: dict[str, dict[str, float]],
    amplification: float,
) -> float:
    row = table.get(move_type, {})
    v = 1.0
    for d in dict.fromkeys(def_types):
        v *= DIAGONAL.get(move_type, 1.0) if d == move_type else row.get(d, 1.0)
    return hunt_effectiveness(v, amplification)


def hit_damage(
    level: int, power: float, attack: float, defense: float, stab: bool, eff: float
) -> float:
    base = ((2 * level / 5 + 2) * power * attack / max(1.0, defense)) / 50 + 2
    return base * (1.5 if stab else 1.0) * eff * RANDOM_MEAN


@dataclass(frozen=True)
class WaveModel:
    """Ritmo da cena (o mesmo em todas as áreas): medido nos dados (ver o design)."""

    size: float = 8.0  # selvagens por onda
    walk_s: float = 2.0  # caminhada média até o próximo selvagem
    gap_s: float = 11.0  # espera entre o último abate e o primeiro da onda seguinte


@dataclass(frozen=True)
class Rules:
    table: dict[str, dict[str, float]]
    amplification: float = 1.5
    wild_hp_mult: float = 5.0
    potencies: tuple[tuple[float, float], ...] = ((0.0, 100.0),)  # (bônus, chance %)

    @classmethod
    def from_welcome(cls, rules: dict[str, Any]) -> Rules:
        pots = tuple(
            (float(p.get("bonus") or 0), float(p.get("chance") or 0))
            for p in rules.get("potencias") or []
            if isinstance(p, dict)
        )
        return cls(
            table={
                k.upper(): {d.upper(): float(v) for d, v in row.items()}
                for k, row in (rules.get("tabelaTipos") or {}).items()
            },
            amplification=float(rules.get("ampliacaoHunt") or 1.5),
            wild_hp_mult=float(rules.get("multHpSelvagem") or 5),
            potencies=pots or ((0.0, 100.0),),
        )


def _pick(rng: random.Random, weighted: list[tuple[Any, float]]) -> Any:
    total = sum(w for _, w in weighted)
    x = rng.uniform(0, total)
    for v, w in weighted:
        x -= w
        if x <= 0:
            return v
    return weighted[-1][0]


def random_wild(species: SpeciesData, level: int, rules: Rules, rng: random.Random) -> Fighter:
    """Selvagem pela distribuição do jogo: IV 1–32, qualidade pelas faixas, potência pela tabela."""
    lo, hi = _pick(rng, [((a, b), w) for a, b, w in QUALITY_BANDS])
    bonus = _pick(rng, list(rules.potencies))
    return Fighter(
        species=species,
        level=level,
        ivs={s: rng.randint(1, 32) for s in STATS},
        quality=rng.uniform(lo, hi),
        multiplier=1 + bonus,
    )


class Attacker:
    """Estado do pokémon ativo durante a hunt: as recargas continuam de um selvagem para o outro."""

    def __init__(self, fighter: Fighter, rules: Rules) -> None:
        self.f = fighter
        self.rules = rules
        self.st = fighter.stats()
        disc = speed_discount_pct(fighter.species.base["speed"], fighter.ivs.get("speed", 16))
        self.moves = [
            (m, m.cooldown_ms / 1000 * (1 - disc / 100))
            for m in fighter.species.moves
            if m.learn_level <= fighter.level
        ]
        self.ready_at = {m.name: 0.0 for m, _ in self.moves}
        self.basic_every = max(
            MIN_HIT_INTERVAL_S, BASIC_INTERVAL_S - 0.01 * fighter.ivs.get("speed", 16)
        )
        self.basic_at = 0.0

    def _damage(
        self,
        power: float,
        mtype: str,
        category: str,
        wild_types: tuple[str, ...],
        wild_st: dict[str, int],
        stab: bool | None = None,
    ) -> float:
        physical = category == "PHYSICAL"
        a = self.st["atk"] if physical else self.st["spAtk"]
        d = wild_st["def"] if physical else wild_st["spDef"]
        eff = effectiveness(mtype, wild_types, self.rules.table, self.rules.amplification)
        stab = mtype in self.f.species.types if stab is None else stab
        return hit_damage(self.f.level, power, a, d, stab, eff)

    def _basic_type(self, wild_types: tuple[str, ...]) -> str:
        for t in self.f.species.types:
            if effectiveness(t, wild_types, self.rules.table, self.rules.amplification) > 0:
                return t
        return self.f.species.types[0]

    def kill(self, wild: Fighter, t: float) -> float:
        """Luta contra `wild` a partir do instante `t`; devolve o instante do abate."""
        wst = wild.stats()
        hp = combat_hp(wst["hp"]) * self.rules.wild_hp_mult
        wtypes = wild.species.types
        dmg = {
            m.name: self._damage(m.power, m.type, m.category, wtypes, wst) for m, _ in self.moves
        }
        btype = self._basic_type(wtypes)
        basic = self._damage(BASIC_POWER, btype, "PHYSICAL", wtypes, wst, stab=True)
        if max([basic, *dmg.values()]) <= 0:
            return float("inf")
        while hp > 0:
            ready = [(dmg[m.name], m, cd) for m, cd in self.moves if self.ready_at[m.name] <= t]
            if ready:
                d, m, cd = max(ready, key=lambda x: x[0])
                hp -= d
                self.ready_at[m.name] = t + cd
            elif self.basic_at <= t:
                hp -= basic
                self.basic_at = t + self.basic_every
            else:
                t = min([self.basic_at, *self.ready_at.values()])
                continue
            if hp > 0:
                t += MIN_HIT_INTERVAL_S
        return t


def kills_per_hour(
    attacker: Fighter,
    wild_species: SpeciesData,
    hunt_level: int,
    rules: Rules,
    waves: WaveModel = WaveModel(),
    n_kills: int = 400,
    seed: int = 7,
) -> float:
    """Abates/h simulando `n_kills` selvagens sorteados, em ondas, com recargas contínuas."""
    rng = random.Random(seed)
    att = Attacker(attacker, rules)
    t = 0.0
    in_wave = 0
    for _ in range(n_kills):
        t += waves.walk_s
        t = att.kill(random_wild(wild_species, hunt_level, rules, rng), t)
        if t == float("inf"):
            return 0.0
        in_wave += 1
        if in_wave >= waves.size:
            t += waves.gap_s
            in_wave = 0
    return n_kills * 3600 / t
