"""Catálogo de hunts, Pokedex e gravação (docs/design/fase-3b-catalogo-e-fila.md, casos 1 a 12)."""

import json

import pytest

from pokeidle_farm.gamedata import (
    BallInfo,
    CaptureTable,
    Hunt,
    HuntCatalog,
    SpeciesCatalog,
    SpeciesSync,
    save_hunt_catalog,
)
from pokeidle_farm.store.memory import MemoryStore

# --- frames no formato real (welcome de 12/11 e creatures.json de 14/11) ---------

TREECKO = {
    "area": "orre",
    "nome": "Treecko",
    "slug": "treecko_hoenn",
    "nivel": 500,
    "pixel": [550, 50],
    "regiao": "hoenn",
    "especies": [{"nome": "Treecko", "pokeId": 13252, "pontos": 16}],
    "looktype": 60252,
    "totalSpawns": 16,
}
CATERPIE = {
    "area": "kanto",
    "nome": "Caterpie",
    "slug": "caterpie",
    "nivel": 1,
    "especies": [{"nome": "Caterpie", "pokeId": 10, "pontos": 15}],
    "totalSpawns": 15,
}
MAGIKARP = {**CATERPIE, "nome": "Magikarp", "slug": "magikarp"}
MAGIKARP["especies"] = [{"nome": "Magikarp", "pokeId": 129, "pontos": 15}]
CAPTURA = {
    "base": 0.0075,
    "piso": 0.003,
    "teto": 0.1,
    "porDegrau": {"20": 2.8669, "40": 3.5745, "100": 4.4681},
    "raridadeDiv": 17,
    "precoSemPreco": 787928,
}
BOLAS = [
    {"id": 1, "nome": "Poke Ball", "catchRate": 1, "compravel": True, "priceGold": 5},
    {"id": 2, "nome": "Great Ball", "catchRate": 2, "compravel": True, "priceGold": 20},
    {"id": 3, "nome": "Super Ball", "catchRate": 3, "compravel": True, "priceGold": 50},
    {"id": 4, "nome": "Ultra Ball", "catchRate": 4, "compravel": True, "priceGold": 130},
    {
        "id": 5,
        "nome": "Beast Ball",
        "icone": "/img/ball-beast.png",
        "catchRate": 8,
        "compravel": False,
    },
]


def welcome_raw(hunts=None, captura=CAPTURA, bolas=BOLAS) -> dict:
    raw = {"t": "welcome", "estado": {"level": 6}}
    if hunts is not None:
        raw["hunts"] = hunts
    if captura is not None:
        raw["captura"] = captura
    if bolas is not None:
        raw["catalogoBolas"] = bolas
    return raw


def creature(pid, name, evolves_to=0, **extra) -> dict:
    return {
        "pokeId": pid,
        "name": name,
        "type1": extra.pop("type1", "BUG"),
        "rarity": "COMMON",
        "huntLevel": extra.pop("huntLevel", 1),
        "evolvesToId": evolves_to,
        "evolveLevel": 10 if evolves_to else 0,
        "priceNpc": 80,
        "experience": 8,
        "loot": [{"name": "Bug Gosme", "chance": 95000}],
        "attacks": [{"name": "String Shot", "power": 56}],
        **extra,
    }


KANTO = [
    creature(10, "Caterpie", 11),
    creature(11, "Metapod", 12, huntLevel=10),
    creature(12, "Butterfree", 0, type2="FLYING", huntLevel=30),
    creature(128, "Tauros", 0, type1="NORMAL", huntLevel=60),
    creature(129, "Magikarp", 130, type1="WATER"),
    creature(130, "Gyarados", 0, type1="WATER", type2="FLYING", huntLevel=100),
]


# --- catálogo de hunts -----------------------------------------------------------


def test_hunt_complete():
    cat = HuntCatalog.from_welcome(welcome_raw([TREECKO]))
    assert cat.hunts["treecko_hoenn"] == Hunt(
        slug="treecko_hoenn",
        name="Treecko",
        area="orre",
        region="hoenn",
        level=500,
        species_id=13252,
        species_name="Treecko",
        total_spawns=16,
    )


