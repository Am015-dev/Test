"""Tests for rental-comparable aggregation."""

from __future__ import annotations

from scout.rent_comps import OVERALL_KEY, compute_rent_comps, rent_for


def _row(rent, area, hood):
    return {"rent": rent, "area_m2": area, "neighborhood": hood}


def test_median_per_neighbourhood_and_overall():
    rows = [
        _row(1200, 100, "A"),  # 12
        _row(1500, 100, "A"),  # 15
        _row(1800, 100, "A"),  # 18 -> median A = 15
        _row(900, 100, "B"),  # 9
        _row(1100, 100, "B"),  # 11 -> only 2 samples, below threshold
    ]
    comps = compute_rent_comps(rows)
    assert comps["A"] == 15.0
    assert "B" not in comps  # < 3 samples -> no neighbourhood median
    assert comps[OVERALL_KEY] == 12.0  # median of [12,15,18,9,11]


def test_rent_for_falls_back_to_overall_then_none():
    comps = {"A": 15.0, OVERALL_KEY: 12.0}
    assert rent_for(comps, "A") == 15.0
    assert rent_for(comps, "Unknown") == 12.0  # area-wide fallback
    assert rent_for({}, "A") is None  # no comps at all


def test_junk_rows_skipped():
    rows = [
        _row(0, 100, "A"),  # zero rent
        _row(1200, 0, "A"),  # zero area
        _row(200000, 90, "A"),  # sale price leaked in -> €2222/m², out of band
        _row(50, 100, "A"),  # €0.5/m², below band
    ]
    assert compute_rent_comps(rows) == {}
