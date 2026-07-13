"""Tests for the liquidity, EPBD-capex, price-percentile and leverage helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

from scout.analytics import area_ppm2_distributions, ppm2_percentile_cheaper
from scout.epbd import epbd_flag
from scout.finance import leverage_oneliner
from scout.liquidity import liquidity_by_area

NOW = datetime(2026, 7, 13)


def _listing(area, status, days_listed=None):
    fs = NOW - timedelta(days=days_listed) if days_listed is not None else NOW
    return {"search_area": area, "status": status, "first_seen": fs, "last_seen": NOW}


def test_liquidity_reports_median_dwell_and_absorption():
    listings = [_listing("Nea Smyrni", "gone", d) for d in [30, 40, 50, 60, 70, 80, 90, 100]]
    listings += [_listing("Nea Smyrni", "active") for _ in range(2)]
    out = liquidity_by_area(listings)
    liq = out["Nea Smyrni"]
    assert liq.cleared == 8 and liq.active == 2
    assert liq.median_days_on_market == 65  # median of 30..100
    assert abs(liq.absorption_rate - 8 / 10) < 1e-9


def test_liquidity_hidden_below_min_sample():
    out = liquidity_by_area([_listing("Tiny", "gone", 40) for _ in range(3)])
    assert out["Tiny"].median_days_on_market is None  # too few cleared to trust


def test_epbd_flags_poor_class_with_capex():
    f = epbd_flag("G", area_m2=80.0)
    assert f.at_risk and f.est_capex and f.est_capex > 0
    assert "EPBD" in f.note


def test_epbd_no_flag_for_good_or_unknown_class():
    assert not epbd_flag("A", 80.0).at_risk
    assert not epbd_flag(None, 80.0).at_risk  # missing data never invents a liability
    assert epbd_flag("A", 80.0).est_capex is None


def test_epbd_worse_class_costs_more():
    assert epbd_flag("G", 80.0).est_capex > epbd_flag("E", 80.0).est_capex


def test_price_percentile_is_cheaper_share():
    listings = [{"search_area": "A", "price_per_m2": p} for p in [1000, 2000, 3000, 4000, 5000]]
    dist = area_ppm2_distributions(listings)
    # A 1500 €/m² flat is cheaper than the 2000..5000 four of five → 0.8.
    assert ppm2_percentile_cheaper(1500, dist["A"]) == 0.8
    assert ppm2_percentile_cheaper(6000, dist["A"]) == 0.0  # dearer than all


def test_price_percentile_needs_enough_comps():
    assert ppm2_percentile_cheaper(1500, [1000, 2000]) is None


def test_leverage_oneliner_formats_cash_on_cash():
    line = leverage_oneliner(200_000, annual_rent=12_000, area_m2=80.0, is_private_seller=False)
    assert line is not None and "cash-on-cash" in line and "down" in line


def test_leverage_oneliner_none_without_rent():
    assert (
        leverage_oneliner(200_000, annual_rent=None, area_m2=80.0, is_private_seller=False) is None
    )
