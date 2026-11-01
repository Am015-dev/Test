# ruff: noqa: F811  (the imported `env` fixture is re-declared as a test argument)
"""C16: one number per flat. The rent estimate, the gross yield and the score of a listing read
the same on the guide card, the search card and the listing page — all three take them from
the row's own fields (``est_monthly_rent`` / ``listed_rent``, ``score``), never from a second
rent model. Driven through the real pages on the seeded gauntlet DB."""

from __future__ import annotations

import re

import pytest

from scout import market_intel, picks

from .test_guide import walk
from .test_picks import RENTS, YEAR, flat
from .test_ui_gauntlet import FIND, SEARCH, env, fresh, goto, ok  # noqa: F401

pytest.importorskip("streamlit.testing.v1")

RENT = re.compile(r"Ενοίκιο \((?:εκτίμηση|από την αγγελία)\) ~?([\d.]+) €/μήνα")
YIELD = re.compile(r"Μικτή απόδοση ([\d,]+ %)")
SCORE = re.compile(r"Βαθμολογία (\d+)")


def _numbers(at) -> dict[int, tuple[str, str, str]]:
    """listing id → (rent, gross yield, score) as printed on every card of the page."""
    out = {}
    for m in at.markdown:
        if 'class="hg-card' not in m.value:
            continue
        text = re.sub(r"<[^>]+>", " ", m.value)
        lid = int(re.search(r'data-lid="(\d+)"', m.value).group(1))
        rent, gy, sc = RENT.search(text), YIELD.search(text), SCORE.search(text)
        assert rent and gy and sc, text[:300]
        out[lid] = (rent.group(1), gy.group(1), sc.group(1))
    return out


def test_guide_search_and_listing_page_print_the_same_rent_yield_and_score(env):
    from scout.nl_search import SearchFilters

    at = walk(fresh(FIND))
    on_guide = _numbers(at)
    assert len(on_guide) >= 3

    # The search page, asked (the way _set_query asks) for flats up to each of the guide's
    # first three prices with every other filter wide open and no paging, prints the same
    # flats through buyer.card_html from the row's own fields.
    from scout.ui import queries

    price = {d["id"]: d["price"] for d in queries.load_listings(include_excluded=True)}
    at = fresh(SEARCH)
    for ver, lid in enumerate(list(on_guide)[:3], start=1):
        at.session_state["nl_filters"] = SearchFilters(
            price_max=price[lid],
            floor_min=0,
            year_min=1900,
            include_unfinished=True,
            include_undeclared=True,
        )
        at.session_state["nl_text"] = f"έως {price[lid]} €"
        at.session_state["f_ver"] = ver
        at.session_state["limit"] = 10_000
        at.run()
        ok(at, "search")
        on_search = _numbers(at)
        assert lid in on_search, (lid, sorted(on_search))
        assert on_guide[lid] == on_search[lid], (lid, on_guide[lid], on_search[lid])

    # The listing page of the guide's first card.
    first = next(iter(on_guide))
    at.session_state["page"] = "Αγγελία"
    at.session_state["detail_id"] = first
    at.run()
    ok(at, "listing page")
    on_page = _numbers(at)
    assert on_page == {first: on_guide[first]}, (on_page, on_guide[first])


def test_the_pick_reads_the_stored_rent_and_names_its_basis():
    """No second rent model: a pick's rent is the row's own estimate (or its listed rent), the
    yield follows from it, and the basis line says whether the neighbourhood's rentals or the
    area's stand behind it."""
    rows = [  # distinct sizes and prices, so none of them counts as another's twin
        flat(1, 300_000, m2=100),  # stored estimate 11 €/m² × 100
        flat(2, 280_000, m2=90, est_monthly_rent=1_500),  # a different stored estimate
    ]
    intel = market_intel.build(rows, YEAR)
    by_id = {p.listing["id"]: p for p in picks.find(rows, intel, RENTS, 300_000, year=YEAR,
                                                     near_rail=False, top=10)}  # fmt: skip
    assert by_id[1].rent == 1_100 and by_id[1].gross == pytest.approx(12 * 1_100 / 300_000)
    assert by_id[1].lines[0] == (
        "Ενοίκιο (εκτίμηση) ~1.100 €/μήνα: τα διπλανά (20 αγγελίες) ζητούν 11,0 €/τ.μ. × "
        "100 τ.μ."
    )
    assert by_id[2].rent == 1_500 and "16,7 €/τ.μ. × 90 τ.μ." in by_id[2].lines[0]
    rented = picks._build(flat(3, 260_000, m2=85, listed_rent=1_300), intel,
                          picks.rent_index(RENTS), YEAR)  # fmt: skip
    assert rented.rent == 1_300  # the ad states its rent: that figure, as on the card
    assert rented.lines[0] == "Ενοίκιο (από την αγγελία) 1.300 €/μήνα"
    area = picks._build(
        flat(4, 240_000, m2=75, hood="Παπάγου (Κέντρο)"), intel, picks.rent_index(RENTS), YEAR
    )  # fmt: skip  (no rent row for the hood)
    assert "στην περιοχή (Παπάγου) ζητούν" in area.lines[0]
    # the score is nl_search.advise on the same dict, whichever page asks
    for p in by_id.values():
        assert p.buyer_score == picks.buyer_score(p.listing, intel)
    # a row without a stored rent has no yield to show and is not a pick
    assert picks.find([flat(5, 300_000, est_monthly_rent=None)], intel, RENTS, 300_000,
                      year=YEAR, near_rail=False) == []  # fmt: skip
