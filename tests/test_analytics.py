from __future__ import annotations

from datetime import datetime

from scout.analytics import market_price_index, neighborhood_stats


def _listing(**overrides):
    base = {
        "id": 1,
        "price": 100_000,
        "area_m2": 50.0,
        "neighborhood": "Kentro",
        "price_per_m2": 2000.0,
        "gross_yield": 0.05,
        "is_opportunity": False,
        "is_currently_rented": False,
        "excluded": False,
        "status": "active",
    }
    base.update(overrides)
    return base


def test_neighborhood_stats_two_neighborhoods_medians_and_counts():
    listings = [
        _listing(id=1, neighborhood="Kentro", price=100_000, price_per_m2=2000.0, gross_yield=0.04),
        _listing(id=2, neighborhood="Kentro", price=120_000, price_per_m2=2400.0, gross_yield=0.06),
        _listing(
            id=3, neighborhood="Perissos", price=80_000, price_per_m2=1600.0, gross_yield=0.05
        ),
    ]

    stats = neighborhood_stats(listings)

    assert [s["neighborhood"] for s in stats] == ["Kentro", "Perissos"]

    kentro = stats[0]
    assert kentro["count"] == 2
    assert kentro["median_price"] == 110_000
    assert kentro["median_ppm2"] == 2200.0
    assert kentro["median_yield_pct"] == 5.0

    perissos = stats[1]
    assert perissos["count"] == 1
    assert perissos["median_price"] == 80_000
    assert perissos["median_ppm2"] == 1600.0
    assert perissos["median_yield_pct"] == 5.0


def test_neighborhood_stats_sorted_by_count_desc_then_name_asc():
    listings = [
        _listing(id=1, neighborhood="Z-Area"),
        _listing(id=2, neighborhood="A-Area"),
        _listing(id=3, neighborhood="A-Area"),
    ]

    stats = neighborhood_stats(listings)

    assert [s["neighborhood"] for s in stats] == ["A-Area", "Z-Area"]
    assert stats[0]["count"] == 2
    assert stats[1]["count"] == 1


def test_neighborhood_stats_skips_falsy_neighborhood():
    listings = [
        _listing(id=1, neighborhood=None),
        _listing(id=2, neighborhood=""),
        _listing(id=3, neighborhood="Real"),
    ]

    stats = neighborhood_stats(listings)

    assert len(stats) == 1
    assert stats[0]["neighborhood"] == "Real"
    assert stats[0]["count"] == 1


def test_neighborhood_stats_ppm2_fallback_to_price_over_area():
    listings = [
        _listing(id=1, neighborhood="Kentro", price=100_000, area_m2=50.0, price_per_m2=None),
        _listing(id=2, neighborhood="Kentro", price=120_000, area_m2=40.0, price_per_m2=3000.0),
    ]

    stats = neighborhood_stats(listings)

    # fallback listing -> 100000/50 = 2000; explicit listing -> 3000
    assert stats[0]["median_ppm2"] == 2500.0


def test_neighborhood_stats_ppm2_fallback_skips_when_area_missing_or_zero():
    listings = [
        _listing(id=1, neighborhood="Kentro", price=100_000, area_m2=0, price_per_m2=None),
        _listing(id=2, neighborhood="Kentro", price=100_000, area_m2=None, price_per_m2=None),
        _listing(id=3, neighborhood="Kentro", price=100_000, area_m2=50.0, price_per_m2=2500.0),
    ]

    stats = neighborhood_stats(listings)

    assert stats[0]["median_ppm2"] == 2500.0


def test_neighborhood_stats_opportunities_and_rented_counts():
    listings = [
        _listing(id=1, neighborhood="Kentro", is_opportunity=True, is_currently_rented=True),
        _listing(id=2, neighborhood="Kentro", is_opportunity=True, is_currently_rented=False),
        _listing(id=3, neighborhood="Kentro", is_opportunity=False, is_currently_rented=False),
    ]

    stats = neighborhood_stats(listings)

    assert stats[0]["opportunities"] == 2
    assert stats[0]["rented"] == 1


def test_neighborhood_stats_empty_input_returns_empty_list():
    assert neighborhood_stats([]) == []


def test_neighborhood_stats_handles_none_price_and_yield_without_raising():
    listings = [
        _listing(
            id=1,
            neighborhood="Kentro",
            price=None,
            gross_yield=None,
            price_per_m2=None,
            area_m2=None,
        ),
        _listing(id=2, neighborhood="Kentro", price=100_000, gross_yield=0.05, price_per_m2=2000.0),
    ]

    stats = neighborhood_stats(listings)

    assert stats[0]["count"] == 2
    assert stats[0]["median_price"] == 100_000
    assert stats[0]["median_yield_pct"] == 5.0
    assert stats[0]["median_ppm2"] == 2000.0


def test_market_price_index_across_months_known_median():
    history = [
        {"observed_at": datetime(2026, 1, 5), "price": 100_000},
        {"observed_at": datetime(2026, 1, 20), "price": 120_000},
        {"observed_at": datetime(2026, 2, 3), "price": 200_000},
        {"observed_at": datetime(2026, 3, 1), "price": 90_000},
        {"observed_at": datetime(2026, 3, 15), "price": 110_000},
        {"observed_at": datetime(2026, 3, 28), "price": 130_000},
    ]

    index = market_price_index(history)

    assert [row["month"] for row in index] == ["2026-01", "2026-02", "2026-03"]
    assert index[0]["median_price"] == 110_000
    assert index[0]["samples"] == 2
    assert index[1]["median_price"] == 200_000
    assert index[1]["samples"] == 1
    assert index[2]["median_price"] == 110_000
    assert index[2]["samples"] == 3


def test_market_price_index_empty_input_returns_empty_list():
    assert market_price_index([]) == []


def test_market_price_index_skips_bad_entries_without_raising():
    history = [
        {"observed_at": datetime(2026, 1, 5), "price": 100_000},
        {"observed_at": datetime(2026, 1, 10), "price": None},
        {"observed_at": datetime(2026, 1, 12), "price": -50},
        {"observed_at": datetime(2026, 1, 14), "price": 0},
        {"observed_at": None, "price": 150_000},
        {"price": 130_000},
        "not-a-dict",
        {"observed_at": datetime(2026, 1, 15), "price": 200_000},
    ]

    index = market_price_index(history)

    assert index == [{"month": "2026-01", "median_price": 150_000, "samples": 2}]
