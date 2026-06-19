"""Parser + normalize tests, driven by saved HTML fixtures (offline)."""

from __future__ import annotations

from pathlib import Path

from scout.collectors.spitogatos import SpitogatosCollector
from scout.config import Strategy
from scout.normalize import normalize

FIXTURES = Path(__file__).parent / "fixtures"


def _collector() -> SpitogatosCollector:
    return SpitogatosCollector(Strategy(), save_raw=False)


def test_parse_full_card():
    html = (FIXTURES / "spitogatos_card.html").read_text(encoding="utf-8")
    raw = _collector().parse_card(html, base_url="https://www.spitogatos.gr/en/search")
    assert raw["source"] == "spitogatos"
    assert raw["source_id"] == "1234567"
    assert raw["url"] == "https://www.spitogatos.gr/en/property/1234567"
    assert raw["price"] == 215000
    assert raw["area_m2"] == 82.0
    assert raw["floor"] == 3.0
    assert raw["is_currently_rented"] is True
    assert raw["listed_rent"] == 850
    assert raw["is_private_seller"] is True


def test_parse_minimal_card_fails_soft():
    """Missing fields become None; parser never raises."""
    html = (FIXTURES / "spitogatos_card_minimal.html").read_text(encoding="utf-8")
    raw = _collector().parse_card(html, base_url="https://www.spitogatos.gr/en/search")
    assert raw["source_id"] == "9988"
    assert raw["area_m2"] is None
    assert raw["floor"] == 0.0  # ισόγειο
    assert raw["neighborhood"] is None


def test_normalize_maps_to_listing():
    html = (FIXTURES / "spitogatos_card.html").read_text(encoding="utf-8")
    raw = _collector().parse_card(html, base_url="https://www.spitogatos.gr/en/search")
    listing = normalize(raw)
    assert listing is not None
    assert listing.price == 215000
    assert listing.neighborhood == "Άνω Χολαργός"
    # description is portal-specific and must not leak onto the canonical schema.
    assert not hasattr(listing, "description")


def test_normalize_drops_unusable_raw():
    # No price/area -> unusable -> dropped.
    raw = {"source": "spitogatos", "source_id": "x", "url": "http://x", "price": None}
    assert normalize(raw) is None
