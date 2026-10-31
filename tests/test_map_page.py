"""The 🗺 Χάρτης page: every filter works and actually narrows the map."""

from __future__ import annotations

import inspect
import re

import pytest

pytest.importorskip("streamlit.testing.v1")

from scout.ui import components  # noqa: E402

from .test_ui_gauntlet import env, fresh, ok  # noqa: E402,F401

MAP = "Χάρτης"


def _count(at) -> int:
    for m in at.markdown:
        hit = re.search(r"\*\*([\d.]+) αγγελ(?:ία|ίες) στον χάρτη\*\*", m.value)
        if hit:
            return int(hit.group(1).replace(".", ""))
    raise AssertionError("map count not shown")


def test_map_has_three_filters_and_they_narrow_the_points(env):  # noqa: F811
    at = fresh(MAP)
    ok(at, "open")
    total = _count(at)
    assert total > 0
    # exactly three filters: area, price max, min year (no checkboxes, no score/age sliders)
    assert len(at.multiselect) + len(at.slider) == 3
    assert not at.checkbox
    # areas are grouped by municipality
    areas = at.multiselect(key="map_areas")
    assert any(o == "Χολαργός" for o in areas.options), areas.options
    areas.set_value(["Χολαργός"]).run()
    ok(at, "area")
    by_area = _count(at)
    assert 0 < by_area < total
    at.multiselect(key="map_areas").set_value([]).run()
    lo = at.slider(key="map_price").min
    at.slider(key="map_price").set_value(lo).run()
    ok(at, "price")
    assert _count(at) < total
    at.slider(key="map_price").set_value(at.slider(key="map_price").max).run()
    assert _count(at) == total
    year = at.slider(key="map_year")
    year.set_value(year.max).run()
    ok(at, "year")
    assert _count(at) < total


def test_map_hides_unfinished_flats_and_says_so(env):  # noqa: F811
    at = fresh(MAP)
    ok(at, "open")
    notes = " ".join(c.value for c in at.caption)
    assert re.search(r"[\d.]+ υπό κατασκευή δεν εμφανίζονται", notes), notes


def test_map_cards_replace_the_wide_table(env):  # noqa: F811
    """Listings under the map are the search page's cards, never a table to scroll to."""
    at = fresh(MAP)
    assert len(at.dataframe) == 0
    assert sum('class="hg-card"' in m.value for m in at.markdown) >= 5


def test_map_popup_shows_card_facts_in_greek():
    """The tooltip template names price, m², €/τ.μ., floor, year and status — no English."""
    src = inspect.getsource(components.results_map)
    for field in ("{price}", "{m2}", "{ppm2}", "{floor}", "{year}", "{status}"):
        assert field in src
    assert not re.search(r"\b(Score|Price|Floor|Year|Status)\b", src.split("tooltip =")[1][:400])
    unfinished = components._status_gr({"is_unfinished": True, "page_checked": True})
    assert unfinished == "Υπό κατασκευή"
    assert components._status_gr({"page_checked": True}) == "Ελέγχθηκε η περιγραφή"
    assert components._status_gr({"page_checked": False}) == "Δεν έχει ελεγχθεί ακόμα"


def test_approx_points_are_jittered_deterministically():
    base = {"lat": 38.0, "lng": 23.8, "source": "xe"}
    a = components.map_position({**base, "source_id": "1", "location_precision": "approx"})
    b = components.map_position({**base, "source_id": "2", "location_precision": "approx"})
    again = components.map_position({**base, "source_id": "1", "location_precision": "approx"})
    exact = components.map_position({**base, "source_id": "1", "location_precision": "exact"})
    assert a == again and a != b
    assert exact == (38.0, 23.8)
    assert abs(a[0] - 38.0) < 0.004 and abs(a[1] - 23.8) < 0.006


def test_score_color_runs_red_to_green():
    red, green = components.score_color(0), components.score_color(70)
    assert red[0] > red[1] and green[1] > green[0]
    assert components.score_color(None) == [150, 150, 160]


def test_map_colours_by_gross_yield_in_three_bands():
    low, mid, high = (components.yield_color(g) for g in (0.03, 0.04, 0.06))
    assert len({tuple(low), tuple(mid), tuple(high)}) == 3
    assert components.yield_color(0.035) == mid and components.yield_color(0.05) == mid
    assert components.yield_color(None) == [150, 150, 160]  # no rent figure: grey
    d = {"price": 200_000, "est_monthly_rent": 700}
    assert components.gross_yield_of(d) == pytest.approx(0.042)
    assert components.gross_yield_of({"price": 200_000}) is None


def test_map_page_says_how_few_positions_are_exact(env):  # noqa: F811
    at = fresh(MAP)
    first = next(c.value for c in at.caption if "θέση" in c.value and "κέντρο" in c.value)
    assert re.match(
        r"(Μόνο [\d.]+ αγγελίες έχουν ακριβή θέση· οι υπόλοιπες στο κέντρο|Καμία)", first
    )
    assert not any("Σκορ 0–100" in c.value for c in at.caption)
