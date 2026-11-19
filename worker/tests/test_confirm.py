import asyncio
import time

from pokeidle_farm.session import AccountSession


def _session() -> AccountSession:
    s = AccountSession.__new__(AccountSession)
    from collections import deque

    s.replies = deque(maxlen=20)
    return s


async def test_confirm_returns_none_when_the_effect_shows_up():
    s = _session()
    state = {"ok": False}

    async def later():
        await asyncio.sleep(0.15)
        state["ok"] = True

    asyncio.get_running_loop().create_task(later())
    assert await s.confirm(lambda: state["ok"], time.monotonic(), within=2) is None


async def test_confirm_reports_the_game_reply():
    s = _session()
    since = time.monotonic()
    s.replies.append((since + 0.01, "acesse o Depot no Centro Pokemon de Cerulean"))
    assert (
        await s.confirm(lambda: False, since, within=2)
        == "acesse o Depot no Centro Pokemon de Cerulean"
    )


async def test_confirm_ignores_old_replies_and_times_out():
    s = _session()
    s.replies.append((time.monotonic() - 10, "velho"))
    assert await s.confirm(lambda: False, time.monotonic(), within=0.3) == "sem confirmação do jogo"
