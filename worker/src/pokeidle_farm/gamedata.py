"""Dados do jogo para a fase 3b: catálogo de hunts e Pokedex.

Ver docs/design/fase-3b-catalogo-e-fila.md.

- `HuntCatalog`: hunts, tabela de captura e bolas, montados do `welcome`.
- `SpeciesCatalog`: Pokedex montada dos `creatures*.json` públicos do jogo, com o
  estágio evolutivo de cada espécie (o `welcome` não traz isso).
- `save_hunt_catalog` e `SpeciesSync`: gravam no store só quando a `version` muda.
- `ItemsSync` e `save_welcome_items` (fase 7): catálogo de itens do `items.json` público
  e dos `itensNossos` do `welcome`, para dar preço aos drops pelo nome.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .store.base import Store

log = logging.getLogger(__name__)

Stage = Literal["first_of_three", "middle", "last"]
STAGES: tuple[Stage, ...] = ("first_of_three", "middle", "last")

SPECIES_FILES = (
    "creatures",
    "creatures-novos",
    "creatures-outland-novos",
    "creatures-formas",
)
SPECIES_BASE_URL = "https://pokeidle.io/assets"


def stable_version(*parts: Any) -> str:
    """sha256 do JSON com chaves ordenadas: a mesma informação dá a mesma versão."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


# --- catálogo de hunts -------------------------------------------------------------


@dataclass(frozen=True)
class Hunt:
    slug: str
    name: str | None
    area: str | None
    region: str | None
    level: int
    species_id: int
    species_name: str | None
    total_spawns: int | None


@dataclass(frozen=True)
class CaptureTable:
    base: float
    floor: float
    ceiling: float
    by_step: tuple[float, ...]  # fatores em ordem crescente: 1º de três, meio, última

    def chance(self, catch_rate: float, stage: Stage | None) -> float:
        """Chance com o selvagem derrubado (hp 0, multiplicador 1,4). Sem estágio: a pior."""
        if stage in STAGES and len(self.by_step) == len(STAGES):
            factor = self.by_step[STAGES.index(stage)]
        else:
            factor = self.by_step[-1]
        return self.clamp(self.base * catch_rate / factor * 1.4)

    def clamp(self, chance: float) -> float:
        return min(max(chance, self.floor), self.ceiling)


@dataclass(frozen=True)
class BallInfo:
    id: int
    name: str | None
    catch_rate: float
    price: int | None


@dataclass
class HuntCatalog:
    hunts: dict[str, Hunt] = field(default_factory=dict)
    capture: CaptureTable | None = None
    balls: dict[int, BallInfo] = field(default_factory=dict)
    version: str = ""
    # o JSON como veio, para gravar em game_catalog
    raw_capture: Any = None
    raw_balls: Any = None

    @classmethod
    def from_welcome(cls, raw: dict[str, Any]) -> HuntCatalog:
        hunts_raw = raw.get("hunts") if isinstance(raw.get("hunts"), list) else []
        hunts: dict[str, Hunt] = {}
        for h in hunts_raw:
            parsed = _parse_hunt(h)
            if parsed is not None:
                hunts[parsed.slug] = parsed
        captura = raw.get("captura")
        bolas = raw.get("catalogoBolas")
        return cls(
            hunts=hunts,
            capture=_parse_capture(captura),
            balls=_parse_balls(bolas),
            version=stable_version(hunts_raw, captura, bolas),
            raw_capture=captura,
            raw_balls=bolas,
        )

    def hunt_rows(self) -> list[dict[str, Any]]:
        return [asdict(h) for h in self.hunts.values()]


def _parse_hunt(h: Any) -> Hunt | None:
    if not isinstance(h, dict):
        return None
    slug, level = h.get("slug"), _int(h.get("nivel"))
    especies = h.get("especies")
    if not isinstance(slug, str) or not slug or level is None:
        return None
    if not isinstance(especies, list) or not especies or not isinstance(especies[0], dict):
        return None
    species_id = _int(especies[0].get("pokeId"))
    if species_id is None:
        return None
    return Hunt(
        slug=slug,
        name=h.get("nome"),
        area=h.get("area"),
        region=h.get("regiao") or h.get("area"),
        level=level,
        species_id=species_id,
        species_name=especies[0].get("nome"),
        total_spawns=_int(h.get("totalSpawns")),
    )