def test_hunt_without_region_uses_area():
    cat = HuntCatalog.from_welcome(welcome_raw([CATERPIE]))
    assert cat.hunts["caterpie"].region == "kanto"


def test_hunt_without_species_or_malformed_is_skipped():
    bad = [
        {**CATERPIE, "slug": "vazia", "especies": []},
        {k: v for k, v in CATERPIE.items() if k != "slug"},
        {**CATERPIE, "slug": "nivel_ruim", "nivel": "x"},
        "não é dict",
    ]
    cat = HuntCatalog.from_welcome(welcome_raw([*bad, CATERPIE]))
    assert list(cat.hunts) == ["caterpie"]


def test_capture_table_and_balls():
    cat = HuntCatalog.from_welcome(welcome_raw([CATERPIE]))
    assert cat.capture == CaptureTable(
        base=0.0075, floor=0.003, ceiling=0.1, by_step=(2.8669, 3.5745, 4.4681)
    )
    assert cat.balls[4] == BallInfo(id=4, name="Ultra Ball", catch_rate=4, price=130)
    assert cat.balls[5].price is None


def test_welcome_without_tables_is_empty():
    cat = HuntCatalog.from_welcome({"t": "welcome", "estado": {}})
    assert cat.hunts == {} and cat.balls == {} and cat.capture is None


def test_hunt_version_is_stable():
    a = HuntCatalog.from_welcome(welcome_raw([CATERPIE, TREECKO]))
    shuffled = [dict(reversed(list(h.items()))) for h in (CATERPIE, TREECKO)]
    b = HuntCatalog.from_welcome(welcome_raw(shuffled))
    c = HuntCatalog.from_welcome(welcome_raw([{**CATERPIE, "nivel": 2}, TREECKO]))
    assert a.version == b.version
    assert a.version != c.version


# --- Pokedex ---------------------------------------------------------------------


def test_species_stages():
    sp = SpeciesCatalog.from_creatures([{"creatures": KANTO}]).species
    assert sp[10].stage == "first_of_three"
    assert sp[11].stage == "middle"
    assert sp[12].stage == "last"
    assert sp[129].stage == "middle"
    assert sp[130].stage == "last"
    assert sp[128].stage == "last"
    assert sp[12].type2 == "FLYING" and sp[10].evolves_to == 11 and sp[12].evolves_to is None


def test_species_link_to_missing_is_no_evolution():
    sp = SpeciesCatalog.from_creatures([{"creatures": [creature(1, "A", 99999)]}]).species
    assert sp[1].stage == "last" and sp[1].evolves_to is None


def test_species_cycle_does_not_hang():
    sp = SpeciesCatalog.from_creatures(
        [{"creatures": [creature(1, "A", 2), creature(2, "B", 1)]}]
    ).species
    assert sp[1].stage == "middle" and sp[2].stage == "middle"


def test_species_files_are_merged_in_order():
    novos = {"_leia": "texto", "creatures": [creature(13252, "Treecko"), creature(10, "Outro")]}
    cat = SpeciesCatalog.from_creatures([{"creatures": KANTO}, novos, {"_leia": "sem creatures"}])
    assert cat.species[13252].name == "Treecko"
    assert cat.species[10].name == "Caterpie"  # repetido: vale o primeiro arquivo


def test_species_version_and_row_without_loot():
    a = SpeciesCatalog.from_creatures([{"creatures": KANTO}])
    b = SpeciesCatalog.from_creatures([{"creatures": list(reversed(KANTO))}])
    assert a.version == b.version
    row = a.rows()[0]
    assert "loot" not in row["data"] and "attacks" not in row["data"]
    assert set(row) >= {"species_id", "name", "stage", "evolves_to", "data"}


# --- gravação --------------------------------------------------------------------


