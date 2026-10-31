"""C7 — never a thin list: near matches after the strict ones, one loosened answer each, and
the score on every pick."""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from scout import market_intel, nl_search, picks, picks_rent

YEAR = 2026
RENTS = [
    {"neighborhood": "Νέα Ιωνία (Περισσός)", "rent_per_m2": 11.0, "samples": 20},
    {"neighborhood": "Γαλάτσι (Λαμπρινή)", "rent_per_m2": 12.0, "samples": 20},
]
BUDGET = 300_000


def flat(i, price, hood="Νέα Ιωνία (Περισσός)", year=2024, m2=80, **kw):
    return {
        "id": i,
        "url": f"https://x/{i}",
        "title": f"Διαμέρισμα {m2} τ.μ.",
        "price": price,
        "area_m2": m2,
        "price_per_m2": price / m2,
        "floor": 2.0,
        "year_built": year,
        "neighborhood": hood,
        "is_fresh": True,
        "bedrooms": 2,
        **kw,
    }


ROWS = [
    flat(1, 300_000),  # strict
    flat(2, 290_000, year=2023),  # strict
    flat(3, 350_000, year=2022),  # price +17 % → step 20 %
    flat(4, 385_000, year=2021),  # price +29 % → step 30 %
    flat(5, 330_000, year=2010),  # age 2010 → step «20 ετών»
    flat(6, 310_000, year=1980),  # age any
    flat(7, 300_000, hood="Γαλάτσι (Λαμπρινή)", year=2020),  # no station
    flat(8, 420_000, year=1980),  # price AND age: never shown
    flat(9, 450_000),  # +50 %: past every price step
    flat(10, 290_000, floor=0.0),  # ground floor: not an answer, never loosened
]


def run(rows=ROWS, **kw):
    intel = market_intel.build(rows, YEAR)
    args = dict(year=YEAR, top=10**6, near=True) | kw
    return picks.find(rows, intel, RENTS, BUDGET, **args)


def test_strict_first_then_near_ranked_with_labels():
    got = run()
    ids = [p.listing["id"] for p in got]
    assert set(ids[:2]) == {1, 2} and all(p.relaxed == "" for p in got[:2])
    labels = {p.listing["id"]: p.relaxed for p in got[2:]}
    assert labels == {
        3: "ποσό +17 %",
        4: "ποσό +29 %",
        5: "κτίριο 2010",
        6: "κτίριο 1980",
        7: "χωρίς όρο σταθμού",
    }
    keys = [p.sort_key() for p in got[2:]]
    assert keys == sorted(keys, reverse=True)  # one ranking over all near matches


def test_steps_order_any_age_last():
    assert picks.near_steps(10, True, ["Γαλάτσι"], 2) == [
        ("price", 1),
        ("price", 2),
        ("age", 1),  # 10 → 20
        ("rail", 1),
        ("areas", 1),
        ("bedrooms", 1),
        ("age", 2),  # any building age
    ]
    assert picks.near_steps(None, False, None, None) == [("price", 1), ("price", 2)]


def test_hard_rules_and_the_widest_band_stay():
    ids = {p.listing["id"] for p in run()}
    assert not ids & {8, 9, 10}  # +40 %, +50 %, ground floor: never shown


def test_third_tier_names_every_answer_it_fails_and_nothing_repeats():
    rows = [*ROWS, flat(11, 360_000, year=1985, hood="Γαλάτσι (Λαμπρινή)")]  # +20 %, age, rail
    got = run(rows)
    tiers = [p.tier for p in got]
    assert tiers == sorted(tiers)  # strict → near → ευρύτερα
    wide = [p for p in got if p.tier == 2]
    assert [(p.listing["id"], p.relaxed) for p in wide] == [
        (11, "ποσό +20 %, κτίριο 1985, χωρίς όρο σταθμού")
    ]
    assert all(p.tier == 1 and "," not in p.relaxed for p in got if p.tier == 1)
    assert len({p.listing["id"] for p in got}) == len(got)


def test_strict_find_is_unchanged_by_default():
    intel = market_intel.build(ROWS, YEAR)
    got = picks.find(ROWS, intel, RENTS, BUDGET, year=YEAR, top=99)
    assert {p.listing["id"] for p in got} == {1, 2}
    assert all(p.relaxed == "" for p in got)


