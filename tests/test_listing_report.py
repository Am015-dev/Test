"""Tests for the single-file HTML listing report (backlog #27)."""

from __future__ import annotations

from scout.listing_report import build_report_html
from scout.ui.format import euro


def _full_listing(**overrides) -> dict:
    base = dict(
        neighborhood="Ano Cholargos",
        title="2-bedroom flat near the metro",
        price=200_000,
        price_per_m2=2500.0,
        area_m2=80.0,
        score=72.0,
        deal_grade="B",
        deal_grade_reason="strong overall fit, 4.1% net yield",
        deal_thesis="Offer €185k; motivated seller, priced under model.",
        bedrooms=2,
        floor=3.0,
        year_built=2005,
        energy_class="C",
        nearest_metro="Holargos",
        metro_distance_m=400,
        net_yield=0.041,
        gross_yield=0.054,
        est_monthly_rent=900,
        is_private_seller=False,
        url="https://example.gr/listing/0001",
    )
    base.update(overrides)
    return base


def test_report_is_nonempty_html_with_core_fields():
    html = build_report_html(_full_listing())
    assert isinstance(html, str)
    assert html
    assert "<html" in html
    # Neighborhood and the formatted price both appear in the rendered report.
    assert "Ano Cholargos" in html
    assert euro(200_000) in html  # "€200,000"
    # The investment case metrics are surfaced.
    assert "Net yield" in html
    assert "Cap rate" in html
    # The listing URL is linked.
    assert "https://example.gr/listing/0001" in html


def test_missing_optional_fields_still_valid():
    # Only a price — everything else absent. Must not raise, still valid HTML.
    html = build_report_html({"price": 150_000, "neighborhood": "Pagrati"})
    assert isinstance(html, str)
    assert "<html" in html
    assert "Pagrati" in html
    assert euro(150_000) in html


def test_empty_dict_does_not_raise():
    html = build_report_html({})
    assert isinstance(html, str)
    assert "<html" in html


def test_none_input_does_not_raise():
    html = build_report_html(None)  # type: ignore[arg-type]
    assert "<html" in html


def test_injected_html_is_escaped():
    payload = "<script>alert('xss')</script>"
    html = build_report_html(_full_listing(neighborhood=payload, title=payload))
    # No raw script tag passthrough — it must be entity-escaped.
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_url_is_attribute_escaped():
    html = build_report_html(_full_listing(url='https://x.gr/"><script>hack()</script>'))
    assert "<script>hack()</script>" not in html
