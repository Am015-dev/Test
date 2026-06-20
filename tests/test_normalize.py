"""Parser + normalize tests, driven by saved HTML fixtures (offline)."""

from __future__ import annotations

from pathlib import Path

from scout.collectors.spitogatos import SpitogatosCollector
from scout.collectors.xe import XeCollector
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


def test_parse_xe_real_card():
    """XE parser against a card captured from XE's live results page."""
    html = (FIXTURES / "xe_card.html").read_text(encoding="utf-8")
    raw = XeCollector(Strategy(), save_raw=False).parse_card(
        html, base_url="https://www.xe.gr/property/results"
    )
    assert raw["source"] == "xe"
    assert raw["source_id"] == "782567"
    assert raw["url"].startswith("https://www.xe.gr/property/")
    assert raw["price"] == 1_600_000
    assert raw["area_m2"] == 257.0  # parsed out of the title
    assert raw["floor"] == 0.0  # "Ισόγειο,1ος" -> ground-floor entry
    assert raw["bedrooms"] == 4
    assert raw["year_built"] == 2021
    assert raw["neighborhood"]  # non-empty, taken before the "|" separator
    # Real card normalizes into the canonical schema.
    listing = normalize(raw)
    assert listing is not None
    assert listing.price == 1_600_000


def test_parse_xe_d_form_url_uses_uuid():
    """The /property/d/<category>/<uuid>/ form must yield the UUID, not the slug.

    Regression: every `d` listing previously collapsed onto the category slug
    ("poliseis-katoikion") and dedup wiped them down to a single record.
    """
    uuid = "bdfc1a03-3272-4824-899b-c10ea028e12b"
    html = (
        '<div class="common-ad-body"><a '
        f'href="/property/d/poliseis-katoikion/{uuid}/cholargos-diamerisma">'
        '<div class="common-property-ad-title"><h3>Διαμέρισμα 91 τ.μ.</h3></div>'
        '<span class="property-ad-price">200.000&nbsp;€</span>'
        '<h3 class="common-property-ad-address">Χολαργός (Τσακός) | Πώληση κατοικίας</h3>'
        "</a></div>"
    )
    raw = XeCollector(Strategy(), save_raw=False).parse_card(
        html, base_url="https://www.xe.gr/property/results"
    )
    assert raw["source_id"] == uuid
    # Transaction suffix is stripped from the address (kept clean for geocoding).
    assert raw["address"] == "Χολαργός (Τσακός)"
    assert raw["neighborhood"] == "Χολαργός (Τσακός)"


def test_xe_area_anchored_and_url_cleaned():
    """Area must come from the τ.μ. unit (not a leading room count), and the stored
    URL must drop XE's tracking query string (which carries link-breaking spaces)."""
    html = (
        '<div class="common-ad-body"><a '
        'href="/property/d/poliseis-katoikion/abc-uuid-1/cholargos'
        '?widget_name=search results sponsored placement&rank_in_widget=2">'
        '<div class="common-property-ad-title"><h3>Διαμέρισμα 2 δωμ. 85 τ.μ.</h3></div>'
        '<span class="property-ad-price">200.000&nbsp;€</span>'
        '<h3 class="common-property-ad-address">Χολαργός (Τσακός) | Πώληση κατοικίας</h3>'
        "</a></div>"
    )
    raw = XeCollector(Strategy(), save_raw=False).parse_card(
        html, base_url="https://www.xe.gr/property/results"
    )
    assert raw["area_m2"] == 85.0  # the τ.μ. value, not the "2 δωμ." room count
    assert raw["source_id"] == "abc-uuid-1"
    assert "?" not in raw["url"] and " " not in raw["url"]
    assert raw["url"] == "https://www.xe.gr/property/d/poliseis-katoikion/abc-uuid-1/cholargos"
