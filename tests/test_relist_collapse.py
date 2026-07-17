"""Same-flat relistings collapse to one card (the XE re-post duplicate bug)."""

from scout.ui.queries import _collapse_relistings


def _row(**kw):
    base = {
        "source": "xe",
        "neighborhood": "Παπάγου",
        "price": 300000,
        "area_m2": 55.0,
        "floor": 1.0,
        "bedrooms": None,
        "days_on_market": None,
        "listed_date": None,
        "data_missing": [],
        "data_confidence": 50,
    }
    base.update(kw)
    return base


def test_two_identical_relistings_collapse_to_one():
    rows = [
        _row(source_id="a", days_on_market=227, data_missing=["energy"]),
        _row(source_id="b", days_on_market=379, data_missing=["energy", "year"]),
    ]
    out = _collapse_relistings(rows)
    assert len(out) == 1
    rep = out[0]
    # Richest-data record wins (fewest missing) …
    assert rep["source_id"] == "a"
    # … but days-on-market anchors to the OLDEST posting (the honest distress signal).
    assert rep["days_on_market"] == 379
    assert rep["relist_count"] == 2


def test_distinct_flats_are_not_merged():
    rows = [
        _row(source_id="a", price=300000),
        _row(source_id="b", price=310000),  # different price → different flat
    ]
    out = _collapse_relistings(rows)
    assert len(out) == 2


def test_sparse_rows_never_collapse():
    # No price/area → not safe to treat as the same flat; pass through untouched.
    rows = [
        _row(source_id="a", price=None, area_m2=None),
        _row(source_id="b", price=None, area_m2=None),
    ]
    out = _collapse_relistings(rows)
    assert len(out) == 2
    assert all("relist_count" not in r for r in out)
