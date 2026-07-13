"""Tests for the investment decision calculators + data-confidence score."""

from __future__ import annotations

from scout.data_quality import listing_confidence
from scout.investment import (
    break_even_rent,
    deal_grade,
    net_yield_sensitivity,
    payback_years,
    rent_vs_buy_monthly,
    yield_on_offer,
)


def test_net_yield_sensitivity_orders_scenarios():
    s = net_yield_sensitivity(200_000, 12_000, 80.0, False)
    assert s is not None
    assert s["pessimistic"] < s["base"] < s["optimistic"]


def test_net_yield_sensitivity_none_without_rent():
    assert net_yield_sensitivity(200_000, None, 80.0, False) is None


def test_yield_on_offer_beats_asking_yield():
    at_ask = yield_on_offer(200_000, 12_000, 80.0, False)
    at_offer = yield_on_offer(180_000, 12_000, 80.0, False)
    assert at_offer > at_ask  # a lower price → higher yield


def test_break_even_rent_positive():
    be = break_even_rent(200_000, 80.0, False)
    assert be and be > 0


def test_payback_years_reasonable():
    p = payback_years(200_000, 12_000, 80.0, False)
    assert p and 10 < p < 40  # unlevered payback in a sane band


def test_rent_vs_buy():
    r = rent_vs_buy_monthly(
        200_000, own_monthly_rent_saved=900, area_m2=80.0, is_private_seller=False
    )
    assert r is not None and "advantage" in r


def test_deal_grade_caps_incomplete_data():
    strong = dict(score=70, net_yield=0.05, value_gap_pct=0.15, negotiation_score=50)
    a = deal_grade(data_complete=True, **strong)
    capped = deal_grade(data_complete=False, **strong)
    assert a.grade == "A"
    assert capped.grade == "B"  # never an A without complete data


def test_listing_confidence_scales_with_known_fields():
    full = dict(
        energy_class="B",
        year_built=2000,
        location_precision="exact",
        rent_estimated=False,
        listed_date="2026-07-01",
    )
    bare = dict(
        energy_class=None, year_built=None, location_precision="approx", rent_estimated=True
    )
    assert listing_confidence(full) == 100
    assert listing_confidence(bare) == 0
