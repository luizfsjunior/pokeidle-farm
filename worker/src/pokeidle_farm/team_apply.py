"""Aplicar uma equipe montada no painel numa ida só ao Pokécenter (docs/design/conta-v2.md, seção 3).

`plan_moves` é puro: recebe a equipe atual e a desejada e devolve os passos na ordem que o jogo aceita.
O ativo fica sempre na equipe: troca de ativo antes de tirar o antigo, e o antigo só sai no fim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TEAM_SLOTS = 5


@dataclass(frozen=True)
class Step:
    kind: Literal["move", "active"]
    pokemon_id: int
    slot: int | None = None

    def label(self) -> str:
        if self.kind == "active":
            return f"ativo {self.pokemon_id}"
        if self.slot is None:
            return f"tirou {self.pokemon_id}"
        return f"{self.pokemon_id} na vaga {self.slot + 1}"


def plan_moves(
    team: dict[int, int], active: int | None, target: list[int | None], target_active: int
) -> list[Step]:
    """`team` é vaga -> id; `target` é a lista de ids por vaga (None = vaga vazia).

    Ordem: o ativo novo entra (numa vaga livre, se a dele estiver ocupada) e vira ativo; quem não fica
    sai; cada um vai para a sua vaga, abrindo-a antes se preciso. Nunca tira o ativo nem põe em vaga
    ocupada.
    """
    where = {pid: slot for slot, pid in team.items()}  # id -> vaga, simulado passo a passo
    wanted = {pid: slot for slot, pid in enumerate(target) if pid is not None}
    steps: list[Step] = []

    def move(pid: int, slot: int | None) -> None:
        steps.append(Step("move", pid, slot))
        where.pop(pid, None)
        if slot is not None:
            where[pid] = slot

    def occupant(slot: int) -> int | None:
        return next((p for p, s in where.items() if s == slot), None)

    def free_slot() -> int | None:
        return next((i for i in range(TEAM_SLOTS) if occupant(i) is None), None)

    if target_active not in where:
        slot = wanted[target_active] if occupant(wanted[target_active]) is None else free_slot()
        if slot is None:  # equipe cheia: abre uma vaga com quem não é o ativo
            spare = [p for p in where if p != active]
            spare.sort(key=lambda p: p in wanted)  # primeiro quem não fica
            move(spare[0], None)
            slot = free_slot()
        move(target_active, slot)
    if active != target_active:
        steps.append(Step("active", target_active))
    active = target_active

    for pid in [p for p in where if p not in wanted]:
        move(pid, None)

    order = sorted(wanted.items(), key=lambda kv: kv[0] != target_active)
    for pid, slot in order:
        if where.get(pid) == slot:
            continue
        other = occupant(slot)
        if other is not None:
            if other == active:  # só acontece antes do ativo ir para a vaga dele, que vem primeiro
                continue
            move(other, None)
        move(pid, slot)
    return steps


def team_by_slot(team: list[dict[str, Any]] | None) -> dict[int, int]:
    out: dict[int, int] = {}
    for m in team or []:
        slot, pid = m.get("slot"), m.get("id")
        if isinstance(slot, int) and isinstance(pid, int):
            out[slot] = pid
    return out
