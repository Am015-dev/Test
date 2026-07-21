"""The relative-value signal is a market-position rank, so check it ranks correctly,
respects the peer minimum, and stays within the size/area peer group."""

from __future__ import annotations

from scout.relative_value import annotate_relative_value, relative_value


def _mk(area_val, ppm2, size=80):
    return {"search_area": area_val, "price_per_m2": ppm2, "area_m2": size, "price": ppm2 * size}


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


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("ok")