def _parse_capture(c: Any) -> CaptureTable | None:
    if not isinstance(c, dict):
        return None
    try:
        steps = c.get("porDegrau") or {}
        by_step = tuple(sorted(float(v) for v in steps.values()))
        if not by_step:
            return None
        return CaptureTable(
            base=float(c["base"]),
            floor=float(c["piso"]),
            ceiling=float(c["teto"]),
            by_step=by_step,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _parse_balls(b: Any) -> dict[int, BallInfo]:
    out: dict[int, BallInfo] = {}
    for item in b if isinstance(b, list) else []:
        if not isinstance(item, dict):
            continue
        bid, rate = _int(item.get("id")), item.get("catchRate")
        if bid is None or not isinstance(rate, int | float) or isinstance(rate, bool):
            continue
        out[bid] = BallInfo(
            id=bid, name=item.get("nome"), catch_rate=float(rate), price=_int(item.get("priceGold"))
        )
    return out


# --- Pokedex ---------------------------------------------------------------------


@dataclass(frozen=True)
class Species:
    id: int
    name: str | None
    type1: str | None
    type2: str | None
    rarity: str | None
    hunt_level: int | None
    evolves_to: int | None
    evolve_level: int | None
    stage: Stage


@dataclass
class SpeciesCatalog:
    species: dict[int, Species] = field(default_factory=dict)
    version: str = ""
    raw: dict[int, dict[str, Any]] = field(default_factory=dict)  # sem loot e attacks

    @classmethod
    def from_creatures(cls, files: list[Any]) -> SpeciesCatalog:
        raw: dict[int, dict[str, Any]] = {}
        for f in files:
            creatures = f.get("creatures") if isinstance(f, dict) else None
            for c in creatures if isinstance(creatures, list) else []:
                pid = _int(c.get("pokeId")) if isinstance(c, dict) else None
                if pid is None or pid in raw:
                    continue  # repetido: vale o primeiro arquivo
                raw[pid] = {k: v for k, v in c.items() if k not in ("loot", "attacks")}

        def target(pid: int) -> int | None:
            to = _int(raw[pid].get("evolvesToId"))
            return to if to and to != pid and to in raw else None

        parents: dict[int, int] = {}
        for pid in raw:
            to = target(pid)
            if to is not None:
                parents.setdefault(to, pid)

        species = {}
        for pid, c in raw.items():
            species[pid] = Species(
                id=pid,
                name=c.get("name"),
                type1=c.get("type1"),
                type2=c.get("type2"),
                rarity=c.get("rarity"),
                hunt_level=_int(c.get("huntLevel")),
                evolves_to=target(pid),
                evolve_level=_int(c.get("evolveLevel")) or None,
                stage=_stage(pid, target, parents),
            )
        return cls(species=species, version=stable_version(sorted(raw.items())), raw=raw)

    def rows(self) -> list[dict[str, Any]]:
        return [
            {
                "species_id": s.id,
                "name": s.name,
                "type1": s.type1,
                "type2": s.type2,
                "rarity": s.rarity,
                "hunt_level": s.hunt_level,
                "evolves_to": s.evolves_to,
                "evolve_level": s.evolve_level,
                "stage": s.stage,
                "data": self.raw[s.id],
            }
            for s in self.species.values()
        ]


def _stage(pid: int, target: Callable[[int], int | None], parents: dict[int, int]) -> Stage:
    seen = {pid}
    up, x = 0, pid
    while (p := parents.get(x)) is not None and p not in seen:
        seen.add(p)
        up, x = up + 1, p
    down, x = 0, pid
    while (t := target(x)) is not None and t not in seen:
        seen.add(t)
        down, x = down + 1, t
    if target(x) is not None:
        return "middle"  # a descida parou num ciclo
    if down == 0:
        return "last"
    if up == 0 and up + down + 1 >= 3:
        return "first_of_three"
    return "middle"


# --- gravação ----------------------------------------------------------------------


async def save_hunt_catalog(store: Store, catalog: HuntCatalog) -> bool:
    """Grava hunts e tabelas se a `version` mudou. Retorna True se gravou."""
    current = await store.get_catalog("hunts")
    if current is not None and current[0] == catalog.version:
        return False
    await store.save_hunt_catalog(
        catalog.version,
        catalog.hunt_rows(),
        {"captura": catalog.raw_capture, "catalogoBolas": catalog.raw_balls},
    )
    return True


HttpGet = Callable[[str, str | None], Awaitable[tuple[int, str | None, bytes]]]


async def http_get(url: str, if_none_match: str | None) -> tuple[int, str | None, bytes]:
    """GET com `If-None-Match` opcional. Retorna (status, etag, corpo)."""
    import httpx

    headers = {"User-Agent": "pokeidle-farm-worker"}
    if if_none_match:
        headers["If-None-Match"] = if_none_match
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        res = await client.get(url, headers=headers)
    return res.status_code, res.headers.get("etag"), res.content


SyncResult = Literal["saved", "unchanged", "failed"]


class SpeciesSync:
    """Mantém a Pokedex em dia com o jogo (GET condicional por ETag).

    Uma por worker. `run_once` na subida e depois a cada `interval_s`.
    """

    def __init__(
        self,
        store: Store,
        http_get: HttpGet,
        *,
        base_url: str = SPECIES_BASE_URL,
        interval_s: float = 24 * 3600,
    ) -> None:
        self.store = store
        self.http_get = http_get
        self.base_url = base_url.rstrip("/")
        self.interval_s = interval_s
        self.catalog: SpeciesCatalog | None = None
        self._etags: dict[str, str] = {}
        self._files: dict[str, Any] = {}

    async def run_once(self) -> SyncResult:
        try:
            changed = await self._fetch_all()
            if self.catalog is not None and not changed:
                return "unchanged"
            catalog = SpeciesCatalog.from_creatures([self._files[n] for n in SPECIES_FILES])
            if not catalog.species:
                raise ValueError("Pokedex vazia")
        except Exception as exc:
            log.warning("species.fetch_failed: %r", exc)
            if self.catalog is None:
                await self._load_saved()
            return "failed"
        self.catalog = catalog
        current = await self.store.get_catalog("species")
        if current is not None and current[0] == catalog.version:
            return "unchanged"
        await self.store.save_species(catalog.version, catalog.rows(), {"etags": self._etags})
        return "saved"

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            result = await self.run_once()
            log.info(
                "Pokedex: %s (%d espécies)",
                result,
                len(self.catalog.species) if self.catalog else 0,
            )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval_s)

    async def _fetch_all(self) -> bool:
        """Baixa o que mudou. True se algum arquivo veio novo."""
        fetched: dict[str, tuple[str | None, Any]] = {}
        for name in SPECIES_FILES:
            have = name in self._files
            status, etag, body = await self.http_get(
                f"{self.base_url}/{name}.json", self._etags.get(name) if have else None
            )
            if status == 304 and have:
                continue
            if status != 200:
                raise ConnectionError(f"{name}.json: HTTP {status}")
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError(f"{name}.json não é um objeto")
            fetched[name] = (etag, data)
        # só aplica se todos deram certo
        for name, (etag, data) in fetched.items():
            self._files[name] = data
            if etag:
                self._etags[name] = etag
        return bool(fetched)

    async def _load_saved(self) -> None:
        rows = await self.store.load_species()
        if rows:
            self.catalog = SpeciesCatalog.from_creatures([{"creatures": rows}])


