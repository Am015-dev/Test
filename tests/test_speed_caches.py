"""C13: the per-data-version sharing (market_intel.share, ui.derived) returns the same results
as building from scratch, builds once, and never serves a stale list."""

from __future__ import annotations

from datetime import date

from scout import market_intel
from scout.ui import derived


def _flat(i: int, ppm: float, **kw) -> dict:
    d = {
        "id": i,
        "title": "Διαμέρισμα 70τ.μ.",
        "neighborhood": "Χολαργός (Κέντρο)",
        "search_area": "Cholargos",
        "price": int(ppm * 70),
        "price_per_m2": ppm,
        "area_m2": 70,
        "floor": 2,
        "year_built": 2005,
        "excluded": False,
        "is_fresh": True,
    }
    return d | kw


def _listings() -> list[dict]:
    return [_flat(i, 3000 + 50 * i) for i in range(12)] + [
        _flat(100, 3100, title="Μονοκατοικία 70τ.μ."),
        _flat(101, 3100, price=217_000),  # a twin of id 2 (same area, m², floor, year)
    ]


def test_kind_unchanged_by_the_title_cache():
    for title, want in [
        ("Μονοκατοικία 120τ.μ.", "house"),
        ("ΜΕΖΟΝΕΤΑ 3 επιπέδων", "house"),
        ("Βίλα", "house"),
        ("Διαμέρισμα 70τ.μ.", "flat"),
        ("", "flat"),
    ]:
        assert market_intel.kind({"title": title}) == want
    assert market_intel.kind({}) == "flat"


def test_shared_intel_equals_a_fresh_build():
    listings = _listings()
    shared = market_intel.share(listings)
    assert market_intel.build(listings) is shared  # same object for the same list
    fresh = market_intel._build(listings, None)
    for d in listings:
        assert shared.comps(d) == fresh.comps(d)
        assert shared.twins(d) == fresh.twins(d)


def test_other_lists_and_years_are_built_fresh():
    listings = _listings()
    shared = market_intel.share(listings)
    copy = list(listings)
    assert market_intel.build(copy) is not shared  # another list: never the shared index
    assert market_intel.build(listings, year=2020) is not shared
    assert market_intel.build(listings, year=2020).year == 2020


def test_new_data_version_replaces_the_old_one():
    old, new = _listings(), _listings()
    market_intel.share(old)
    market_intel.share(new)
    assert id(old) not in market_intel._SHARED  # the old list is not kept alive
    assert market_intel._SHARED[id(new)][0] is new


def test_memo_computes_once_per_list():
    listings = _listings()
    calls = []
    for _ in range(3):
        got = derived.memo(listings, "x", lambda: calls.append(1) or len(calls))
    assert got == 1 and calls == [1]
    other = _listings()
    assert derived.memo(other, "x", lambda: "other") == "other"
    assert id(listings) not in derived._STORE  # one data version at a time


def test_guide_context_follows_the_rents():
    listings = _listings()
    year = date.today().year
    facts1, memo1 = derived.guide_context(listings, [], year)
    facts2, memo2 = derived.guide_context(listings, [], year)
    assert facts1 is facts2 and memo1 is memo2
    rents = [{"neighborhood": "Χολαργός", "price_per_m2": 12.0}]
    facts3, memo3 = derived.guide_context(listings, rents, year)
    assert memo3 is not memo1  # different rents: the per-listing work starts over
