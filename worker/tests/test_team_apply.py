"""team.apply: equipe montada no painel aplicada numa ida ao centro (conta-v2.md, seção 3)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pokeidle_farm.team_apply import Step, plan_moves

from .test_commands import farm, rig  # noqa: F401


def simulate(
    team: dict[int, int], active: int | None, steps: list[Step]
) -> tuple[dict[int, int], int | None]:
    where = {p: s for s, p in team.items()}
    for st in steps:
        if st.kind == "active":
            assert st.pokemon_id in where, "o ativo tem que estar na equipe"
            active = st.pokemon_id
            continue
        if st.slot is None:
            assert st.pokemon_id != active, "não tira o ativo"
            where.pop(st.pokemon_id)
        else:
            assert st.slot not in where.values(), "vaga ocupada"
            where[st.pokemon_id] = st.slot
    return {s: p for p, s in where.items()}, active


def test_plan_swaps_slots_and_keeps_an_active_in_the_team():
    team = {0: 1, 1: 2, 2: 3}
    steps = plan_moves(team, 1, [2, 1, 9, None, 8], 9)
    final, active = simulate(team, 1, steps)
    assert final == {0: 2, 1: 1, 2: 9, 4: 8} and active == 9


def test_plan_drops_the_old_active_last():
    team = {0: 1, 1: 2}
    steps = plan_moves(team, 1, [5, 6], 5)
    final, active = simulate(team, 1, steps)
    assert final == {0: 5, 1: 6} and active == 5
    assert steps.index(Step("active", 5)) < steps.index(Step("move", 1, None))


def test_plan_handles_a_full_team():
    team = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}
    steps = plan_moves(team, 1, [9, 2, 3, 4, 5], 9)
    final, active = simulate(team, 1, steps)
    assert final == {0: 9, 1: 2, 2: 3, 3: 4, 4: 5} and active == 9
    steps = plan_moves(team, 1, [5, 4, 3, 2, 1], 3)
    final, active = simulate(team, 1, steps)
    assert final == {0: 5, 1: 4, 2: 3, 3: 2, 4: 1} and active == 3


def test_plan_is_empty_when_nothing_changes():
    assert plan_moves({0: 1, 1: 2}, 1, [1, 2], 1) == []


class Game:
    """Gateway e estado de mentira: aplica as ações como o jogo faria."""

    def __init__(self, team: list[dict[str, Any]], active: int, hunt: str) -> None:
        from datetime import UTC, datetime

        self.view = SimpleNamespace(
            team=team,
            active_pokemon={"id": active},
            hunt_slug=hunt,
            in_center=False,
            combat_free_at=None,
            server_now=lambda: datetime.now(UTC),
        )
        self.sent: list[dict[str, Any]] = []
        self.holds: dict[str, Any] = {}

    def hold(self, action, until, owner, label=None):  # type: ignore[no-untyped-def]
        self.holds[action] = (until, owner, label)

    def release(self, owner, action=None):  # type: ignore[no-untyped-def]
        for a in [a for a, h in self.holds.items() if h[1] == owner]:
            del self.holds[a]

    async def note(self, type_, data):  # type: ignore[no-untyped-def]
        pass

    async def submit(self, action, *, source):  # type: ignore[no-untyped-def]
        w = action.to_wire()
        self.sent.append(w)
        v = self.view
        if w["t"] == "centro.ir":
            from datetime import UTC, datetime

            # em combate o jogo recusa ("espere Xs sem tomar nem dar dano")
            if v.combat_free_at is None or v.combat_free_at <= datetime.now(UTC):
                v.in_center = True
        elif w["t"] == "hunt.select":
            v.in_center, v.hunt_slug = False, w["slug"]
        elif w["t"] == "team.active":
            v.active_pokemon = {"id": w["pokemonId"]}
        elif w["t"] == "team.move" and v.in_center:
            v.team = [m for m in v.team if m["id"] != w["pokemonId"]]
            if w["slot"] is not None:
                v.team.append({"id": w["pokemonId"], "slot": w["slot"]})


async def _wire(rig, game: Game):  # type: ignore[no-untyped-def]  # noqa: F811
    s = rig.sessions[0]
    s.state_view, s.gateway = game.view, game

    async def confirm(check, since, within):  # type: ignore[no-untyped-def]
        return None if check() else "sem confirmação do jogo"

    s.confirm = confirm


async def test_apply_goes_to_center_swaps_and_returns(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}, {"id": 2, "slot": 1}], active=1, hunt="brave_steelix")
    game.holds["hunt.select"] = ("x", "hunt_hold", "brave_steelix")
    await _wire(rig, game)
    c = await rig.cmd(acc, "team.apply", team=[2, 7], active=7)
    assert c["status"] == "done", c
    assert game.sent[0] == {"t": "centro.ir"} and game.sent[-1] == {
        "t": "hunt.select",
        "slug": "brave_steelix",
    }
    assert sorted((m["slot"], m["id"]) for m in game.view.team) == [(0, 2), (1, 7)]
    assert game.view.active_pokemon == {"id": 7} and game.view.in_center is False
    assert game.holds == {
        "hunt.select": ("x", "hunt_hold", "brave_steelix")
    }  # trava da hunt de volta


async def test_apply_rejects_an_active_outside_the_team(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    await rig.boot()
    await _wire(rig, Game([{"id": 1, "slot": 0}], active=1, hunt="x"))
    c = await rig.cmd(acc, "team.apply", team=[1], active=5)
    assert c["status"] == "failed" and "ativo" in c["error"]


async def test_apply_waits_for_a_break_in_combat_before_going_to_the_center(rig):  # noqa: F811
    from datetime import UTC, datetime, timedelta

    acc = farm(rig.store, "farm1")
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}], active=1, hunt="brave_steelix")
    game.view.combat_free_at = datetime.now(UTC) + timedelta(seconds=0.4)
    await _wire(rig, game)
    c = await rig.cmd(acc, "team.apply", team=[1, 2], active=1)
    assert c["status"] == "done", c
    assert [w["t"] for w in game.sent].count("centro.ir") == 1  # esperou a folga e mandou uma vez


class _Prof:
    def __init__(self, mons: dict[int, dict[str, Any]]) -> None:
        self.profile = SimpleNamespace(pokemons=mons, ready=True)


def _with_mons(rig, game: Game, mons: dict[int, dict[str, Any]]) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    s = rig.sessions[0]
    s.plugins.running["profile"] = _Prof(mons)
    orig = game.submit

    async def submit(action, *, source):  # type: ignore[no-untyped-def]
        await orig(action, source=source)
        w = action.to_wire()
        if w["t"] == "colecao.mover":
            mons[w["pokemonId"]]["colecao"] = w["para"] == "colecao"
        elif w["t"] == "shop.sellAllPokemons":
            for pid in [
                p for p, m in mons.items() if m.get("slot") is None and not m.get("colecao")
            ]:
                del mons[pid]

    game.submit = submit  # type: ignore[method-assign]


async def test_who_leaves_the_team_goes_where_the_panel_said(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}, {"id": 2, "slot": 1}], active=1, hunt="h")
    game.view.team.append({"id": 3, "slot": 2})
    mons = {
        1: {"id": 1, "slot": 0},
        2: {"id": 2, "slot": 1},
        3: {"id": 3, "slot": 2, "colecao": True},
        7: {"id": 7, "slot": None},
    }
    await _wire(rig, game)
    _with_mons(rig, game, mons)
    c = await rig.cmd(
        acc, "team.apply", team=[1, 7], active=1, left_to={"2": "colecao", "3": "depot"}
    )
    assert c["status"] == "done", c
    assert mons[2]["colecao"] is True and mons[3]["colecao"] is False and not mons[7].get("colecao")


async def test_depot_sell_guards(rig):  # noqa: F811
    acc = farm(rig.store, "farm1")
    await rig.boot()
    game = Game([{"id": 1, "slot": 0}], active=1, hunt="h")
    mons = {
        1: {"id": 1, "slot": 0},
        2: {"id": 2, "slot": None, "colecao": True},
        3: {"id": 3, "slot": None},
        4: {"id": 4, "slot": None, "shiny": True},
    }
    await _wire(rig, game)
    _with_mons(rig, game, mons)
    c = await rig.cmd(acc, "depot.sell", expected=1)
    assert c["status"] == "failed" and "tem 2" in c["error"]
    c = await rig.cmd(acc, "depot.sell", expected=2)
    assert c["status"] == "failed" and "shiny" in c["error"]
    c = await rig.cmd(acc, "collection.move", pokemon_id=4, to="colecao")
    assert c["status"] == "done", c
    c = await rig.cmd(acc, "depot.sell", expected=1)
    assert c["status"] == "done" and c["result"]["sold"] == 1
    assert set(mons) == {1, 2, 4}
