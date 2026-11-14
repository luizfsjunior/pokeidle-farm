import json
from uuid import uuid4

from pokeidle_farm.events import NOT_PERSISTED, Event, Translator
from pokeidle_farm.protocol import codec
from pokeidle_farm.protocol.messages import Battle, GameError, Hello, UnknownMessage, Welcome

from .conftest import battle, welcome


def test_hello_wire_format():
    wire = json.loads(codec.encode(Hello(nick="n", token="t", dispositivo="d")))
    assert wire == {"t": "hello", "nick": "n", "token": "t", "delta": 1, "dispositivo": "d"}


def test_decode_known_types():
    msg, _ = codec.decode(welcome())
    assert isinstance(msg, Welcome)
    assert msg.estado.hunt_slug == "rota-1"
    msg, _ = codec.decode(battle({"k": "morte"}))
    assert isinstance(msg, Battle)
    msg, _ = codec.decode('{"t":"erro","chave":"auth.contaBanida","motivoBan":"x"}')
    assert isinstance(msg, GameError)
    assert msg.motivo_ban == "x"


def test_decode_never_raises():
    for frame in ["não é json", "[1,2]", '{"t":"algo.novo","x":1}', '{"t":"welcome","estado":5}']:
        msg, raw = codec.decode(frame)
        assert isinstance(msg, UnknownMessage)
        assert raw


def test_translate_kill_and_capture():
    tr = Translator(uuid4(), uuid4())
    frame = battle(
        {
            "k": "morte",
            "nome": "Rattata",
            "xpTreinador": 30,
            "ouro": 7,
            "ouroVendaAuto": 3,
            "drops": [{"nome": "Pena"}],
            "extra": "guardado no raw",
        },
        {"k": "bola", "ballId": 1, "sucesso": True, "shiny": False, "chance": 0.4},
        {"k": "ataque", "slot": 0, "hpAlvo": 10},
        {"k": "coisaNova"},
    )
    msg, raw = codec.decode(frame)
    kill, cap, atk, new = tr.translate(msg, raw)
    assert kill.type == "kill"
    assert kill.data == {
        "wild_name": "Rattata",
        "xp": 30,
        "xp_pokemon": 0,
        "gold": 7,
        "gold_loot": 0,
        "loot_boost": False,
        "gold_autosell": 3,
        "drops": [{"name": "Pena"}],
        "hunt_slug": None,
    }
    assert kill.raw["extra"] == "guardado no raw"
    assert cap.type == "capture_attempt" and cap.data["success"] is True
    assert atk.type == "attack"
    assert new.type == "battle.coisaNova"


def test_kills_carry_current_hunt():
    tr = Translator(uuid4(), uuid4())
    tr.translate(*codec.decode(welcome()))  # huntSlug = rota-1
    (k1,) = tr.translate(*codec.decode(battle({"k": "morte"})))
    tr.translate(*codec.decode(battle({"k": "hunt", "slug": "caverna", "nome": "Caverna"})))
    k2, cap = tr.translate(*codec.decode(battle({"k": "morte"}, {"k": "bola", "sucesso": False})))
    assert k1.data["hunt_slug"] == "rota-1"
    assert k2.data["hunt_slug"] == "caverna"
    assert cap.data["hunt_slug"] == "caverna"


def test_welcome_sets_server_offset():
    tr = Translator(uuid4(), uuid4())
    msg, raw = codec.decode(welcome(servidorAgora=0))  # relógio do servidor em 1970
    (snap,) = tr.translate(msg, raw)
    assert snap.type == "state.snapshot"
    assert tr.server_offset is not None and tr.server_offset.total_seconds() < 0
    ev = tr.system("x")
    assert ev.server_ts is not None and ev.server_ts.year == 1970


def test_unknown_message_becomes_event():
    tr = Translator(uuid4(), uuid4())
    msg, raw = codec.decode('{"t":"mercado.novo","a":1}')
    (ev,) = tr.translate(msg, raw)
    assert ev.type == "unknown" and ev.raw == {"t": "mercado.novo", "a": 1}