def test_areas_and_bedrooms_are_loosened_last():
    rows = [
        flat(1, 300_000, bedrooms=2),
        flat(2, 300_000, hood="Γαλάτσι (Λαμπρινή)", bedrooms=2, year=2021),
        flat(3, 305_000, bedrooms=3, year=2022),
    ]
    got = run(rows, near_rail=False, areas=["Νέα Ιωνία"], bedrooms=2)
    assert [(p.listing["id"], p.relaxed) for p in got] == [
        (1, ""),
        (2, "Γαλάτσι"),
        (3, "3 υπν."),
    ]


def test_no_near_matches_after_a_long_strict_list():
    rows = [flat(i, 280_000 + i * 500, year=1990 + i) for i in range(30)]  # distinct blocks
    rows += [flat(100, 350_000)]  # +17 %: would be a near match
    got = run(rows, max_age=None)
    assert len(got) == 30 and all(not p.relaxed for p in got)


def test_each_step_keeps_at_most_three_pages_and_the_rest_go_wider():
    # 36 off-station flats in distinct blocks: the station step keeps NEAR_MIN, the other 6
    # go to «ευρύτερα» with their own label — every flat in the band appears exactly once.
    rows = [flat(i, 280_000 + i * 500, hood="Γαλάτσι (Λαμπρινή)", year=1990 + i) for i in range(36)]
    got = run(rows, max_age=None)
    assert [p.tier for p in got] == [1] * picks.NEAR_MIN + [2] * 6
    assert all(p.relaxed == "χωρίς όρο σταθμού" for p in got)
    assert {p.listing["id"] for p in got} == set(range(36))


def test_every_pick_carries_the_buyer_score_of_advise():
    intel = market_intel.build(ROWS, YEAR)
    for p in run():
        cmp = intel.comps(p.listing)
        want = nl_search.advise(p.listing, cmp["pct"] if cmp else None)["score"]
        assert p.buyer_score == want == picks.buyer_score(p.listing, intel)
        assert 0 <= p.buyer_score <= 100


def test_relaxations_keep_their_meaning():
    """Each relaxation still counts what the STRICT find adds with that one change."""
    intel = market_intel.build(ROWS, YEAR)
    got = picks.relaxations(ROWS, intel, RENTS, BUDGET, year=YEAR)
    assert got
    base = {p.listing["id"] for p in picks.find(ROWS, intel, RENTS, BUDGET, year=YEAR, top=99)}
    for r in got:
        args = {"budget": BUDGET} | r.changes
        more = picks.find(ROWS, intel, RENTS, args.pop("budget"), year=YEAR, top=99, **args)
        assert r.added == len({p.listing["id"] for p in more} - base)


# ---- rentals -------------------------------------------------------------------------------


def rental(i, price, m2=70, hood="Χαλάνδρι (Κέντρο)", **kw):
    return {
        "id": 10_000 + i,
        "listing_type": "rent",
        "url": f"https://x/r/{i}",
        "price": price,
        "area_m2": m2,
        "rent_per_m2": price / m2,
        "floor": 2.0,
        "year_built": 2005,
        "bedrooms": 2,
        "neighborhood": hood,
        "is_fresh": True,
        "days_on_market": 20,
        **kw,
    }


RENTALS = [rental(i, 700 + i * 10) for i in range(6)] + [
    rental(20, 950),  # +19 % over 800 → step 20 %
    rental(21, 1030),  # +29 % → step 30 %
    rental(22, 780, bedrooms=3),  # bedrooms
    rental(23, 1100, bedrooms=3),  # +38 % and bedrooms: past the widest band, never
    rental(24, 1000, bedrooms=3),  # +25 % and bedrooms: «ευρύτερα»
]


def test_rent_near_matches_and_labels():
    got = picks_rent.find(RENTALS, 800, bedrooms=2, top=10**6, near=True)
    strict = [p for p in got if not p.relaxed]
    assert {p.listing["id"] for p in strict} == {10_000 + i for i in range(6)}
    near = got[len(strict) :]
    assert {p.listing["id"]: p.relaxed for p in near} == {
        10_020: "ποσό +19 %",
        10_021: "ποσό +29 %",
        10_022: "3 υπν.",
        10_024: "ποσό +25 %, 3 υπν.",
    }
    one = [p for p in near if p.tier == 1]
    assert [p.score for p in one] == sorted((p.score for p in one), reverse=True)
    assert len(picks_rent.find(RENTALS, 800, bedrooms=2, top=10**6)) == 6


def test_rent_long_strict_list_has_no_near_matches():
    rows = [rental(i, 700 + i, hood=f"Χαλάνδρι ({i})") for i in range(30)] + [rental(99, 950)]
    got = picks_rent.find(rows, 800, top=10**6, near=True)
    assert len(got) == 30 and not any(p.relaxed for p in got)


