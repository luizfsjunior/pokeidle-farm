"""Pokémon protegidos (épico C1): a regra, o espelho na Coleção e as travas nos comandos."""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from pokeidle_farm.actions import ActionGateway, ActionMode, RateLimiter
from pokeidle_farm.bus import EventBus
from pokeidle_farm.events import Event
from pokeidle_farm.plugins.base import AccountStateView, PluginContext
from pokeidle_farm.plugins.protect import ProtectConfig, ProtectPlugin
from pokeidle_farm.protection import is_protected, keeps_out_of_depot, needs_mirror, reasons
from pokeidle_farm.store.memory import MemoryStore

from .test_commands import farm, rig  # noqa: F401  (fixture)
from .test_team_apply import Game, _wire, _with_mons

# --- regra -------------------------------------------------------------------


def test_reasons_cover_manual_shiny_team_and_collection():
    assert reasons({"slot": None}, 1) == []
    assert reasons({"slot": 0, "shiny": True}, 1, manual={1}, collection={1}) == [
        "manual",
        "shiny",
        "equipe",
        "colecao",
    ]
    assert reasons(None, 9, manual=[9]) == ["manual"]  # marcado mas fora do perfil ainda


def test_is_protected_firm_only_ignores_the_collection():
    mon = {"slot": None}
    assert is_protected(mon, 3, collection={3})
    assert not is_protected(mon, 3, collection={3}, firm_only=True)
    assert is_protected({"shiny": True}, 3, firm_only=True)


def test_keeps_out_of_depot_is_manual_or_shiny_only():
    assert keeps_out_of_depot({"shiny": True}, 1, set())
    assert keeps_out_of_depot({}, 1, {1})
    assert not keeps_out_of_depot({"slot": 2}, 1, set())  # saindo da equipe pode ir ao Depot


def test_needs_mirror_lists_firm_protected_outside_team_and_collection():
    mons = {
        1: {"slot": 0, "shiny": True},  # equipe: não é vendido
        2: {"slot": None, "shiny": True},
        3: {"slot": None},
        4: {"slot": None},  # manual, já na Coleção
        5: {"slot": None},  # manual
        "6": {"slot": None, "shiny": True},  # id como texto
    }
    assert needs_mirror(mons, manual={4, 5}, collection={4}) == [2, 6, 5]


# --- plugin protect ----------------------------------------------------------


class Rig:
    def __init__(self, manual: set[int], **cfg: Any) -> None:
        self.t = 1000.0
        self.sent: list[dict[str, Any]] = []
        self.notes: list[tuple[str, dict[str, Any]]] = []

        async def send(p: dict[str, Any]) -> None:
            self.sent.append(p)

        async def record(t: str, d: dict[str, Any]) -> None:
            self.notes.append((t, d))

        store = MemoryStore()
        self.account = uuid4()
        store.protected[self.account] = manual
        self.store = store
        self.state = AccountStateView(automation={"pokemonTravado": [4]})
        self.plugin = ProtectPlugin()
        self.plugin.clock = lambda: self.t
        self.ctx = PluginContext(
            account_id=self.account,
            nick="farm1",
            config=ProtectConfig.model_validate(cfg),
            bus=EventBus(),
            actions=ActionGateway(
                "acc",
                ActionMode.ENABLED,
                send=send,
                record=record,
                limiter=RateLimiter(clock=lambda: self.t),
            ),
            state=self.state,
            store=store,
            settings=None,
            log=logging.getLogger("t"),
        )

    async def start(self) -> Rig:
        await self.plugin.start(self.ctx)
        if self.plugin._timer is not None:
            self.plugin._timer.cancel()
        return self

    async def snapshot(self, pokemons: list[dict[str, Any]]) -> None:
        estado = {"pokemons": pokemons, "automation": {"pokemonTravado": [4]}}
        await self.plugin.on_event(
            Event(
                account_id=self.account,
                session_id=uuid4(),
                type="state.snapshot",
                data={},
                raw={"t": "welcome", "estado": estado},
            )
        )

    async def patch(self) -> None:
        await self.plugin.on_event(
            Event(
                account_id=self.account,
                session_id=uuid4(),
                type="state.patch",
                data={},
                raw={"t": "estado", "estado": {"gold": 1}},
            )
        )

    def moved(self) -> list[int]:
        return [p["pokemonId"] for p in self.sent if p["t"] == "colecao.mover"]


MONS = [
    {"id": 1, "slot": 0, "shiny": True},
    {"id": 2, "slot": None, "shiny": True, "nome": "Pichu"},
    {"id": 3, "slot": None},
    {"id": 4, "slot": None},
    {"id": 5, "slot": None},
]


async def test_protect_mirrors_one_at_a_time_and_marks_the_view():
    r = await Rig(manual={4, 5}).start()
    await r.snapshot(MONS)
    assert r.moved() == [2]
    assert r.sent[0] == {"t": "colecao.mover", "pokemonId": 2, "para": "colecao"}
    assert 2 in r.state.automation["pokemonTravado"]  # o auto.set não apaga a marca
    assert r.notes[-1] == (
        "protect.mirrored",
        {"pokemon_id": 2, "species_id": None, "name": "Pichu", "reason": "shiny"},
    )
    await r.patch()
    assert r.moved() == [2]  # espera o intervalo
    r.t += 21
    await r.patch()
    assert r.moved() == [2, 5]  # o 4 já estava na Coleção
    r.t += 21
    await r.patch()
    assert r.moved() == [2, 5]  # nada mais a fazer


