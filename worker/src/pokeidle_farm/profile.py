"""Perfil da conta para o painel: o `estado` do jogo juntado (welcome + patches) e resumido.

Ver docs/design/painel-perfil.md. O `welcome` traz o estado inteiro; cada `estado` depois traz só o
que mudou: `pkMud` (pokémons alterados, merge por `id`), `pkFora` (ids que saíram), `dexMud`
(Pokédex por espécie) e os mapas `items`/`balls` (parciais). O resto substitui o valor anterior.

O resumo (`summary`) é uma linha de `account_profile`: números da conta, a equipe, os destaques da
coleção e o inventário. Nada de token ou dado de login passa por aqui: só o `estado`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

# campos do pokémon que o painel mostra (o resto do objeto do jogo fica de fora)
POKEMON_FIELDS = {
    "id": "id",
    "speciesId": "species_id",
    "nome": "name",
    "level": "level",
    "shiny": "shiny",
    "slot": "slot",
    "looktype": "looktype",
    "poder": "power",
    "quality": "quality",
    "potencia": "potency",
    "hp": "hp",
    "maxHp": "max_hp",
    "caughtAt": "caught_at",
    # para a ficha do pokémon no painel (nomes vistos no app.js do jogo, 17/11)
    "xp": "xp",
    "xpNivel": "xp_level",
    "xpProximo": "xp_next",
    "apelido": "nickname",
    "skin": "skin",
    "refino": "refine",
    "refinoTotal": "refine_total",
    "tmElemental": "tm_elemental",
    "tmFisico": "tm_physical",
    "tmAoe": "tm_aoe",
    "heldItemId": "held_item_id",
    "caughtBy": "caught_by",
    "levelGinasio": "gym_level",
    "nota": "grade",  # a nota que o jogo calcula (0 a 10)
    "starter": "starter",
    "pasta": "folder",  # a pasta da coleção (o jogo organiza em pastas)
    "travado": "locked",
    "pisoNivel": "min_level",
}
# dicionários pequenos guardados como vieram (IV por stat; stats de combate, se o jogo mandar)
POKEMON_DICTS = {"ivs": "ivs", "stats": "stats"}
MERGED_MAPS = ("items", "balls")
# campos do estado guardados como vieram, para o painel (passe, ginásios, guild...). Um campo maior
# que EXTRA_MAX_BYTES em JSON fica de fora (não deixa a linha crescer sem controle).
EXTRA_KEYS = (
    "passe",
    "ginasios",
    "ginasiosPodio",
    "guild",
    "guildBonusPct",
    "guildBonusRank",
    "caixas",
    "chocadeira",
    "boss",
    "outlandTier",
    "bicicleta",
    "casa",
    "campConquistas",
    "pkCoroa",
    "pkMedalha",
    "bonusXp",
    "xpShare",
    "topMes",
    "evento",
    "safari",
    "mistico",
    "pvp",
    "automation",
    "servidorAgora",
)
LOJA_KEYS = ("vip", "vipAte", "looktype", "gender", "visual")
EXTRA_MAX_BYTES = 20_000
TOP_POKEMON = 24  # destaques da coleção: os mais fortes
TOP_PER_SPECIES = 3  # fora da equipe, no máximo 3 de cada espécie (senão viram 24 Brave Steelix)
MAX_SHINIES = 60


def travado_ids(automation: Any) -> set[int]:
    """A Coleção do jogo: os ids em `estado.automation.pokemonTravado` (app.js, 20/11). Não é um campo
    de cada pokémon; quem está nessa lista não vai na venda do Depot."""
    lst = automation.get("pokemonTravado") if isinstance(automation, dict) else None
    out: set[int] = set()
    for x in lst or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def set_travado(automation: Any, pid: Any, dentro: bool) -> None:
    """Põe ou tira o id da lista (como o `marcarColecaoLocal` do app.js)."""
    if not isinstance(automation, dict):
        return
    arr = automation.setdefault("pokemonTravado", [])
    n = int(pid)
    has = any(_as_int(x) == n for x in arr)
    if dentro and not has:
        arr.append(n)
    elif not dentro and has:
        automation["pokemonTravado"] = [x for x in arr if _as_int(x) != n]


def _as_int(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


class ProfileState:
    """Estado da conta juntado a partir do welcome e dos patches."""

    def __init__(self) -> None:
        self.estado: dict[str, Any] = {}
        self.pokemons: dict[Any, dict[str, Any]] = {}
        self.pokedex: dict[str, Any] = {}
        self.ready = False  # só depois do primeiro welcome
        # o que mudou na coleção desde a última gravação de account_pokemon
        self.changed: set[Any] = set()
        self.removed: set[Any] = set()
        self.full_sync = False

    def apply_snapshot(self, estado: dict[str, Any]) -> None:
        self.estado = {
            k: v for k, v in estado.items() if k not in ("pokemons", "pokedex", "pkMud", "pkFora")
        }
        self.pokemons = {}
        for p in estado.get("pokemons") or []:
            if isinstance(p, dict) and p.get("id") is not None:
                self.pokemons[p["id"]] = dict(p)
        dex = estado.get("pokedex")
        self.pokedex = dict(dex) if isinstance(dex, dict) else {}
        self.ready = True
        self.full_sync = True
        self.changed.clear()
        self.removed.clear()

    def collection_ids(self) -> set[int]:
        return travado_ids(self.estado.get("automation"))

    def in_collection(self, pid: Any) -> bool:
        return int(pid) in self.collection_ids()

    def set_collection(self, pid: Any, dentro: bool) -> None:
        """A marca confirmada pelo jogo (`batalha` k "colecao"), antes de o estado trazer a lista."""
        auto = self.estado.setdefault("automation", {})
        set_travado(auto, pid, dentro)
        if pid in self.pokemons:
            self.changed.add(pid)

    def apply_patch(self, src: dict[str, Any]) -> None:
        before = self.collection_ids() if "automation" in src else None
        for p in src.get("pkMud") or []:
            if isinstance(p, dict) and p.get("id") is not None:
                self.pokemons.setdefault(p["id"], {}).update(p)
                self.changed.add(p["id"])
                self.removed.discard(p["id"])
        for pid in src.get("pkFora") or []:
            self.pokemons.pop(pid, None)
            self.removed.add(pid)
            self.changed.discard(pid)
        dex = src.get("dexMud")
        if isinstance(dex, dict):
            for key, entry in dex.items():
                cur = self.pokedex.get(key)
                if isinstance(cur, dict) and isinstance(entry, dict):
                    self.pokedex[key] = {**cur, **entry}
                else:
                    self.pokedex[key] = entry
        for key, value in src.items():
            if key in ("pkMud", "pkFora", "dexMud", "pokemons", "pokedex"):
                continue
            if key in MERGED_MAPS and isinstance(value, dict):
                cur = self.estado.get(key)
                self.estado[key] = {**(cur if isinstance(cur, dict) else {}), **value}
            else:
                self.estado[key] = value
        if before is not None:  # quem entrou ou saiu da Coleção: a linha dele muda
            moved = before ^ self.collection_ids()
            self.changed.update(pid for pid in self.pokemons if _as_int(pid) in moved)

    def collection_rows(self, account_id: str) -> tuple[list[dict[str, Any]], list[int], bool]:
        """O que gravar em account_pokemon: (linhas, ids que saíram, sincronização completa).

        Zera o que estava pendente; quem chama devolve com `requeue` se a gravação falhar.
        """
        full = self.full_sync
        ids = list(self.pokemons) if full else [i for i in self.changed if i in self.pokemons]
        coll = self.collection_ids()
        rows = []
        for pid in ids:
            p = self.pokemons[pid]
            c = compact_pokemon(p)
            c["in_collection"] = _as_int(pid) in coll
            rows.append(
                {
                    "account_id": account_id,
                    "pokemon_id": int(pid),
                    "species_id": c.get("species_id"),
                    "slot": c.get("slot"),
                    "data": c,
                }
            )
        removed = [int(i) for i in self.removed]
        self.full_sync = False
        self.changed.clear()
        self.removed.clear()
        return rows, removed, full

    def requeue(self, rows: list[dict[str, Any]], removed: list[int], full: bool) -> None:
        self.full_sync = self.full_sync or full
        self.changed.update(r["pokemon_id"] for r in rows)
        self.removed.update(removed)

    def summary(self, now: datetime | None = None) -> dict[str, Any]:
        """Linha de `account_profile` (sem `account_id`)."""
        est = self.estado
        pks = [compact_pokemon(p) for p in self.pokemons.values()]
        team = sorted((p for p in pks if p.get("slot") is not None), key=lambda p: p["slot"])
        strongest = sorted(
            pks, key=lambda p: (p.get("power") or 0, p.get("level") or 0), reverse=True
        )
        shinies = [p for p in strongest if p.get("shiny")]
        caught = sum(1 for e in self.pokedex.values() if _dex_caught(e))
        return {
            "updated_at": (now or datetime.now(UTC)).isoformat(),
            "level": _int(est.get("level")),
            "xp": _num(est.get("xp")),
            "xp_level": _num(est.get("xpNivel")),
            "xp_next": _num(est.get("xpProximo")),
            "gold": _num(est.get("gold")),
            "gems": _num(est.get("orbs")),
            "diamonds": _num(est.get("diamonds", est.get("diamantes"))),
            "vip_until": _ms_to_iso(_dict(est.get("loja")).get("vipAte")),
            "hunt_slug": est.get("huntSlug") if isinstance(est.get("huntSlug"), str) else None,
            "active_pokemon_id": _int(est.get("activeId")),
            "pokemon_count": len(pks),
            "shiny_count": len(shinies),
            "dex_seen": len(self.pokedex),
            "dex_caught": caught,
            "team": team,
            "top_pokemon": _varied(strongest, TOP_POKEMON),
            "shinies": shinies[:MAX_SHINIES],
            "items": _positive(est.get("items")),
            "balls": _positive(est.get("balls")),
            # só os nomes dos campos, para descobrir o que mais dá para mostrar
            "estado_keys": sorted(est),
            "extra": self._extra(),
            # Pokédex completa: {speciesId: entrada do jogo} (c = capturas)
            "pokedex": self.pokedex,
        }

    def _extra(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in EXTRA_KEYS:
            value = self.estado.get(key)
            if value is not None and len(json.dumps(value, default=str)) <= EXTRA_MAX_BYTES:
                out[key] = value
        # os nomes dos campos dos pokémons, para descobrir o que mais dá para mostrar na ficha
        keys: set[str] = set()
        for p in self.pokemons.values():
            keys.update(str(k) for k in p)
        out["pokemon_keys"] = sorted(keys)
        loja = _dict(self.estado.get("loja"))
        out["loja"] = {k: loja[k] for k in LOJA_KEYS if k in loja}
        return out


def compact_pokemon(p: dict[str, Any]) -> dict[str, Any]:
    out = {
        dst: p[src]
        for src, dst in POKEMON_FIELDS.items()
        if p.get(src) is not None
        and not isinstance(p[src], list)
        and (not isinstance(p[src], dict) or len(p[src]) <= 12)
    }
    for src, dst in POKEMON_DICTS.items():
        value = p.get(src)
        if isinstance(value, dict) and all(isinstance(v, int | float) for v in value.values()):
            out[dst] = dict(value)
    ivs = p.get("ivs")
    if isinstance(ivs, dict):
        out["iv_sum"] = sum(v for v in ivs.values() if isinstance(v, int | float))
    return out


def _dex_caught(entry: Any) -> bool:
    if isinstance(entry, dict):
        return bool(entry.get("c"))
    return bool(entry)


def _positive(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(k): int(v) for k, v in value.items() if isinstance(v, int | float) and v > 0}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _ms_to_iso(value: Any) -> str | None:
    if not isinstance(value, int | float) or isinstance(value, bool) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, UTC).isoformat()


def _varied(strongest: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Os mais fortes, com no máximo TOP_PER_SPECIES de cada espécie fora da equipe."""
    out: list[dict[str, Any]] = []
    seen: dict[Any, int] = {}
    for p in strongest:
        if p.get("slot") is None:
            key = p.get("species_id") or p.get("name")
            if seen.get(key, 0) >= TOP_PER_SPECIES:
                continue
            seen[key] = seen.get(key, 0) + 1
        out.append(p)
        if len(out) >= n:
            break
    return out
