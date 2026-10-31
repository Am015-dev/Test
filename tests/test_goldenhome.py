"""Golden Home collector: offline parse tests on a real captured page, pagination,
the SOURCES toggle, and cross-portal twins with XE."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from scout import market_intel as mi
from scout.collectors import default_collectors, enabled_sources
from scout.collectors import goldenhome as gh
from scout.collectors.goldenhome import GoldenHomeCollector
from scout.config import Strategy
from scout.normalize import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "goldenhome_search.html"


def _collector(municipality: str = "Cholargos") -> GoldenHomeCollector:
    strategy = Strategy()
    strategy.search.municipality = municipality
    return GoldenHomeCollector(strategy, save_raw=False)


def _cards() -> dict[str, dict]:
    c = _collector()
    tree = HTMLParser(FIXTURE.read_text(encoding="utf-8"))
    raws = [c.parse_card(n.html, base_url="x") for n in tree.css(c.CARD_SELECTOR)]
    return {r["source_id"]: r for r in raws}


def test_parse_card_reads_every_field_from_the_real_card():
    r = _cards()["437446"]
    assert r["source"] == "goldenhome"
    assert r["url"] == "https://goldenhome.gr/property/view/437446"
    assert r["title"] == "Ρετιρέ 107 τ.μ."
    assert r["price"] == 270_000
    assert r["area_m2"] == 107.0
    assert r["bedrooms"] == 3
    assert r["floor"] == 4.0
    assert r["year_built"] == 1975
    assert r["is_unfinished"] is False
    # XE's "Municipality (quarter)" form, so twins/comps share the municipality key.
    assert r["neighborhood"] == "Χολαργός (Φανερωμένη)"
    assert r["photo_count"] == 25
    assert r["image_url"].startswith("https://goldenhome.gr/images/PropertyPhotos/437446/")


def test_future_build_year_is_flagged_under_construction_not_new():
    r = _cards()["530643"]
    assert r["year_built"] == 2028 and r["is_unfinished"] is True
    lst = normalize(r, now=datetime(2026, 10, 31))
    assert lst.is_unfinished is True
    assert lst.year_built is None  # a future year is not a fact about the building


def test_floor_words_follow_the_shared_xe_mapping():
    assert _cards()["527374"]["floor"] == 0.0  # "0 (Υπερυψ. Ισόγειο)"
    assert GoldenHomeCollector._floor("0  (Ημιυπόγειο)") == -1.0
    assert GoldenHomeCollector._floor("3") == 3.0
    assert GoldenHomeCollector._floor(None) is None


def test_keep_drops_air_rights_and_out_of_band():
    cards = _cards()
    search = Strategy().search
    search.price_min, search.price_max, search.area_min_m2 = 100_000, 400_000, 45
    assert GoldenHomeCollector._keep(cards["437446"], search)
    assert not GoldenHomeCollector._keep(cards["436231"], search)  # "Υπόλοιπο Υψούν/Αέρας"
    assert not GoldenHomeCollector._keep({**cards["437446"], "price": 900_000}, search)
    assert not GoldenHomeCollector._keep({**cards["437446"], "area_m2": 30}, search)


def test_parse_card_fails_soft_on_garbage():
    raw = _collector().parse_card("<article class='property-card' data-key='9'></article>", "x")
    assert raw["source_id"] == "9"
    assert raw["price"] is None and raw["area_m2"] is None and raw["url"] is None
    assert normalize(raw) is None  # no url/price → dropped, never stored


def test_search_url_is_the_run_municipality_only():
    assert _collector().search_urls(_collector().strategy) == [
        "https://goldenhome.gr/property/pwlisi/katoikies/perioxi-holargos"
    ]
    c = _collector("Atlantis")
    assert c.search_urls(c.strategy) == []  # unknown area: skipped, not guessed


def test_every_weekly_area_has_a_golden_home_page():
    weekly = (
        "Cholargos,Papagou,Agia Paraskevi,Chalandri,Vrilissia,Marousi,Zografou,Psychiko,"
        "Filothei,Irakleio,Nea Filadelfeia,Pefki,Galatsi,Ampelokipoi,Metamorfosi"
    )
    assert [a for a in weekly.split(",") if a not in gh.AREA_SLUGS] == []


def test_collect_follows_pagination_and_stops(monkeypatch):
    page1 = FIXTURE.read_text(encoding="utf-8")
    page2 = page1.replace('class="next"', 'class="next disabled"').replace(
        '<li class="next disabled"><a', '<li class="next disabled"><span'
    )
    fetched: list[str] = []

    def fake_fetch(self, session, url):
        fetched.append(url)
        return page1 if len(fetched) == 1 else page2.replace('data-key="437446"', 'data-key="1"')

    monkeypatch.setattr(GoldenHomeCollector, "_fetch", fake_fetch)
    monkeypatch.setattr(GoldenHomeCollector, "_pause", lambda self: None)
    c = _collector()
    c.strategy.search.price_min, c.strategy.search.price_max = 50_000, 2_000_000
    raws = list(c.collect())
    assert fetched[0].endswith("/katoikies/perioxi-holargos")
    assert "page=2" in fetched[1]
    assert len(fetched) == 2
    assert {r["source"] for r in raws} == {"goldenhome"}
    assert "436231" not in {r["source_id"] for r in raws}  # air rights never kept


# ---- SOURCES toggle -----------------------------------------------------------------------


def test_sources_default_is_unchanged(monkeypatch):
    monkeypatch.delenv("SOURCES", raising=False)
    assert enabled_sources() == ["xe", "greenacres"]
    assert [c.source for c in default_collectors(Strategy())] == ["xe", "greenacres"]


def test_sources_env_selects_collectors_and_ignores_unknown(monkeypatch):
    monkeypatch.setenv("SOURCES", "xe, goldenhome,nope,xe")
    assert enabled_sources() == ["xe", "goldenhome"]
    assert [c.source for c in default_collectors(Strategy())] == ["xe", "goldenhome"]


# ---- cross-portal twins ---------------------------------------------------------------------


@pytest.fixture
def same_flat_two_portals():
    """The real Golden Home card 437446 and an XE listing of the same flat (same area,
    m², floor, year; price 3 % apart), as the UI loads them."""
    g = normalize(_cards()["437446"], now=datetime(2026, 10, 31)).model_dump()
    g.update(id=2, price_per_m2=g["price"] / g["area_m2"])
    x = {
        "id": 1,
        "source": "xe",
        "title": "Διαμέρισμα 107 τ.μ.",
        "price": 278_000,
        "area_m2": 107.0,
        "price_per_m2": 278_000 / 107,
        "floor": 4.0,
        "year_built": 1975,
        "neighborhood": "Χολαργός (Φανερωμένη)",
    }
    return x, g


def test_xe_and_golden_home_listing_of_one_flat_are_twins(same_flat_two_portals):
    x, g = same_flat_two_portals
    intel = mi.build([x, g], year=2026)
    assert [t["source"] for t in intel.twins(x)] == ["goldenhome"]
    assert [t["source"] for t in intel.twins(g)] == ["xe"]


def test_source_survives_normalize_for_the_ui():
    lst = normalize(_cards()["437446"])
    assert lst.source == "goldenhome" and lst.photo_count == 25