# --- tradutor v2 (docs/design/tradutor-v2.md), frames no formato real -------


def _tr_in_hunt(slug: str = "magikarp") -> Translator:
    tr = Translator(uuid4(), uuid4())
    tr.translate(*codec.decode(welcome(huntSlug=slug)))
    return tr


def _one(tr: Translator, frame: dict) -> Event:
    (ev,) = tr.translate(*codec.decode(json.dumps(frame)))
    return ev


def _kill_hunt(tr: Translator) -> str | None:
    return _one(tr, {"t": "batalha", "ev": [{"k": "morte"}]}).data["hunt_slug"]


def test_v2_nested_state_patch():
    tr = Translator(uuid4(), uuid4())
    frame = {
        "t": "estado",
        "estado": {
            "xp": 165,
            "gold": 1115,
            "pkMud": [{"id": 7, "nome": "Bulbasaur"}],
            "pkFora": [3],
        },
    }
    ev = _one(tr, frame)
    assert ev.type == "state.patch"
    assert ev.data == {"xp": 165, "gold": 1115, "pokemon_changed": [7], "pokemon_removed": [3]}
    assert ev.raw == frame


def test_v2_flat_state_patch_still_works():
    tr = Translator(uuid4(), uuid4())
    ev = _one(tr, {"t": "estado", "pkMud": [{"id": 7}]})
    assert ev.data["pokemon_changed"] == [7]


def test_v2_patch_scalars_and_hunt():
    tr = _tr_in_hunt()
    ev = _one(
        tr,
        {
            "t": "estado",
            "estado": {
                "level": 3,
                "balls": {"1": 56},
                "centroLivreEm": 123,
                "huntSlug": "caverna",
                "dexMud": [1],
                "servidorAgora": 9,
            },
        },
    )
    assert ev.data == {
        "level": 3,
        "balls": {"1": 56},
        "centro_livre_em": 123,
        "hunt_slug": "caverna",
        "pokemon_changed": [],
        "pokemon_removed": [],
    }
    assert _kill_hunt(tr) == "caverna"


def test_v2_center_is_not_a_hunt():
    tr = _tr_in_hunt("magikarp")
    ev = _one(tr, {"t": "campo.init", "slug": "centro", "centro": True, "mapa": "cerulean"})
    assert ev.type == "field.init"
    assert ev.data == {"slug": "centro", "map": "cerulean", "is_center": True}
    assert _kill_hunt(tr) == "magikarp"
    # só o slug já basta para reconhecer o Centro
    _one(tr, {"t": "campo.init", "slug": "centro"})
    assert _kill_hunt(tr) == "magikarp"


def test_v2_field_init_of_hunt_changes_hunt():
    tr = _tr_in_hunt("magikarp")
    ev = _one(tr, {"t": "campo.init", "slug": "caverna", "mapa": "gerado_agua_21-f428e88d"})
    assert ev.data == {"slug": "caverna", "map": "gerado_agua_21-f428e88d", "is_center": False}
    assert _kill_hunt(tr) == "caverna"


def test_v2_real_kill():
    tr = _tr_in_hunt()
    raw = {
        "k": "morte", "quem": "selvagem", "slot": 12, "nome": "Magikarp",
        "xp": 8, "xpPokemon": 11, "xpTreinador": 11,
        "ouro": 41, "ouroLoot": 5, "lootBoost": True, "drops": [],
    }  # fmt: skip
    ev = _one(tr, {"t": "batalha", "ev": [raw]})
    assert ev.type == "kill"
    assert ev.data == {
        "wild_name": "Magikarp",
        "xp": 11,
        "xp_pokemon": 11,
        "gold": 41,
        "gold_loot": 5,
        "loot_boost": True,
        "gold_autosell": 0,
        "drops": [],
        "hunt_slug": "magikarp",
    }


