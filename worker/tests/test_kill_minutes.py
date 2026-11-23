"""Abates somados por minuto (kill_minutes.py e a telemetria; docs/design/retencao-eventos.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pokeidle_farm.events import NOT_PERSISTED, Event
from pokeidle_farm.kill_minutes import AGGREGATED, KillMinutes
from pokeidle_farm.plugins.telemetry import TelemetryPlugin
from pokeidle_farm.store.memory import MemoryStore

ACC, SES = uuid4(), uuid4()
T0 = datetime(2026, 11, 23, 10, 1, 5, tzinfo=UTC)


def kill(at: datetime, **data) -> Event:
    base = {"hunt_slug": "rochaz", "xp": 100, "gold": 40, "gold_autosell": 0, "drops": []}
    base["active_species_id"] = 7
    return Event(account_id=ACC, session_id=SES, type="kill", received_at=at, data={**base, **data})


def consumed(at: datetime, qty: int, price: int) -> Event:
    data = {"item_id": 200, "qty": qty, "unit_price": price, "hunt_slug": "rochaz"}
    return Event(account_id=ACC, session_id=SES, type="item.consumed", received_at=at, data=data)


def test_sums_a_minute():
    km = KillMinutes()
    km.add(kill(T0, gold_autosell=5, active_level=30, drops=[{"name": "Pena", "qty": 2}]))
    km.add(
        kill(
            T0 + timedelta(seconds=30), active_level=31, drops=[{"name": "Pena"}, {"name": "Pedra"}]
        )
    )
    km.add(kill(T0 + timedelta(seconds=40), active_level=None))
    km.add(consumed(T0, 2, 26))
    rows = km.take()
    kills = next(r for r in rows if r["kills"])
    assert kills["minute"] == "2026-11-23T10:01:00+00:00"
    assert (kills["kills"], kills["xp"], kills["gold"]) == (3, 300, 125)
    assert (kills["active_level_sum"], kills["kills_leveled"]) == (61, 2)
    assert kills["drops"] == [{"name": "Pedra", "qty": 1}, {"name": "Pena", "qty": 3}]
    # o consumo vai numa linha sem pokémon ativo nem dia sazonal
    items = next(r for r in rows if not r["kills"])
    assert (items["consumables_gold"], items["active_species_id"], items["season"]) == (52, 0, "")
    assert len(km) == 0


def test_kill_without_active_shares_the_row_with_consumption():
    # sem pokémon ativo conhecido, o abate cai na mesma chave do consumo: uma linha com os dois
    km = KillMinutes()
    km.add(kill(T0, active_species_id=None))
    km.add(consumed(T0, 1, 26))
    [row] = km.take()
    assert (row["kills"], row["consumables_gold"], row["active_species_id"]) == (1, 26, 0)


def test_species_and_season_split_the_minute():
    km = KillMinutes()
    km.add(kill(T0, active_species_id=1, season="ROCK"))
    km.add(kill(T0, active_species_id=2, season="ROCK"))
    km.add(kill(T0, active_species_id=2, season=None))
    keys = sorted((r["active_species_id"], r["season"]) for r in km.take())
    assert keys == [(1, "ROCK"), (2, ""), (2, "ROCK")]


def test_only_closed_minutes_are_taken():
    km = KillMinutes()
    km.add(kill(T0))
    km.add(kill(T0 + timedelta(minutes=1)))
    rows = km.take(T0 + timedelta(minutes=1, seconds=10))  # 10:02 ainda está aberto
    assert [r["minute"] for r in rows] == ["2026-11-23T10:01:00+00:00"]
    assert len(km) == 1


def test_late_kill_goes_to_a_new_part():
    km = KillMinutes()
    km.add(kill(T0))
    [first] = km.take(T0 + timedelta(minutes=1))
    km.add(kill(T0 + timedelta(seconds=20)))  # chegou atrasado: o minuto 10:01 já foi entregue
    [late] = km.take(T0 + timedelta(minutes=2))
    assert (first["part"], late["part"]) == (0, 1)
    assert first["minute"] == late["minute"] and late["kills"] == 1


def test_aggregated_types_are_not_persisted_as_events():
    assert AGGREGATED == {"kill", "item.consumed"}
    assert not AGGREGATED & NOT_PERSISTED  # vão para kill_minute, não somem
    assert "battle.cura" in NOT_PERSISTED


async def test_memory_store_ignores_repeated_rows():
    store = MemoryStore()
    km = KillMinutes()
    km.add(kill(T0))
    rows = km.take()
    await store.insert_kill_minutes(rows)
    await store.insert_kill_minutes(rows)  # reenvio do buffer
    assert len(store.kill_minutes) == 1


async def test_rank_hunt_stats_reads_kill_minutes():
    store = MemoryStore()
    km = KillMinutes()
    km.add(kill(T0, active_level=30))
    km.add(kill(T0 + timedelta(seconds=10), active_level=32))
    km.add(kill(T0 + timedelta(minutes=1)))
    await store.insert_kill_minutes(km.take())
    [stats] = await store.rank_hunt_stats(ACC, T0 - timedelta(hours=1))
    assert (stats.hunt_slug, stats.kills, stats.active_minutes, stats.xp) == ("rochaz", 3, 2, 300)
    assert stats.avg_active_level == 31


@pytest.fixture
def telemetry(tmp_path):
    async def make(store: MemoryStore) -> TelemetryPlugin:
        settings = SimpleNamespace(
            telemetry_batch_size=100,
            telemetry_flush_s=3600,  # nada de flush periódico: o teste chama
            telemetry_buffer_path=str(tmp_path / "buffer.jsonl"),
        )
        ctx = SimpleNamespace(
            settings=settings,
            account_id=ACC,
            store=store,
            log=SimpleNamespace(warning=lambda *a: None),
        )
        plugin = TelemetryPlugin()
        await plugin.start(ctx)
        return plugin

    return make


async def test_telemetry_keeps_open_minute_until_stop(telemetry):
    store = MemoryStore()
    plugin = await telemetry(store)
    now = datetime.now(UTC)
    await plugin.on_event(kill(now - timedelta(minutes=2)))  # minuto fechado
    await plugin.on_event(kill(now))  # minuto aberto
    await plugin.on_event(Event(account_id=ACC, session_id=SES, type="pokemon.captured"))
    await plugin.flush()
    assert [e["type"] for e in store.events] == ["pokemon.captured"]
    assert [m["kills"] for m in store.kill_minutes] == [1]
    await plugin.stop()  # ao parar, o minuto aberto também vai
    assert sum(m["kills"] for m in store.kill_minutes) == 2


async def test_telemetry_buffers_minutes_when_store_fails(telemetry, tmp_path):
    store = MemoryStore()
    plugin = await telemetry(store)
    await plugin.on_event(kill(datetime.now(UTC) - timedelta(minutes=2)))
    store.fail_inserts = True
    await plugin.flush()
    assert store.kill_minutes == []
    assert list(tmp_path.glob("buffer.*.minutes.jsonl"))
    store.fail_inserts = False
    await plugin.flush()
    await plugin.stop()
    assert [m["kills"] for m in store.kill_minutes] == [1]
    assert not list(tmp_path.glob("buffer.*.jsonl"))
