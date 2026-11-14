"""Fila de hunts por tempo até a captura (docs/design/fase-3b-catalogo-e-fila.md, casos 15 a 22)."""

from datetime import UTC, datetime, timedelta

import pytest

from pokeidle_farm.gamedata import HuntCatalog, SpeciesCatalog
from pokeidle_farm.rank_queue import observed_chances, plan_queue

from .test_gamedata import BOLAS, CAPTURA, KANTO, creature


def hunt(slug, pid, name, level, area="kanto") -> dict:
    return {
        "area": area,
        "nome": name,
        "slug": slug,
        "nivel": level,
        "especies": [{"nome": name, "pokeId": pid, "pontos": 15}],
        "totalSpawns": 15,
    }


HUNTS = HuntCatalog.from_welcome(
    {
        "t": "welcome",
        "hunts": [
            hunt("caterpie", 10, "Caterpie", 1),
            hunt("gyarados", 130, "Gyarados", 100),
            hunt("tauros", 128, "Tauros", 60),
            hunt("outland1", 2001, "Outlander", 150, area="outland"),
            hunt("treecko_hoenn", 13252, "Treecko", 500, area="orre"),
        ],
        "captura": CAPTURA,
        "catalogoBolas": BOLAS,
    }
)
SPECIES = SpeciesCatalog.from_creatures(
    [{"creatures": [*KANTO, creature(2001, "Outlander"), creature(13252, "Treecko", 13253)]}]
)


def plan(**kw):
    args = {
        "hunts": HUNTS,
        "species": SPECIES,
        "trainer_level": 150,
        "scored_species": set(),
        "ball_id": 4,
        "kills_per_hour": {},
        "default_kills_per_hour": 1000.0,
        "known_chance": {},
    }
    args.update(kw)
    return plan_queue(**args)


def test_reach_by_trainer_level():
    slugs = {q.slug for q in plan()}
    assert "treecko_hoenn" not in slugs
    assert {"caterpie", "gyarados", "tauros", "outland1"} <= slugs


def test_scored_species_leave_the_queue():
    assert "caterpie" not in {q.slug for q in plan(scored_species={10})}


def test_chance_by_stage():
    q = {i.slug: i for i in plan()}
    assert q["caterpie"].chance == pytest.approx(0.0075 * 4 / 2.8669 * 1.4)
    assert q["caterpie"].chance_source == "stage"
    assert q["gyarados"].chance == pytest.approx(0.0075 * 4 / 4.4681 * 1.4)
    assert q["caterpie"].hours == pytest.approx(1 / (1000 * 0.0075 * 4 / 2.8669 * 1.4))
    assert plan()[0].slug == "caterpie"


def test_without_pokedex_uses_worst():
    q = plan(species=None)
    assert {i.chance_source for i in q} == {"worst"}
    poke = plan(species=None, ball_id=1)
    assert poke[0].chance == pytest.approx(0.003)  # 0,0075 / 4,4681 × 1,4 ≈ 0,00235 → piso


def test_observed_beats_stage():
    q = {i.slug: i for i in plan(known_chance={130: 0.02})}
    assert q["gyarados"].chance == 0.02 and q["gyarados"].chance_source == "observed"


def test_measured_kills_per_hour_wins():
    q = plan(kills_per_hour={"tauros": 2000.0})
    order = [i.slug for i in q]
    assert order.index("tauros") < order.index("gyarados")  # mesmo estágio, mais abates/h
    t = next(i for i in q if i.slug == "tauros")
    assert t.kills_per_hour == 2000.0 and t.kph_known is True


def test_tie_break_by_level_then_slug():
    q = plan(species=None)  # todas com a mesma chance e o mesmo abates/h
    assert [i.slug for i in q] == ["caterpie", "tauros", "gyarados", "outland1"]


@pytest.mark.parametrize(
    "kw", [{"ball_id": 99}, {"default_kills_per_hour": 0.0}, {"trainer_level": 0}]
)
def test_empty_cases(kw):
    assert plan(**kw) == []


def _attempt(chance, slug="caterpie", ball=4, minutes=0) -> tuple[datetime, dict]:
    at = datetime(2026, 11, 14, 17, tzinfo=UTC) + timedelta(minutes=minutes)
    return at, {"ball_id": ball, "chance": chance, "hunt_slug": slug}


def test_observed_chances():
    attempts = [_attempt(0.015)]
    assert observed_chances(attempts, HUNTS, 4) == {10: pytest.approx(0.015)}
    assert observed_chances(attempts, HUNTS, 2) == {10: pytest.approx(0.0075)}
    assert observed_chances(attempts, HUNTS, 1) == {10: pytest.approx(0.00375)}
    ignored = [_attempt(0.015, slug="fora"), _attempt(None)]
    assert observed_chances(ignored, HUNTS, 4) == {}
    newest = [_attempt(0.010, minutes=5), _attempt(0.015, minutes=1)]
    assert observed_chances(newest, HUNTS, 4) == {10: pytest.approx(0.010)}