# --- catálogo de itens (fase 7) ------------------------------------------------------

ITEMS_URL = "https://pokeidle.io/assets/items.json"


def item_rows_from_json(data: Any) -> list[dict[str, Any]]:
    """Linhas de game_items a partir do `items.json` (`{"items": [{id, name, ...}]}`)."""
    items = data.get("items") if isinstance(data, dict) else data
    out: dict[int, dict[str, Any]] = {}
    for it in items or []:
        if not isinstance(it, dict):
            continue
        item_id, name = _int(it.get("id")), it.get("name")
        if item_id is None or not isinstance(name, str) or not name:
            continue
        price = it.get("npcPrice")
        out[item_id] = {
            "item_id": item_id,
            "name": name,
            "category": it.get("category"),
            "rare": bool(it.get("rare")),
            "npc_price": price if isinstance(price, int | float) else None,
        }
    return [out[k] for k in sorted(out)]


def item_rows_from_welcome(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Itens próprios do servidor (`welcome.itensNossos`, ids ≥ 70000), sem preço de NPC."""
    out: dict[int, dict[str, Any]] = {}
    for it in raw.get("itensNossos") or []:
        if not isinstance(it, dict):
            continue
        item_id = _int(it.get("id"))
        name = it.get("nome") or it.get("name")
        if item_id is None or not isinstance(name, str) or not name:
            continue
        out[item_id] = {
            "item_id": item_id,
            "name": name,
            "category": it.get("categoria") or it.get("category"),
            "rare": bool(it.get("raro") or it.get("rare")),
            "npc_price": None,
        }
    return [out[k] for k in sorted(out)]


async def save_items(
    store: Store, source: str, rows: list[dict[str, Any]], meta: Any = None
) -> bool:
    """Grava os itens de uma origem (`json` ou `welcome`) se mudaram. True se gravou."""
    if not rows:
        return False
    version = stable_version(rows)
    current = await store.get_catalog(f"items_{source}")
    if current is not None and current[0] == version:
        return False
    await store.save_items(source, version, rows, meta or {})
    return True


class ItemsSync:
    """Mantém o catálogo de itens em dia com o `items.json` (GET condicional por ETag)."""

    def __init__(
        self,
        store: Store,
        http_get: HttpGet,
        *,
        url: str = ITEMS_URL,
        interval_s: float = 24 * 3600,
    ) -> None:
        self.store = store
        self.http_get = http_get
        self.url = url
        self.interval_s = interval_s
        self._etag: str | None = None

    async def run_once(self) -> SyncResult:
        try:
            status, etag, body = await self.http_get(self.url, self._etag)
            if status == 304 and self._etag:
                return "unchanged"
            if status != 200:
                raise ConnectionError(f"items.json: HTTP {status}")
            rows = item_rows_from_json(json.loads(body))
            if not rows:
                raise ValueError("items.json sem itens")
        except Exception as exc:
            log.warning("items.fetch_failed: %r", exc)
            return "failed"
        saved = await save_items(self.store, "json", rows, {"etag": etag})
        self._etag = etag
        return "saved" if saved else "unchanged"

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            log.info("Itens: %s", await self.run_once())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval_s)


# --- wiki e fórmulas do jogo (análise de 15/11, proposta C) ----------------------------

GAME_BASE_URL = "https://pokeidle.io"
# A wiki (`pokepedia.mjs`, ~1 MB, 45 capítulos) e os módulos com as fórmulas do servidor que
# importam para o farm. Guardados em game_files (o banco é privado; o repositório é público,
# então o conteúdo do jogo não vai para o git).
GAME_FILES = (
    "pokepedia.mjs",
    "shared/loot-pedras.mjs",
    "shared/pedras-evolucao.mjs",
    "shared/taxa-mercado.mjs",
    "shared/recompensa-hunt.mjs",
    "shared/sell-value.mjs",
    "shared/tipo-efetividade.mjs",
    "shared/captura-degrau.mjs",
)


def parse_loot_stones(loot_js: str, stones_js: str) -> dict[str, Any] | None:
    """Constantes das pedras: chance por posição na cadeia e pedra por tipo. None se mudou o formato."""
    import re

    m = re.search(r"CHANCE_PEDRA_POR_ESTAGIO\s*=\s*\[([^\]]*)\]", loot_js)
    t = re.search(r"PEDRA_POR_TIPO\s*=\s*\{([^}]*)\}", stones_js)
    if not m or not t:
        return None
    try:
        # o jogo guarda em porcento (0.2 = 0,2% por abate)
        chances = [round(float(x) / 100, 6) for x in m.group(1).split(",") if x.strip()]
    except ValueError:
        return None
    by_type = dict(re.findall(r"([A-Z]+)\s*:\s*'([^']+)'", t.group(1)))
    if len(chances) != 3 or not by_type:
        return None
    return {"chance_by_position": chances, "stone_by_type": by_type}


class GameFilesSync:
    """Mantém a wiki e as fórmulas do jogo no banco (GET condicional por ETag)."""

    def __init__(
        self,
        store: Store,
        http_get: HttpGet,
        *,
        base_url: str = GAME_BASE_URL,
        files: tuple[str, ...] = GAME_FILES,
        interval_s: float = 24 * 3600,
    ) -> None:
        self.store = store
        self.http_get = http_get
        self.base_url = base_url.rstrip("/")
        self.files = files
        self.interval_s = interval_s
        self._etags: dict[str, str] = {}
        self._content: dict[str, str] = {}

    async def run_once(self) -> SyncResult:
        changed = False
        try:
            for path in self.files:
                status, etag, body = await self.http_get(
                    f"{self.base_url}/{path}",
                    self._etags.get(path) if path in self._content else None,
                )
                if status == 304 and path in self._content:
                    continue
                if status != 200:
                    raise ConnectionError(f"{path}: HTTP {status}")
                text = body.decode("utf-8", errors="replace")
                await self.store.save_game_file(path, etag, text)
                self._content[path] = text
                if etag:
                    self._etags[path] = etag
                changed = True
        except Exception as exc:
            log.warning("game_files.fetch_failed: %r", exc)
            return "failed"
        if not changed:
            return "unchanged"
        loot = parse_loot_stones(
            self._content.get("shared/loot-pedras.mjs", ""),
            self._content.get("shared/pedras-evolucao.mjs", ""),
        )
        if loot is not None:
            await self.store.save_catalog_entry("loot_stones", stable_version(loot), loot)
        else:
            log.warning("game_files: não reconheci as constantes das pedras (o jogo mudou?)")
        return "saved"

    async def run_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            log.info("Arquivos do jogo: %s", await self.run_once())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.interval_s)
