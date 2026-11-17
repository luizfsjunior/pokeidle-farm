"""Perfil da conta (docs/design/painel-perfil.md): merge do estado e o plugin profile."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.profile import ProfileConfig, ProfilePlugin
from pokeidle_farm.profile import ProfileState
from pokeidle_farm.store.memory import MemoryStore

ESTADO = {
    "nick": "farm1",
    "level": 38,
    "xp": 123456,
    "xpNivel": 1000,
    "xpProximo": 5000,
    "gold": 41000,
    "orbs": 12,
    "diamonds": 3,
    "huntSlug": "kabuto",
    "activeId": 7,
    "loja": {"vipAte": 1_800_000_000_000},
    "items": {"200": 5, "201": 0},
    "balls": {"1": 56, "2": 0},
    "pokedex": {"129": {"c": 1, "k": 502}, "10": {"c": 0, "k": 3}},
    "pokemons": [
        {
            "id": 7,
            "speciesId": 140,
            "nome": "Kabuto",
            "level": 38,
            "slot": 0,
            "poder": 900,
            "looktype": 140,
            "ivs": {"hp": 10, "atk": 20},
            "xp": 4000,
            "apelido": "Kabu",
            "shiny": False,
            "segredo": "x",
        },
        {
            "id": 8,
            "speciesId": 129,
            "nome": "Magikarp",
            "level": 5,
            "slot": None,
            "poder": 10,
            "shiny": True,
        },
        {"id": 9, "speciesId": 10, "nome": "Caterpie", "level": 3, "slot": 1, "poder": 30},
    ],
}


def test_snapshot_summary():
    p = ProfileState()
    p.apply_snapshot(ESTADO)
    s = p.summary(datetime(2026, 11, 16, tzinfo=UTC))
    assert (s["level"], s["gold"], s["gems"], s["diamonds"]) == (38, 41000, 12, 3)
    assert s["xp_level"] == 1000 and s["xp_next"] == 5000
    assert s["vip_until"].startswith("2027-01-15")
    assert [t["name"] for t in s["team"]] == ["Kabuto", "Caterpie"]
    assert s["team"][0]["iv_sum"] == 30 and "segredo" not in s["team"][0]
    assert s["team"][0]["ivs"] == {"hp": 10, "atk": 20}
    assert s["team"][0]["xp"] == 4000 and s["team"][0]["nickname"] == "Kabu"
    assert "segredo" in s["extra"]["pokemon_keys"]
    assert s["pokemon_count"] == 3 and s["shiny_count"] == 1
    assert s["dex_seen"] == 2 and s["dex_caught"] == 1
    assert s["items"] == {"200": 5} and s["balls"] == {"1": 56}
    assert s["top_pokemon"][0]["name"] == "Kabuto"
    assert "pokemons" not in s["estado_keys"] and "gold" in s["estado_keys"]


def test_patch_merges_pokemon_dex_and_maps():
    p = ProfileState()
    p.apply_snapshot(ESTADO)
    p.apply_patch(
        {
            "gold": 42000,
            "balls": {"1": 55},
            "pkMud": [
                {"id": 7, "level": 39},
                {"id": 10, "nome": "Pidgey", "slot": 2, "speciesId": 16},
            ],
            "pkFora": [8],
            "dexMud": {"10": {"c": 1}, "16": {"c": 1, "k": 0}},
        }
    )
    s = p.summary()
    assert s["gold"] == 42000 and s["balls"] == {"1": 55}
    assert [(t["name"], t.get("level")) for t in s["team"]] == [
        ("Kabuto", 39),
        ("Caterpie", 3),
        ("Pidgey", None),
    ]
    assert s["pokemon_count"] == 3 and s["shiny_count"] == 0
    assert s["dex_seen"] == 3 and s["dex_caught"] == 3
    assert p.pokedex["10"] == {"c": 1, "k": 3}


def _plugin() -> tuple[ProfilePlugin, MemoryStore, PluginContext]:
    store = MemoryStore()
    ctx = PluginContext(
        account_id=uuid4(),
        nick="farm1",
        config=ProfileConfig(),
        bus=EventBus(),
        actions=ActionGateway("acc", ActionMode.OBSERVE_ONLY),
        state=AccountStateView(),
        store=store,
        settings=None,
        log=logging.getLogger("test"),
    )
    return ProfilePlugin(), store, ctx


def _ev(ctx: PluginContext, type_: str, estado: dict) -> Event:
    return Event(
        account_id=ctx.account_id,
        session_id=uuid4(),
        type=type_,
        raw={"t": "estado", "estado": estado},
    )


async def test_plugin_writes_first_snapshot_then_on_interval():
    plugin, store, ctx = _plugin()
    ticks: list[float] = []

    async def never(s: float) -> None:
        ticks.append(s)
        await __import__("asyncio").Event().wait()

    plugin.sleep = never
    await plugin.start(ctx)
    await plugin.on_event(_ev(ctx, "state.patch", {"gold": 1}))  # antes do welcome: ignorado
    assert not getattr(store, "profiles", {})
    await plugin.on_event(_ev(ctx, "state.snapshot", ESTADO))
    row = store.profiles[str(ctx.account_id)]
    assert row["gold"] == 41000
    await plugin.on_event(_ev(ctx, "state.patch", {"gold": 50000}))
    assert store.profiles[str(ctx.account_id)]["gold"] == 41000  # espera o intervalo
    await plugin.stop()  # grava o que faltou ao parar
    assert store.profiles[str(ctx.account_id)]["gold"] == 50000


async def test_plugin_retries_after_store_failure():
    plugin, store, ctx = _plugin()
    calls = 0

    async def boom(row: dict) -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("fora do ar")

    store.upsert_account_profile = boom  # type: ignore[method-assign]
    plugin.ctx = ctx
    plugin.cfg = ProfileConfig()
    await plugin.on_event(_ev(ctx, "state.snapshot", ESTADO))
    assert calls == 1 and plugin.dirty


def test_extra_keeps_known_fields_and_skips_huge_ones():
    p = ProfileState()
    p.apply_snapshot(
        {
            **ESTADO,
            "passe": {"degrau": 2, "total": 2, "ciclos": 0, "ultimo": 20773},
            "guild": {"nome": "Equipe"},
            "campConquistas": {"x": "y" * 30_000},  # grande demais
            "token": "nunca",  # não está na lista
        }
    )
    s = p.summary()
    assert s["extra"]["passe"]["degrau"] == 2 and s["extra"]["guild"] == {"nome": "Equipe"}
    assert "campConquistas" not in s["extra"] and "token" not in s["extra"]
    assert s["extra"]["loja"] == {"vipAte": 1_800_000_000_000}
    assert s["pokedex"]["129"] == {"c": 1, "k": 502}