async def test_protect_retries_when_the_game_did_not_confirm():
    r = await Rig(manual=set(), retry_min=1).start()
    await r.snapshot(MONS)
    assert r.moved() == [2]
    await r.snapshot(MONS)  # welcome de novo: o 2 ainda fora da Coleção
    r.t += 21
    await r.patch()
    assert r.moved() == [2]  # pedido há pouco: espera retry_min
    r.t += 60
    await r.patch()
    assert r.moved() == [2, 2]


async def test_protect_waits_for_the_list_and_can_be_turned_off():
    r = Rig(manual={5})

    async def broken(_aid):  # type: ignore[no-untyped-def]
        raise RuntimeError("fora do ar")

    r.store.protected_pokemon = broken  # type: ignore[method-assign]
    await r.start()
    await r.snapshot([{"id": 5, "slot": None}])
    assert r.moved() == []  # sem a lista não espelha no escuro
    off = await Rig(manual={5}, mirror=False).start()
    await off.snapshot(MONS)
    assert off.moved() == []


# --- comandos ----------------------------------------------------------------


def _mons() -> dict[int, dict[str, Any]]:
    return {
        1: {"id": 1, "slot": 0},
        2: {"id": 2, "slot": None, "colecao": True},
        3: {"id": 3, "slot": None},
        4: {"id": 4, "slot": None, "shiny": True},
        5: {"id": 5, "slot": None},
    }


async def test_depot_sell_moves_protected_to_the_collection_first(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    rig.store.protected[acc.id] = {5}
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}], active=1, hunt="h")
    mons = _mons()
    await _wire(rig, game)
    _with_mons(rig, game, mons)
    # o painel mostrou 3 no Depot (3, 4, 5): os protegidos não contam
    c = await rig.cmd(acc, "depot.sell", expected=1)
    assert c["status"] == "done", c
    assert c["result"]["sold"] == 1
    assert set(mons) == {1, 2, 4, 5}
    assert mons[4]["colecao"] and mons[5]["colecao"]


async def test_depot_sell_with_only_protected_sells_nothing(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}], active=1, hunt="h")
    mons = {1: {"id": 1, "slot": 0}, 4: {"id": 4, "slot": None, "shiny": True}}
    await _wire(rig, game)
    _with_mons(rig, game, mons)
    c = await rig.cmd(acc, "depot.sell", expected=0)
    assert c["status"] == "done", c
    assert c["result"]["sold"] == 0 and c["result"]["protected"] == [4]
    assert not any(w["t"] == "shop.sellAllPokemons" for w in game.sent)


async def test_depot_sell_fails_closed_without_the_list(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}], active=1, hunt="h")
    mons = _mons()
    await _wire(rig, game)
    _with_mons(rig, game, mons)

    async def broken(_aid):  # type: ignore[no-untyped-def]
        raise RuntimeError("fora do ar")

    rig.store.protected_pokemon = broken  # type: ignore[method-assign]
    c = await rig.cmd(acc, "depot.sell", expected=3)
    assert c["status"] == "failed" and "protegidos" in c["error"]
    assert set(mons) == {1, 2, 3, 4, 5}


async def test_collection_move_never_sends_protected_to_the_depot(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    rig.store.protected[acc.id] = {2}
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}], active=1, hunt="h")
    mons = _mons()
    await _wire(rig, game)
    _with_mons(rig, game, mons)
    c = await rig.cmd(acc, "collection.move", pokemon_id=2, to="depot")
    assert c["status"] == "failed" and "protegido" in c["error"]
    c = await rig.cmd(acc, "collection.move", pokemon_ids=[2, 3, 4], to="depot")
    assert c["status"] == "done", c
    assert c["result"] == {"moved": 0, "to": "depot", "protected": [2, 4]}  # o 3 já estava
    assert mons[2]["colecao"] is True
    # para a Coleção, protegido ou não, vai
    c = await rig.cmd(acc, "collection.move", pokemon_ids=[3, 4], to="colecao")
    assert c["result"] == {"moved": 2, "to": "colecao"}


async def test_protected_leaving_the_team_stays_in_the_collection(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    rig.store.protected[acc.id] = {2}
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}, {"id": 2, "slot": 1}], active=1, hunt="h")
    mons = {1: {"id": 1, "slot": 0}, 2: {"id": 2, "slot": 1}, 7: {"id": 7, "slot": None}}
    await _wire(rig, game)
    _with_mons(rig, game, mons)
    c = await rig.cmd(acc, "team.apply", team=[1, 7], active=1, left_to={"2": "depot"})
    assert c["status"] == "done", c
    assert mons[2]["colecao"] is True
    assert "2 na Coleção" in c["result"]["steps"]
