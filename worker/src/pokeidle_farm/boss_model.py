"""Bosses lendários: qual boss lutar hoje e se a equipe aguenta (épico C4).

Fontes (lidas em 27/11): o welcome traz `bossesJogaveis` (um por boss: `key`, `regiao`, `degrau`,
`posicao` no trio, `entrada` {itemId, qtd}, `teamLevel`, `equipeIdeal`, `minNivelTreinador`);
`shared/bosses-lendarios.mjs` gira o prêmio do trio todo dia sazonal; o `app.js` calcula a penalidade
da equipe (`penalidadeDaMinhaEquipe`):

    força = Σ min(1, nível / teamLevel) dos pokémons da equipe
    multiplicador do dano tomado = 3 ^ max(0, equipeIdeal − força)

Com 5 pokémons no nível do boss a força é 5 e o multiplicador é 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

Prize = Literal["tm", "mega", "tickets"]
PRIZES: tuple[Prize, ...] = ("tm", "mega", "tickets")  # PREMIOS_DA_TRINCA
ROTATION_DAY_ZERO = "2026-11-17"  # ROTACAO_BOSS_DIA_ZERO
# o dia sazonal vira às 18:00 de Brasília = 21:00 UTC (dia-sazonal.mjs; web/lib/bosses.ts)
SEASON_SHIFT = timedelta(hours=3)


@dataclass(frozen=True)
class Boss:
    key: str
    name: str
    region: str
    step: int  # degrau (Kanto 0, Johto 1...)
    position: int  # posição no trio (gira o prêmio)
    entry_item: int
    entry_qty: int
    team_level: int
    ideal: int
    min_trainer: int


def bosses(rules: dict[str, Any] | None) -> list[Boss]:
    out: list[Boss] = []
    for b in (rules or {}).get("bossesJogaveis") or []:
        if not isinstance(b, dict) or not isinstance(b.get("key"), str):
            continue
        raw_entry = b.get("entrada")
        entry: dict[str, Any] = raw_entry if isinstance(raw_entry, dict) else {}
        try:
            out.append(
                Boss(
                    key=b["key"],
                    name=str(b.get("nome") or b["key"]),
                    region=str(b.get("regiao") or ""),
                    step=int(b.get("degrau") or 0),
                    position=int(b.get("posicao") or 0),
                    entry_item=int(entry.get("itemId") or 70000),
                    entry_qty=int(entry.get("qtd") or 1),
                    team_level=int(b.get("teamLevel") or b.get("level") or 0),
                    ideal=int(b.get("equipeIdeal") or 5),
                    min_trainer=int(b.get("minNivelTreinador") or b.get("level") or 0),
                )
            )
        except (TypeError, ValueError):
            continue
    return out


def _days(key: str) -> int:
    return (datetime.fromisoformat(key).date() - datetime(1970, 1, 1).date()).days


def rotation_day(now: datetime, season_key: str | None = None) -> int:
    """`diaDaRotacaoBoss`: pela chave do dia sazonal do estado se houver, senão pelo relógio."""
    if isinstance(season_key, str):
        try:
            return (_days(season_key) - _days(ROTATION_DAY_ZERO)) % len(PRIZES)
        except ValueError:
            pass
    day = (now.astimezone(UTC) + SEASON_SHIFT).date()
    return ((day - datetime.fromisoformat(ROTATION_DAY_ZERO).date()).days) % len(PRIZES)


def prize_of(boss: Boss, day: int) -> Prize:
    """`premioDaPosicaoNoDia`."""
    return PRIZES[(boss.position - day) % len(PRIZES)]


def penalty(levels: list[int], team_level: int, ideal: int) -> tuple[float, float]:
    """(força, multiplicador do dano tomado), como o `penalidadeDaMinhaEquipe` do app.js."""
    if team_level <= 0:
        return float(len(levels)), 1.0
    force = sum(min(1.0, max(0, lv) / team_level) for lv in levels)
    return force, 3 ** max(0.0, ideal - force)


@dataclass(frozen=True)
class Choice:
    boss: Boss | None
    reason: str  # "ok" ou por que não
    mult: float | None = None
    tokens: int = 0

    @property
    def ok(self) -> bool:
        return self.boss is not None and self.reason == "ok"


def choose(
    rules: dict[str, Any] | None,
    *,
    trainer_level: int | None,
    team_levels: list[int],
    items: dict[str, int] | None,
    prize: Prize,
    region: str = "auto",
    max_mult: float = 1.0,
    min_tokens: int = 1,
    now: datetime,
    season_key: str | None = None,
) -> Choice:
    """O boss do prêmio pedido na região mais alta em que o treinador entra e a equipe aguenta.

    `region` fixa a região ("kanto", "johto"...); "auto" escolhe a mais alta que passa nos dois testes.
    """
    all_ = bosses(rules)
    if not all_:
        return Choice(None, "sem_catalogo")
    day = rotation_day(now, season_key)
    regions = sorted({(b.step, b.region) for b in all_}, reverse=True)
    if region != "auto":
        regions = [r for r in regions if r[1] == region]
        if not regions:
            return Choice(None, "regiao_desconhecida")
    last = Choice(None, "nivel_treinador")
    for step, reg in regions:
        trio = [b for b in all_ if b.region == reg and b.step == step]
        boss = next((b for b in trio if prize_of(b, day) == prize), None)
        if boss is None:
            continue
        if (trainer_level or 0) < boss.min_trainer:
            last = Choice(boss, "nivel_treinador")
            continue
        _, mult = penalty(team_levels, boss.team_level, boss.ideal)
        tokens = int((items or {}).get(str(boss.entry_item), 0) or 0)
        if mult > max_mult + 1e-9:
            last = Choice(boss, "equipe_fraca", mult, tokens)
            continue
        if tokens < max(min_tokens, boss.entry_qty):
            return Choice(boss, "sem_token", mult, tokens)
        return Choice(boss, "ok", mult, tokens)
    return last
