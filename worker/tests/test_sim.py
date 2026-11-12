"""Confere se os sorteios seguem as tabelas da seção 14 dos Termos."""

import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pokeidle_farm.sim.generator import EventSimulator, SimConfig
from pokeidle_farm.sim.rolls import (
    POTENCY_TABLE,
    QUALITY_TABLE,
    roll_capture,
    roll_ivs,
    roll_potency,
    roll_quality,
)

N = 200_000


def test_tables_sum_to_100():
    assert sum(p[1] for p in POTENCY_TABLE) == pytest.approx(100)
    assert sum(q[2] for q in QUALITY_TABLE) == pytest.approx(100)


def test_potency_distribution():
    rng = random.Random(1)
    c = Counter(roll_potency(rng) for _ in range(N))
    assert c[1] / N == pytest.approx(0.74495, abs=0.005)
    assert c[2] / N == pytest.approx(0.20, abs=0.005)
    assert c[3] / N == pytest.approx(0.05, abs=0.002)
    assert c[4] / N == pytest.approx(0.005, abs=0.001)


def test_quality_range_and_gap():
    rng = random.Random(2)
    qs = [roll_quality(rng) for _ in range(N)]
    assert min(qs) >= 0.8 and max(qs) <= 1.8
    assert all(round(q, 3) == q for q in qs)
    assert not any(1.6 < q < 1.7 for q in qs)  # faixa ausente nos Termos
    exact_18 = sum(q == 1.8 for q in qs) / N
    assert exact_18 == pytest.approx(0.0028846 + 0.0067308 / 101, abs=0.001)
    assert sum(1.0 <= q < 1.1 for q in qs) / N == pytest.approx(0.3404, abs=0.01)


def test_ivs_range_and_shiny_floor():
    rng = random.Random(3)
    for _ in range(5000):
        ivs = roll_ivs(rng, shiny=False)
        assert set(ivs) == {"hp", "atk", "def", "spa", "spd", "spe"}
        assert all(1 <= v <= 32 for v in ivs.values())
    for _ in range(2000):
        assert sum(roll_ivs(rng, shiny=True).values()) > 110


def test_shiny_odds():
    rng = random.Random(4)
    shinies = sum(roll_capture(rng, shiny_odds=100).shiny for _ in range(N))
    assert shinies / N == pytest.approx(0.01, abs=0.002)


def test_generator_events_are_ordered_and_marked():
    acc = uuid4()
    sim = EventSimulator(acc, SimConfig(seed=42, kills_per_minute=30))
    end = datetime.now(UTC)
    evs = list(sim.generate(end - timedelta(hours=6), end))
    types = Counter(e.type for e in evs)
    assert types["kill"] > 5000
    assert types["capture_attempt"] > 0 and types["pokemon.captured"] > 0
    assert evs[0].type == "state.snapshot"
    assert all(e.raw.get("_sim") is True for e in evs)
    assert all(e.account_id == acc for e in evs)
    ts = [e.received_at for e in evs]
    assert ts == sorted(ts) and ts[-1] < end
    cap = next(e for e in evs if e.type == "pokemon.captured")
    assert {"species", "potency", "quality", "ivs", "iv_sum", "shiny"} <= set(cap.data)
    assert cap.data["iv_sum"] == sum(cap.data["ivs"].values())


def test_generator_is_reproducible_with_seed():
    acc = uuid4()
    end = datetime(2026, 11, 12, tzinfo=UTC)
    a = [
        (e.type, e.data)
        for e in EventSimulator(acc, SimConfig(seed=7)).generate(end - timedelta(hours=1), end)
    ]
    b = [
        (e.type, e.data)
        for e in EventSimulator(acc, SimConfig(seed=7)).generate(end - timedelta(hours=1), end)
    ]
    assert a == b