async def test_hunt_catalog_saved_only_when_changed():
    store = MemoryStore()
    one = HuntCatalog.from_welcome(welcome_raw([CATERPIE, TREECKO]))
    assert await save_hunt_catalog(store, one) is True
    assert await save_hunt_catalog(store, one) is False  # mesma version no store
    assert set(store.game_hunts) == {"caterpie", "treecko_hoenn"}
    assert store.game_catalog["captura"]["data"] == CAPTURA

    fewer = HuntCatalog.from_welcome(welcome_raw([CATERPIE]))
    assert await save_hunt_catalog(store, fewer) is True
    assert set(store.game_hunts) == {"caterpie"}  # a que sumiu foi apagada


class FakeHttp:
    """GET falso: responde por arquivo com (status, etag, corpo)."""

    def __init__(self, files: dict[str, dict]) -> None:
        self.files = files
        self.etags = {name: f'W/"{name}-1"' for name in files}
        self.calls: list[tuple[str, str | None]] = []
        self.fail = False

    async def get(self, url: str, if_none_match: str | None) -> tuple[int, str | None, bytes]:
        name = url.rsplit("/", 1)[-1].removesuffix(".json")
        self.calls.append((name, if_none_match))
        if self.fail:
            raise ConnectionError("falha simulada")
        etag = self.etags[name]
        if if_none_match == etag:
            return 304, etag, b""
        return 200, etag, json.dumps(self.files[name]).encode()


FILES = {
    "creatures": {"creatures": KANTO},
    "creatures-novos": {"_leia": "x", "creatures": [creature(13252, "Treecko")]},
    "creatures-outland-novos": {"_leia": "x", "creatures": []},
    "creatures-formas": {"_leia": "x", "creatures": []},
}


async def test_species_sync_conditional_get():
    store = MemoryStore()
    http = FakeHttp(dict(FILES))
    sync = SpeciesSync(store, http.get, base_url="https://pokeidle.io/assets")

    assert await sync.run_once() == "saved"
    assert all(inm is None for _, inm in http.calls)
    assert store.game_catalog["species"]["data"]["etags"]["creatures"] == 'W/"creatures-1"'
    assert set(store.game_species) == {10, 11, 12, 128, 129, 130, 13252}
    assert sync.catalog is not None and sync.catalog.species[10].stage == "first_of_three"

    http.calls.clear()
    assert await sync.run_once() == "unchanged"
    assert all(inm is not None for _, inm in http.calls)

    # o jogo atualizou um arquivo só
    http.files["creatures-formas"] = {"creatures": [creature(9999, "Forma")]}
    http.etags["creatures-formas"] = 'W/"creatures-formas-2"'
    assert await sync.run_once() == "saved"
    assert 9999 in store.game_species and 10 in store.game_species


async def test_species_sync_failure_keeps_previous():
    store = MemoryStore()
    http = FakeHttp(dict(FILES))
    sync = SpeciesSync(store, http.get, base_url="https://pokeidle.io/assets")
    await sync.run_once()
    before = sync.catalog

    http.fail = True
    assert await sync.run_once() == "failed"
    assert sync.catalog is before

    http.fail = False
    http.etags["creatures"] = 'W/"creatures-2"'
    http.files["creatures"] = "não é um objeto"
    assert await sync.run_once() == "failed"
    assert sync.catalog is before


async def test_species_sync_failure_on_start_loads_saved():
    store = MemoryStore()
    await SpeciesSync(store, FakeHttp(dict(FILES)).get, base_url="x").run_once()
    broken = FakeHttp(dict(FILES))
    broken.fail = True
    sync = SpeciesSync(store, broken.get, base_url="x")
    assert await sync.run_once() == "failed"
    assert sync.catalog is not None and sync.catalog.species[129].stage == "middle"


@pytest.mark.parametrize("version_in_store", [True])
async def test_species_sync_same_version_after_restart_does_not_rewrite(version_in_store):
    store = MemoryStore()
    await SpeciesSync(store, FakeHttp(dict(FILES)).get, base_url="x").run_once()
    writes = store.catalog_writes
    assert await SpeciesSync(store, FakeHttp(dict(FILES)).get, base_url="x").run_once() == (
        "unchanged"
    )
    assert store.catalog_writes == writes