def test_v2_noise_translated_but_not_persisted():
    tr = Translator(uuid4(), uuid4())
    expected = {
        "campo": "field.tick",
        "vivo": "keepalive",
        "chat": "chat",
        "chat.del": "chat",
        "chat.fixada": "chat",
    }
    for t, type_ in expected.items():
        assert _one(tr, {"t": t}).type == type_, t
    assert {"field.tick", "keepalive", "chat"} <= NOT_PERSISTED


def test_v2_friends_still_unknown_and_persisted():
    tr = Translator(uuid4(), uuid4())
    ev = _one(tr, {"t": "amigos", "max": 300, "lista": [], "pedidos": []})
    assert ev.type == "unknown"
    assert "unknown" not in NOT_PERSISTED


def test_v2_lean_welcome():
    tr = Translator(uuid4(), uuid4())
    automation = {"ballIds": [1], "autoBallSemParar": True}
    frame = json.dumps(
        {
            "t": "welcome",
            "estado": {"huntSlug": "magikarp", "balls": {"1": 100}, "automation": automation},
            "hunts": [{"slug": "caterpie"}],
            "mercado": {"x": 1},
        }
    )
    (snap,) = tr.translate(*codec.decode(frame))
    assert set(snap.raw) == {"t", "estado"}
    assert snap.data["balls"] == {"1": 100}
    assert snap.data["automation"] == automation


def test_v2_levelup():
    ev = _one(
        Translator(uuid4(), uuid4()),
        battle_frame({"k": "levelup", "quem": "treinador", "level": 3}),
    )
    assert ev.type == "level_up"
    assert ev.data == {"who": "treinador", "level": 3}


def test_v2_fled_has_shiny():
    ev = _one(
        Translator(uuid4(), uuid4()),
        battle_frame({"k": "fugiu", "nome": "Magikarp", "level": 1, "shiny": False}),
    )
    assert ev.type == "wild_fled"
    assert ev.data["shiny"] is False


def test_v2_spawn_not_persisted():
    raw = {
        "k": "spawn", "hp": 60, "nome": "Magikarp", "slot": 19, "level": 1,
        "maxHp": 60, "tipos": ["WATER"], "looktype": 60129, "speciesId": 129,
    }  # fmt: skip
    ev = _one(Translator(uuid4(), uuid4()), battle_frame(raw))
    assert ev.type == "wild.spawned"
    assert ev.data == {"name": "Magikarp", "level": 1, "max_hp": 60, "species_id": 129}
    assert "wild.spawned" in NOT_PERSISTED


def test_v2_global_shiny_is_not_our_capture():
    frame = {
        "t": "shiny.captura",
        "vs": [0, 114, 114, 0],
        "nick": "Elija",
        "pokemon": {
            "id": 128109384,
            "nome": "Larvitar",
            "level": 20,
            "looktype": 70246,
            "speciesId": 246,
        },
        "looktype": 159,
    }
    evs = Translator(uuid4(), uuid4()).translate(*codec.decode(json.dumps(frame)))
    assert [e.type for e in evs] == ["global.shiny_captured"]
    assert evs[0].data == {"nick": "Elija", "species": "Larvitar", "level": 20, "species_id": 246}
    assert "global.shiny_captured" not in NOT_PERSISTED


def battle_frame(*evs: dict) -> dict:
    return {"t": "batalha", "ev": list(evs)}


CAPTURED = {
    "k": "capturado",
    "pokemon": {
        "id": 128261620,
        "ivs": {"hp": 19, "atk": 6, "def": 17, "spAtk": 27, "spDef": 28, "speed": 8},
        "nome": "Magikarp",
        "level": 1,
        "shiny": False,
        "quality": 0.983,
        "potencia": 1,
        "lookShiny": None,
        "speciesId": 129,
    },
    "paraDepot": False,
}


def test_v2_real_capture():
    ev = _one(_tr_in_hunt("magikarp"), battle_frame(CAPTURED))
    assert ev.type == "pokemon.captured"
    assert ev.data == {
        "species": "Magikarp",
        "species_id": 129,
        "level": 1,
        "shiny": False,
        "potency": 1,
        "quality": 0.983,
        "ivs": {"hp": 19, "atk": 6, "def": 17, "spAtk": 27, "spDef": 28, "speed": 8},
        "iv_sum": 105,
        "pokemon_id": 128261620,
        "to_depot": False,
        "hunt_slug": "magikarp",
    }
    assert "pokemon.captured" not in NOT_PERSISTED


