"""The relative-value and relative-yield signals are market-position ranks, so check
they rank correctly, respect the peer minimum, and stay within the size/area peer group."""

from __future__ import annotations

from scout.relative_value import annotate_relative_value, relative_value, relative_yield


def _mk(area_val, ppm2, size=80, net_yield=None, gross_yield=None):
    return {
        "search_area": area_val,
        "price_per_m2": ppm2,
        "area_m2": size,
        "price": ppm2 * size,
        "net_yield": net_yield,
        "gross_yield": gross_yield,
    }


def test_cheapest_ranks_above_peers():
    pool = [_mk("Koukaki", ppm) for ppm in (2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000)]
    annotate_relative_value(pool)
    cheapest = pool[0]  # 2000 €/m² — cheaper than all 8 peers
    rv = relative_value(cheapest)
    assert rv is not None
    assert rv.percentile == 1.0  # below 100% of peers
    assert "below 100%" in rv.headline


def test_too_few_peers_returns_none():
    pool = [_mk("Rare", ppm) for ppm in (2000, 3000, 4000)]  # only 3 in the area
    annotate_relative_value(pool)
    assert relative_value(pool[0]) is None
    assert pool[0]["value_percentile"] is None


def test_peers_are_size_matched():
    # A 300 m² unit shares an area with many 80 m² flats but has no size peers → None.
    pool = [_mk("Kolonaki", 3000 + i * 100) for i in range(10)]
    big = _mk("Kolonaki", 2000, size=300)
    pool.append(big)
    annotate_relative_value(pool)
    assert relative_value(big) is None  # no comparable-size peers


def test_expensive_reports_above_share():
    pool = [_mk("Pagkrati", ppm) for ppm in (2000, 2200, 2400, 2600, 2800, 3000, 3200, 3400, 9000)]
    annotate_relative_value(pool)
    dear = pool[-1]  # 9000 €/m² — priciest
    rv = relative_value(dear)
    assert rv is not None and rv.percentile == 0.0
    assert "above 100%" in rv.headline


def test_highest_yield_ranks_above_peers():
    pool = [
        _mk("Kypseli", 2500, net_yield=y)
        for y in (0.03, 0.035, 0.04, 0.045, 0.05, 0.055, 0.06, 0.065, 0.09)
    ]
    annotate_relative_value(pool)
    best = pool[-1]  # 9% net yield — highest of all 8 peers
    ry = relative_yield(best)
    assert ry is not None
    assert ry.percentile == 1.0
    assert "Higher yield than 100%" in ry.headline


def test_same_yield_ranks_very_differently_by_area():
    # The exact case the fixed national BUY_YIELD threshold misses: 5.5% net yield is
    # the BEST in a low-yield prime area, but near the BOTTOM in a high-yield peripheral
    # one — a flat threshold can't tell these apart, an area-scoped percentile can.
    prime = [
        _mk("Kolonaki", 4000, net_yield=y)
        for y in (0.010, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.055)
    ]
    peripheral = [
        _mk("Nikaia", 1800, net_yield=y)
        for y in (0.055, 0.07, 0.075, 0.08, 0.085, 0.09, 0.095, 0.10, 0.11)
    ]
    pool = prime + peripheral
    annotate_relative_value(pool)
    prime_55 = prime[-1]  # 5.5% in Kolonaki
    peripheral_55 = peripheral[0]  # 5.5% in Nikaia
    assert relative_yield(prime_55).percentile == 1.0  # best yield locally available
    assert relative_yield(peripheral_55).percentile == 0.0  # worst yield locally available


def test_no_yield_data_returns_none():
    pool = [_mk("Vyronas", 2000 + i * 50) for i in range(10)]  # no net/gross yield set
    annotate_relative_value(pool)
    assert relative_yield(pool[0]) is None
    assert pool[0]["yield_percentile"] is None


def test_gross_yield_used_when_net_missing():
    pool = [
        _mk("Ilion", 2200, gross_yield=y)
        for y in (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.12)
    ]
    annotate_relative_value(pool)
    best = pool[-1]
    assert relative_yield(best) is not None
    assert relative_yield(best).percentile == 1.0


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("ok")
