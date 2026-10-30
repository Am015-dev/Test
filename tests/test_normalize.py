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


def test_parse_detail_jsonld_extracts_investment_fields():
    """The detail page's JSON-LD yields the rich fields the search cards lack."""
    from scout.collectors.xe import parse_detail_jsonld

    html = (FIXTURES / "xe_detail.html").read_text(encoding="utf-8")
    d = parse_detail_jsonld(html)
    assert d["year_built"] == 1984
    assert d["bedrooms"] == 2
    assert d["energy_class"] == "Ε"  # Greek Epsilon
    assert d["area_m2"] == 120.0
    assert d.get("heating")
    assert len(d.get("description", "")) > 50


def _jsonld_html(description: str, main_entity: dict | None = None) -> str:
    """Wrap a description (and optional mainEntity) in a RealEstateListing JSON-LD
    <script> the way an XE detail page embeds it."""
    import json

    node = {
        "@type": "RealEstateListing",
        "description": description,
        "mainEntity": main_entity or {},
    }
    return (
        '<script type="application/ld+json">' + json.dumps(node, ensure_ascii=False) + "</script>"
    )


def test_parse_detail_jsonld_extracts_prose_extras():
    """Heating/parking/storage/condition/delivery_year mined from the description prose."""
    from scout.collectors.xe import parse_detail_jsonld

    desc = (
        "Προς Πώληση Διαμέρισμα, Παπάγος, 55 τ.μ., 1ος Όροφος, 1 Υ/Δ, 1 Μπάνιο/α, "
        "Kουφώματα: Αλουμινίου, 1 parking, Έτος κατασκευής: 2025, "
        "Κατάσταση: υπό κατασκευή, Ενεργειακό Πιστοποιητικό: Α++, "
        "Χαρακτηριστικά: Ασανσέρ, Πόρτα Ασφαλείας, Αποθήκη, ... "
        "ΤΟ ΑΚΙΝΗΤΟ ΘΑ ΠΑΡΑΔΩΘΕΙ ΤΟ 2026, Ατομική - Φυσικό Αέριο Θέρμανση, Τιμή: 300.000€."
    )
    d = parse_detail_jsonld(_jsonld_html(desc))
    assert d["heating"] == "Ατομική - Φυσικό Αέριο"  # prose fallback (no amenity heating)
    assert d["parking"] == 1  # count captured, not just a bool
    assert d["storage"] is True
    assert d["condition"] == "under_construction"
    assert d["delivery_year"] == 2026
    # Existing keys are untouched.
    assert d["description"] == desc


def test_parse_detail_jsonld_prose_heating_never_overrides_amenity():
    """The structured amenity heating wins; the prose fallback only fills a gap."""
    from scout.collectors.xe import parse_detail_jsonld

    d = parse_detail_jsonld(
        _jsonld_html(
            "Ωραίο διαμέρισμα, Ατομική - Φυσικό Αέριο Θέρμανση.",
            main_entity={"amenityFeature": [{"name": "Θέρμανση: Πλήρως αυτόνομη"}]},
        )
    )
    assert d["heating"] == "Πλήρως αυτόνομη"


def test_parse_detail_jsonld_extras_absent_when_not_stated():
    """A plain description yields none of the new keys (they are strictly optional)."""
    from scout.collectors.xe import parse_detail_jsonld

    d = parse_detail_jsonld(_jsonld_html("Πωλείται φωτεινό διαμέρισμα στο κέντρο."))
    for key in ("heating", "parking", "storage", "condition", "delivery_year"):
        assert key not in d
    assert d.get("description")  # description itself is still captured


def test_parse_detail_jsonld_condition_variants():
    """Each condition keyword maps to its label; needs_renovation wins over renovated."""
    from scout.collectors.xe import parse_detail_jsonld

    def cond(text: str):
        return parse_detail_jsonld(_jsonld_html(text)).get("condition")

    assert cond("Νεόδμητο διαμέρισμα, παραδοτέο άμεσα.") == "newbuild"
    assert cond("Πλήρως Ανακαινισμένο το 2020.") == "renovated"
    assert cond("Ακίνητο που χρήζει ανακαίνισης.") == "needs_renovation"
    assert cond("Απλό διαμέρισμα χωρίς ιδιαιτερότητες.") is None


def test_parse_detail_jsonld_fails_soft_on_garbage():
    from scout.collectors.xe import parse_detail_jsonld

    assert parse_detail_jsonld("<html>no json-ld here</html>") == {}
    assert parse_detail_jsonld("<script type='application/ld+json'>{bad</script>") == {}


def test_parse_detail_coordinates_from_bounding_box():
    """The listing's real (lat, lng) comes from the detail page's geo box centre —
    what makes accurate per-listing metro distance possible."""
    from scout.collectors.xe import parse_detail_coordinates

    html = (FIXTURES / "xe_detail.html").read_text(encoding="utf-8")
    lat, lng = parse_detail_coordinates(html)
    assert lat is not None and 37.9 < lat < 38.2  # north Athens
    assert lng is not None and 23.7 < lng < 23.9
    # Fails soft when the box isn't present.
    assert parse_detail_coordinates("<html>no coords</html>") == (None, None)


def test_normalize_drops_negative_price():
    """Regression: a garbled negative price must be dropped (truthiness let it through
    before), else it produces a maxed-out false 'below market' signal downstream."""
    raw = {
        "source": "xe",
        "source_id": "neg1",
        "url": "http://x",
        "price": -50000,
        "area_m2": 60.0,
    }
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
    assert raw["floor"] == 1.0  # "Ισόγειο,1ος" maisonette -> its upper (1st) level
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


def test_parse_xe_card_current_markup():
    """XE now labels card fields with data-testid (real card captured from a GitHub runner)."""
    html = (FIXTURES / "xe_card_v2.html").read_text(encoding="utf-8")
    raw = XeCollector.__new__(XeCollector).parse_card(html, base_url="https://www.xe.gr")
    assert raw["source_id"] == "aa35718c-2b0d-4cc6-94c9-58b783417fdb"
    assert raw["price"] == 365_000 and raw["area_m2"] == 86
    assert raw["floor"] == 4 and raw["bedrooms"] == 2 and raw["year_built"] == 1979
    assert (
        raw["neighborhood"] == "Παπάγου (Υπουργείο Μεταφορών)" and raw["is_private_seller"] is True
    )
    assert normalize(raw) is not None
