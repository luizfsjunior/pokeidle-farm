"""Pokémon protegidos (épico C1, docs/design/protegidos-e-bosses.md).

Um pokémon protegido nunca é vendido, mandado para o Depot, oferecido, sacrificado ou trocado por
automação nenhuma. A regra é uma só, aqui, e todo caminho que tira um pokémon da conta passa por ela.

Motivos:
- `manual`: marcado no painel (tabela `protected_pokemon`);
- `shiny`: todo shiny, sempre;
- `equipe`: quem está na equipe (a equipe é a que luta nos bosses);
- `colecao`: quem está na Coleção do jogo (`automation.pokemonTravado`), que a venda do Depot já não leva.

Os três primeiros são "firmes": nem o painel manda para o Depot sem tirar a marca antes. A Coleção é a
marca que o próprio jogador mexe: mandar para o Depot pelo painel tira esse motivo, e é para isso mesmo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

Reason = Literal["manual", "shiny", "equipe", "colecao"]
FIRM: tuple[Reason, ...] = ("manual", "shiny", "equipe")


def reasons(
    mon: Mapping[str, Any] | None,
    pid: int,
    *,
    manual: Iterable[int] = (),
    collection: Iterable[int] = (),
) -> list[Reason]:
    """Por que o pokémon `pid` está protegido (lista vazia: não está)."""
    out: list[Reason] = []
    if pid in set(manual):
        out.append("manual")
    if mon is not None:
        if mon.get("shiny"):
            out.append("shiny")
        if mon.get("slot") is not None:
            out.append("equipe")
    if pid in set(collection):
        out.append("colecao")
    return out


def is_protected(
    mon: Mapping[str, Any] | None,
    pid: int,
    *,
    manual: Iterable[int] = (),
    collection: Iterable[int] = (),
    firm_only: bool = False,
) -> bool:
    """A pergunta que todo plugin de venda, sacrifício, oferenda ou troca faz antes de agir.

    `firm_only`: ignora a Coleção (para decidir se o painel pode mandar para o Depot)."""
    got = reasons(mon, pid, manual=manual, collection=() if firm_only else collection)
    return bool(got)


def keeps_out_of_depot(mon: Mapping[str, Any] | None, pid: int, manual: Iterable[int]) -> bool:
    """Marcado no painel ou shiny: não vai para o Depot (nem pelo painel, nem saindo da equipe). A
    equipe não entra aqui: quem sai dela já não é da equipe, e quem está nela não é vendido."""
    return bool({"manual", "shiny"} & set(reasons(mon, pid, manual=manual)))


def needs_mirror(
    mons: Mapping[Any, Mapping[str, Any]], manual: Iterable[int], collection: Iterable[int]
) -> list[int]:
    """Protegidos firmes fora da equipe que ainda não estão na Coleção do jogo: a venda do Depot (a
    nossa e a Auto Venda do jogo) levaria. Os shiny primeiro, depois os manuais, por id."""
    coll = set(collection)
    man = set(manual)
    out: list[tuple[int, int]] = []
    for key, mon in mons.items():
        pid = _as_int(key)
        if pid is None or pid in coll or mon.get("slot") is not None:
            continue
        if mon.get("shiny"):
            out.append((0, pid))
        elif pid in man:
            out.append((1, pid))
    return [pid for _, pid in sorted(out)]


def _as_int(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None
