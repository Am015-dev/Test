"""Offline parse tests for the Green-Acres collector, driven by a saved real card."""

from __future__ import annotations

from pathlib import Path

from scout.collectors.greenacres import GreenAcresCollector
from scout.config import Strategy

FIXTURE = Path(__file__).parent / "fixtures" / "greenacres_card.html"


def _collector() -> GreenAcresCollector:
    return GreenAcresCollector(Strategy(), save_raw=False)


def test_parse_card_extracts_all_fields():
    raw = _collector().parse_card(FIXTURE.read_text(encoding="utf-8"), base_url="x")
    assert raw["source"] == "greenacres"
    assert raw["source_id"] == "A7b2xz1i68ximzcy"
    assert raw["price"] == 545000
    assert raw["area_m2"] == 199.0
    assert raw["bedrooms"] == 4
    assert raw["neighborhood"] == "Chalandri"
    assert raw["property_type"] == "apartment"
    # The detail URL is base64-decoded from data-o, not guessed.
    assert raw["url"].endswith("/apartment/chalandri/A7b2xz1i68ximzcy.htm")


def test_parse_card_fails_soft_on_garbage():
    """A card without the expected structure yields Nones, never raises."""
    raw = _collector().parse_card("<div class='announce-card' data-advertid='x'></div>", "x")
    assert raw["source_id"] == "x"
    assert raw["price"] is None
    assert raw["area_m2"] is None


def test_slug_maps_area_names():
    c = _collector()
    assert c._slug("Agia Paraskevi") == "agia-paraskevi"
    assert c._slug("Cholargos") == "cholargos"


def test_keep_filters_type_band_and_location():
    c = _collector()
    search = Strategy().search
    search.price_min, search.price_max, search.area_min_m2 = 120000, 320000, 45

    def raw(**kw):
        base = dict(
            url="u", price=200000, area_m2=80, property_type="apartment", neighborhood="Chalandri"
        )
        base.update(kw)
        return base

    assert c._keep(raw(), "Chalandri", search)
    assert not c._keep(raw(property_type="business-premises"), "Chalandri", search)  # wrong type
    assert not c._keep(raw(price=900000), "Chalandri", search)  # out of band
    assert not c._keep(raw(neighborhood="Glyfada"), "Chalandri", search)  # similar-listings tail
    assert not c._keep(raw(area_m2=20), "Chalandri", search)  # below area floor


def test_search_urls_scoped_to_run_municipality_not_all_areas():
    """A per-area run must scrape ONLY its municipality — not every configured area.

    Regression for the daily-refresh staleness bug: green-acres iterated
    ``all_areas()``, so one ``run_for_area`` re-scraped all 55 areas (4-7s detail fetch
    per card) and the 45-min collect step was killed before ``run()`` reached its store
    phase — no ``last_seen`` ever advanced. Like XE, it must yield exactly one URL for the
    scoped municipality regardless of how many extra areas are configured."""
    strategy = Strategy()
    strategy.search.municipality = "Nea Smyrni"
    strategy.search.areas = ["Cholargos", "Pagkrati", "Glyfada"]  # must NOT be scraped
    urls = _collector().search_urls(strategy)
    assert urls == ["https://www.green-acres.gr/property-for-sale/nea-smyrni"]
