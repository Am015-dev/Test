"""The 🗺 Χάρτης page: every filter works and actually narrows the map."""

from __future__ import annotations

import inspect
import re

import pytest

pytest.importorskip("streamlit.testing.v1")

from scout.ui import components, maplist  # noqa: E402

from .test_ui_gauntlet import env, fresh, ok  # noqa: E402,F401

MAP = "Χάρτης"


def _area_count(at) -> int:
    line = next(m.value for m in at.markdown if re.match(r"\*\*[^*]+\*\* · [\d.]+ αγγελ", m.value))
    return int(re.search(r"· ([\d.]+) αγγελ", line).group(1).replace(".", ""))


def test_map_is_one_circle_per_area_and_the_picker_shows_its_flats(env):  # noqa: F811
    at = fresh(MAP)
    ok(at, "open")
    # two filters (price, year) and one area picker; no checkboxes, no area multiselect
    assert len(at.slider) == 2 and not at.multiselect and not at.checkbox
    assert any(m.value.startswith("#### Οι καλύτερες σε όλες τις περιοχές") for m in at.markdown)
    pick = at.selectbox(key=maplist.AREA)
    assert pick.value is None and any(o.startswith("Χολαργός · ") for o in pick.options)
    pick.set_value("Χολαργός").run()
    ok(at, "area")
    total = _area_count(at)
    cards = [m.value for m in at.markdown if 'class="hg-card"' in m.value]
    assert 0 < len(cards) <= min(total, maplist.PAGE)
    lo = at.slider(key="map_price").min
    at.slider(key="map_price").set_value(lo + 200).run()  # 250 χιλ.
    ok(at, "price")
    assert _area_count(at) < total


def test_map_never_shows_unfinished_flats(env):  # noqa: F811
    at = fresh(MAP)
    assert not any("Υπό κατασκευή" in m.value for m in at.markdown if "hg-card" in m.value)


def test_area_groups_use_the_search_area_and_count_every_flat():
    rows = [
        {"id": 1, "search_area": "Cholargos", "lat": 38.0, "lng": 23.79, "price": 200_000,
         "est_monthly_rent": 800, "price_per_m2": 3000},
        {"id": 2, "search_area": "Cholargos", "lat": 38.002, "lng": 23.8, "price": 300_000,
         "est_monthly_rent": 1000, "price_per_m2": 3200, "neighborhood": "Νέο Ψυχικό"},
        {"id": 3, "search_area": "Galatsi", "lat": 38.02, "lng": 23.75, "price": 150_000},
        {"id": 4, "search_area": "Galatsi", "price": 150_000},  # no position: not on the map
    ]  # fmt: skip
    groups = maplist.area_groups(rows)
    assert [(g["name"], g["n"]) for g in groups] == [("Χολαργός", 2), ("Γαλάτσι", 1)]
    hol = groups[0]
    assert round(hol["gy"], 3) == 0.044 and hol["ppm"] == 3100
    assert maplist.area_line(hol) == "**Χολαργός** · 2 αγγελίες · απόδοση ~4,4 % · ~3.100 €/τ.μ."


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
