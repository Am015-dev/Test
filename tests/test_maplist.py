"""Map + list as one thing with one selection (``scout.ui.maplist``).

The app is driven in-process with AppTest. A real pydeck tap is emitted by sending the deck's
widget state (the JSON the browser sends) — the same path as the browser, end to end through
the ``on_select`` callback. The browser itself is covered by ``docs/qa/maplist/tap.js``.
"""

from __future__ import annotations

import json
import re

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

from streamlit.proto.WidgetStates_pb2 import WidgetState  # noqa: E402
from streamlit.testing.v1.element_tree import UnknownElement  # noqa: E402

from scout.ui import components, maplist  # noqa: E402


def _app():

    from scout.ui import maplist

    ranked = []
    for i in range(30):
        price = 150_000 + i * 5_000
        ranked.append(
            dict(
                id=100 + i,
                source="xe",
                source_id=f"s{i}",
                url=f"https://www.xe.gr/property/d/x/{i}",
                title=f"Διαμέρισμα {60 + i} τ.μ.",
                price=price,
                area_m2=60 + i,
                price_per_m2=price / (60 + i),
                floor=1.0,
                year_built=2005,
                neighborhood="Χολαργός",
                lat=38.0 + i * 0.001,
                lng=23.8,
                location_precision="exact" if i % 3 == 0 else "approx",
                est_monthly_rent=700,
                page_checked=True,
            )
        )
    ranked[29]["lat"] = None  # one listing without a position
    maplist.render(ranked, key="t")


@pytest.fixture
def at():
    a = AppTest.from_function(_app, default_timeout=60).run()
    assert not a.exception, a.exception
    return a


def _cards(a) -> list[int]:
    return [
        int(x) for m in a.markdown for x in re.findall(r'class="hg-card" data-lid="(\d+)"', m.value)
    ]


def _header(a) -> str:
    return next(m.value for m in a.markdown if re.match(r"\*\*\d+ από ", m.value))


def _deck(a) -> UnknownElement:
    def find(node):
        for c in getattr(node, "children", {}).values():
            if isinstance(c, UnknownElement) and c.type == "deck_gl_json_chart":
                return c
            if hit := find(c):
                return hit
        return None

    return find(a._tree)


def _tap(a, lid: int, click: str | None = None):
    """What the browser sends when a point is tapped (Streamlit's PydeckSelectionSerde).

    ``click``: also press that button in the same run — the browser keeps re-sending the last
    tap with every later interaction, so this is how «Επόμενο» arrives after a tap."""
    if click:
        a.button(key=click).click()
    ws = a._tree.get_widget_states()
    sel = {"selection": {"indices": {"pts": [0]}, "objects": {"pts": [{"lid": lid}]}}}
    ws.widgets.append(WidgetState(id=_deck(a).proto.id, string_value=json.dumps(sel)))
    a._run(widget_state=ws)
    assert not a.exception, a.exception
    return a


def test_nothing_selected_shows_first_card_under_the_map_and_a_hint(at):
    assert "selected_id" not in at.session_state or at.session_state["selected_id"] is None
    assert _header(at).startswith("**1 από 30**")
    assert maplist.HINT in _header(at)
    cards = _cards(at)
    assert cards[0] == 100  # the card under the map = first of ranked
    assert cards[1:] == list(range(100, 110))  # then the list, 10 at a time
    deck = _deck(at)
    assert deck is not None and deck.proto.selection_mode  # selectable map
    assert "Δείξε άλλες 10" in [b.label for b in at.button]


def test_tapping_a_point_selects_it_and_its_card_renders_under_the_map(at):
    _tap(at, 107)
    assert at.session_state["selected_id"] == 107
    assert _header(at).startswith("**8 από 30**")
    assert maplist.APPROX in _header(at)  # 107 has an area-centre position
    assert maplist.HINT not in _header(at)
    assert _cards(at)[0] == 107
    spec = json.loads(_deck(at).proto.json)
    ring = next(layer for layer in spec["layers"] if layer["id"] == "sel")
    assert len(ring["data"]) == 1 and ring["data"][0]["lid"] == 107
    vs = spec["initialViewState"]
    lat, lng = components.map_position({"lat": 38.007, "lng": 23.8, "source": "xe",
                                        "source_id": "s7", "location_precision": "approx"})  # fmt: skip
    assert vs["latitude"] == pytest.approx(lat) and vs["longitude"] == pytest.approx(lng)


def test_prev_next_walk_the_ranked_list_and_a_stale_tap_does_not_win(at):
    _tap(at, 103)
    assert "θέση κατά" not in _header(at)  # 103 is exact
    _tap(at, 103, click="t-next")  # the same (old) tap re-sent with «Επόμενο»: Επόμενο wins
    assert at.session_state["selected_id"] == 104
    _tap(at, 103, click="t-next")
    assert at.session_state["selected_id"] == 105
    assert _cards(at)[0] == 105
    at.button(key="t-prev").click().run()
    at.button(key="t-prev").click().run()
    at.button(key="t-prev").click().run()
    assert at.session_state["selected_id"] == 102
    assert _header(at).startswith("**3 από 30**")


def test_next_from_nothing_selected_goes_to_the_second_and_wraps(at):
    at.button(key="t-next").click().run()
    assert at.session_state["selected_id"] == 101
    at.button(key="t-prev").click().run()
    at.button(key="t-prev").click().run()
    assert at.session_state["selected_id"] == 129  # wraps to the last
    assert maplist.NO_POSITION in _header(at)  # 129 has no lat/lng


def test_show_10_more_grows_the_list_and_on_the_map_selects(at):
    at.button(key="t-more").click().run()
    assert len(_cards(at)) == 1 + 20
    at.button(key="t-more").click().run()
    assert len(_cards(at)) == 1 + 30
    assert "t-more" not in [b.key for b in at.button]
    # «Στον χάρτη» on the 25th card: selects it, and the card under the map follows
    on_map = [b for b in at.button if b.label == "Στον χάρτη"]
    assert len(on_map) == 30
    on_map[24].click().run()
    assert at.session_state["selected_id"] == 124
    assert _cards(at)[0] == 124
    assert not at.exception


def test_select_helper_is_the_single_selection_state():
    from streamlit.testing.v1 import AppTest

    def app():
        import streamlit as st

        from scout.ui import maplist

        maplist.select("k", 7)
        st.write(sorted(k for k in st.session_state if "7" in str(st.session_state[k])))

    a = AppTest.from_function(app).run()
    assert a.session_state["selected_id"] == 7
    stored = [k for k in a.session_state if a.session_state[k] == 7]
    assert stored == ["selected_id"]


def test_ring_only_for_the_selected_point_and_centred_on_it():
    rows = [
        {"id": 1, "lat": 38.0, "lng": 23.8, "location_precision": "exact", "price": 1},
        {"id": 2, "lat": 38.1, "lng": 23.9, "location_precision": "approx", "price": 1},
    ]
    assert components.selected_view(rows[0]) == (38.0, 23.8, 15.0)
    assert components.selected_view(rows[1])[2] == 13.5  # no street zoom for area centres
    recs = components.map_records(rows)
    assert [r["lid"] for r in recs] == [1, 2]
