import json
from uuid import uuid4

from pokeidle_farm.events import Translator
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
        "gold": 7,
        "gold_autosell": 3,
        "drops": [{"name": "Pena"}],
    }
    assert kill.raw["extra"] == "guardado no raw"
    assert cap.type == "capture_attempt" and cap.data["success"] is True
    assert atk.type == "attack"
    assert new.type == "battle.coisaNova"


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