def test_rent_value_score_and_basis():
    cheap, dear = rental(1, 600), rental(2, 900)
    s_cheap, basis = picks_rent.value_score(-0.20, {"days_on_market": 5})
    assert s_cheap == 100 and basis == (
        "70 από 70 για την τιμή σε σχέση με τα παρόμοια και 30 από 30 για το πόσο καινούργια "
        "είναι η αγγελία"
    )
    assert picks_rent.value_score(0.20, {"days_on_market": 60})[0] == 0
    assert picks_rent.value_score(None, {})[0] == 50
    assert picks_rent.value_score(-0.5, {"days_on_market": 5})[0] == 30  # too cheap: no bonus
    got = {p.listing["id"]: p.score for p in picks_rent.find([*RENTALS, cheap, dear], 1000, top=99)}
    assert got[cheap["id"]] > got[dear["id"]]


# ---- the owner's answers on the published DB -----------------------------------------------

DB = Path(__file__).resolve().parents[1] / "data" / "listings.db"


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    if not DB.exists():
        pytest.skip("published DB not downloaded (data/listings.db)")
    # Load in a child process: the DB engine is process-global and other tests set their own.
    out = tmp_path_factory.mktemp("published") / "rows.pkl"
    code = (
        "import pickle, sys; from scout.db import init_db; init_db(); "
        "from scout.ui import queries; "
        "pickle.dump((queries.load_listings(), queries.load_rent_comp_rows()), "
        "open(sys.argv[1], 'wb'))"
    )
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{DB}"}
    subprocess.run([sys.executable, "-c", code, str(out)], env=env, check=True)
    return pickle.loads(out.read_bytes())


def test_owner_answers_give_at_least_three_pages(published):
    listings, rents = published
    intel = market_intel.build(listings)
    got = picks.find(
        listings, intel, rents, 160_000, max_age=10, near_rail=True, top=10**6, near=True
    )
    near = [p for p in got if p.relaxed]
    assert len(got) > 57  # pages past strict + near: the list does not run out
    assert len({id(p.listing) for p in got}) == len(got)  # nothing repeats across tiers
    assert [p.tier for p in got] == sorted(p.tier for p in got)
    assert all(p.listing["price"] <= 160_000 * 1.30 for p in got)
    assert near and all(p.relaxed for p in got[len(got) - len(near) :])
    # The newer flats one station rule away come before the old blocks of «any age».
    first = near[0].relaxed
    assert not first.startswith("κτίριο 19")
    # (a read page still beats an unread one, as for strict matches)
    station = [i for i, p in enumerate(near) if p.relaxed == "χωρίς όρο σταθμού" and p.checked]
    old = [i for i, p in enumerate(near) if p.relaxed.startswith("κτίριο 19")]
    assert station and old and max(station) < min(old)


def test_owner_like_long_list_has_no_near_matches(published):
    listings, rents = published
    intel = market_intel.build(listings)
    got = picks.find(
        listings, intel, rents, 250_000, max_age=None, near_rail=False, top=10**6, near=True
    )
    assert len(got) >= picks.NEAR_MIN and not any(p.relaxed for p in got)


def test_order_is_trust_ladder_then_the_score_in_every_tier(published):
    """One truth: within a tier and a trust step, a lower «Βαθμολογία» never ranks above a
    higher one; the goal's points only break ties."""
    listings, rents = published
    intel = market_intel.build(listings)
    for goal in picks.GOALS:
        got = picks.find(
            listings, intel, rents, 160_000, max_age=10, near_rail=True, goal=goal,
            top=10**6, near=True,
        )  # fmt: skip
        for tier in (0, 2):  # near (1) is per-step first, then ranked the same way
            rows = [p for p in got if p.tier == tier]
            keys = [p.sort_key()[:4] for p in rows]
            assert keys == sorted(keys, reverse=True)


def test_rent_order_is_the_score():
    got = picks_rent.find(RENTALS, 800, bedrooms=2, top=10**6)
    assert [p.score for p in got] == sorted((p.score for p in got), reverse=True)


def test_rent_overflow_past_a_step_cap_goes_wider():
    rows = [rental(i, 700 + i, hood=f"Χαλάνδρι ({i})", bedrooms=3) for i in range(35)]
    got = picks_rent.find(rows, 800, bedrooms=2, top=10**6, near=True)
    assert [p.tier for p in got] == [1] * picks.NEAR_MIN + [2] * 5
    assert len({p.listing["id"] for p in got}) == 35