def test_v2_successful_ball_alone_is_not_a_capture():
    tr = _tr_in_hunt()
    evs = tr.translate(
        *codec.decode(json.dumps(battle_frame({"k": "bola", "ballId": 4, "sucesso": True})))
    )
    assert [e.type for e in evs] == ["capture_attempt"]


def test_v2_capture_without_ivs():
    frame = {**CAPTURED, "pokemon": {k: v for k, v in CAPTURED["pokemon"].items() if k != "ivs"}}
    ev = _one(_tr_in_hunt(), battle_frame(frame))
    assert ev.data["ivs"] == {} and ev.data["iv_sum"] == 0


# --- fase 3a: preço das bolas e consumo de itens ------------------------------


def test_capture_attempt_carries_ball_price():
    tr = _tr_in_hunt()
    ev = _one(tr, battle_frame({"k": "bola", "ballId": 4, "sucesso": False, "chance": 0.012}))
    assert ev.data["ball_price"] == 130
    ev = _one(tr, battle_frame({"k": "bola", "ballId": 99, "sucesso": False}))
    assert ev.data["ball_price"] is None


def test_snapshot_and_patch_carry_items_gold_automation():
    tr = Translator(uuid4(), uuid4())
    (snap,) = tr.translate(
        *codec.decode(welcome(gold=1000, items={"200": 100}, automation={"ballIds": [1]}))
    )
    assert snap.data["gold"] == 1000
    ev = _one(tr, {"t": "estado", "estado": {"automation": {"ballIds": [2]}}})
    assert ev.data["automation"] == {"ballIds": [2]}


def test_item_consumed_when_stock_drops():
    tr = Translator(uuid4(), uuid4())
    tr.translate(*codec.decode(welcome(huntSlug="caverna", items={"200": 100, "205": 20, "2": 8})))
    evs = tr.translate(
        *codec.decode(json.dumps({"t": "estado", "estado": {"items": {"200": 97, "205": 20}}}))
    )
    assert [e.type for e in evs] == ["state.patch", "item.consumed"]
    assert evs[1].data == {"item_id": 200, "qty": 3, "unit_price": 50, "hunt_slug": "caverna"}
    # compra (estoque subindo) não é consumo; item fora da loja (id 2) também não
    evs = tr.translate(
        *codec.decode(json.dumps({"t": "estado", "estado": {"items": {"200": 150, "2": 1}}}))
    )
    assert [e.type for e in evs] == ["state.patch"]
    # a próxima queda conta a partir do estoque novo
    evs = tr.translate(
        *codec.decode(json.dumps({"t": "estado", "estado": {"items": {"200": 149}}}))
    )
    assert evs[1].data["qty"] == 1


# --- tradutor da 3b (docs/design/tradutor-3b.md), frames reais de 14/11 ----

TOP_CATCH_NOVA = {
    "k": "topCatchNova",
    "s": "2026-11-08",
    "chave": "10",
    "sp": 10,
    "m": 9502,
    "n": 12,
    "pontua": True,
}


def _evs(tr: Translator, frame: dict) -> list[Event]:
    return tr.translate(*codec.decode(json.dumps(frame)))


def _auto_patch(on: bool) -> dict:
    return {"t": "estado", "estado": {"automation": {"ballIds": [4], "autoBallAteCapturar": on}}}


def _tr_with_auto(on: bool, slug: str = "caterpie") -> Translator:
    tr = Translator(uuid4(), uuid4())
    tr.translate(
        *codec.decode(
            welcome(huntSlug=slug, automation={"ballIds": [4], "autoBallAteCapturar": on})
        )
    )
    return tr


