"""Guards that keep DATA ERRORS out of the top of the ranking.

Real cases from the live DB drive these: a 300 m² "Πολυκατοικία" (apartment building) priced
as one flat, a 2028 build year, a 69% yield. A normal 85 m² flat must NOT flag.
"""

from __future__ import annotations

from scout.data_quality_guards import (
    clean_future_years,
    data_quality_flags,
    future_year_flag,
    implausible_ppm2_flag,
    implausible_yield_flag,
    is_suspect,
    whole_building_flag,
)


def test_polykatoikia_flags_whole_building():
    # #20025: "Πολυκατοικία 300 τ.μ.", €250k / 300 m², topped the ranking pre-fix.
    d = {
        "title": "Πολυκατοικία 300 τ.μ.",
        "area_m2": 300,
        "price": 250_000,
        "price_per_m2": 833.33,
        "gross_yield": 0.128,
    }
    assert whole_building_flag(d) is not None
    assert is_suspect(d)


def test_large_area_flags_whole_building_without_title():
    assert whole_building_flag({"title": "Διαμέρισμα", "area_m2": 500}) is not None


def test_big_and_cheap_flags_whole_building():
    # 260 m² at €900/m² — the "building priced as one unit" tell.
    d = {"title": "Διαμέρισμα", "area_m2": 260, "price": 234_000, "price_per_m2": 900}
    assert whole_building_flag(d) is not None


def test_future_year_flags():
    assert future_year_flag({"year_built": 2028}, current_year=2026) is not None
    assert future_year_flag({"renovated_year": 2030}, current_year=2026) is not None


def test_current_year_is_not_future():
    assert future_year_flag({"year_built": 2026}, current_year=2026) is None
    assert future_year_flag({"year_built": 2010}, current_year=2026) is None


def test_implausible_yield_flags():
    assert implausible_yield_flag({"gross_yield": 0.69}) is not None  # 69% — data error
    assert implausible_yield_flag({"net_yield": 0.001}) is not None  # ~0% — mis-parse
    assert implausible_yield_flag({"gross_yield": 0.05}) is None  # normal 5%


def test_implausible_ppm2_flags():
    assert implausible_ppm2_flag({"price_per_m2": 300}) is not None  # too low
    assert implausible_ppm2_flag({"price_per_m2": 20_000}) is not None  # too high
    # Falls back to price/area when price_per_m2 is absent.
    assert implausible_ppm2_flag({"price": 30_000, "area_m2": 200}) is not None  # €150/m²
    assert implausible_ppm2_flag({"price_per_m2": 3_000}) is None  # normal


def test_normal_flat_does_not_flag():
    # A normal 85 m² €250k flat: €2,941/m², 4.2% yield, 2005 build — must be clean.
    d = {
        "title": "Διαμέρισμα 85 τ.μ.",
        "area_m2": 85,
        "price": 250_000,
        "price_per_m2": 2941.18,
        "gross_yield": 0.042,
        "net_yield": 0.031,
        "year_built": 2005,
    }
    assert not is_suspect(d), data_quality_flags(d)


def test_clean_future_years_nulls_only_future():
    assert clean_future_years(2028, 2020, current_year=2026) == (None, 2020)
    assert clean_future_years(2010, None, current_year=2026) == (2010, None)
    assert clean_future_years(None, 2030, current_year=2026) == (None, None)


def test_data_quality_flags_aggregates_multiple():
    d = {"title": "Πολυκατοικία", "area_m2": 500, "gross_yield": 0.69, "year_built": 2028}
    flags = data_quality_flags(d)
    assert len(flags) >= 3  # whole-building + yield + future-year (+ maybe ppm2)
    assert is_suspect(d)