def test_3b_top_catch_nova():
    ev = _one(_tr_in_hunt("caterpie"), battle_frame(TOP_CATCH_NOVA))
    assert ev.type == "rank.catch"
    assert ev.data == {
        "species_id": 10,
        "week_start": "2026-11-08",
        "week_species": 12,
        "week_minute": 9502,
        "scores": True,
        "hunt_slug": "caterpie",
    }
    assert "rank.catch" not in NOT_PERSISTED


def test_3b_top_catch_nova_not_scoring():
    ev = _one(_tr_in_hunt(), battle_frame({**TOP_CATCH_NOVA, "pontua": False}))
    assert ev.data["scores"] is False


def test_3b_top_catch_nova_empty():
    ev = _one(_tr_in_hunt("caterpie"), battle_frame({"k": "topCatchNova"}))
    assert ev.type == "rank.catch"
    assert ev.data == {
        "species_id": None,
        "week_start": None,
        "week_species": None,
        "week_minute": None,
        "scores": None,
        "hunt_slug": "caterpie",
    }


def test_3b_capture_frame_order():
    frame = battle_frame(
        {"k": "bola", "ballId": 4, "slot": 3, "sucesso": True, "chance": 0.015, "shiny": False},
        TOP_CATCH_NOVA,
    )
    assert [e.type for e in _evs(_tr_in_hunt(), frame)] == ["capture_attempt", "rank.catch"]


def test_3b_hunt_changed_switch_free_at():
    tr = _tr_in_hunt()
    ev = _one(
        tr,
        battle_frame(
            {"k": "hunt", "slug": "meowth", "nome": "Meowth", "trocaLivreEm": 1794676585909}
        ),
    )
    assert ev.type == "hunt.changed"
    assert ev.data == {
        "slug": "meowth",
        "name": "Meowth",
        "switch_free_at": "2026-11-14T17:16:25.909000Z",
    }
    assert _kill_hunt(tr) == "meowth"


def test_3b_hunt_changed_without_switch_free_at():
    ev = _one(_tr_in_hunt(), battle_frame({"k": "hunt", "slug": "meowth", "nome": "Meowth"}))
    assert ev.data["switch_free_at"] is None


def test_3b_catch_until_capture_turned_off_by_server():
    evs = _evs(_tr_with_auto(True), _auto_patch(False))
    assert [e.type for e in evs] == ["state.patch", "auto.catch_until_capture_off"]
    assert evs[1].data == {"hunt_slug": "caterpie"}
    assert "auto.catch_until_capture_off" not in NOT_PERSISTED


def test_3b_no_transition_no_event():
    tr = _tr_with_auto(False)
    assert [e.type for e in _evs(tr, _auto_patch(False))] == ["state.patch"]
    assert [e.type for e in _evs(tr, _auto_patch(True))] == ["state.patch"]
    assert [e.type for e in _evs(tr, {"t": "estado", "estado": {"xp": 1}})] == ["state.patch"]


def test_3b_known_automation_follows_patches():
    tr = _tr_with_auto(False)
    assert [e.type for e in _evs(tr, _auto_patch(True))] == ["state.patch"]
    assert [e.type for e in _evs(tr, _auto_patch(False))] == [
        "state.patch",
        "auto.catch_until_capture_off",
    ]


def test_3b_no_welcome_no_event():
    tr = Translator(uuid4(), uuid4())
    assert [e.type for e in _evs(tr, _auto_patch(False))] == ["state.patch"]


def test_3b_top_catch_in_patch():
    tc = {"s": "2026-11-08", "n": 12, "m": 12, "ini": False}
    ev = _one(Translator(uuid4(), uuid4()), {"t": "estado", "estado": {"topCatch": tc}})
    assert ev.data["top_catch"] == tc


def test_3b_top_catch_in_welcome():
    tc = {"s": "2026-11-08", "n": 12, "m": 12, "ini": False}
    (snap,) = Translator(uuid4(), uuid4()).translate(*codec.decode(welcome(topCatch=tc)))
    assert snap.data["top_catch"] == tc
    (snap,) = Translator(uuid4(), uuid4()).translate(*codec.decode(welcome()))
    assert snap.data["top_catch"] is None
