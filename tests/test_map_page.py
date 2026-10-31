"""The 🗺 Χάρτης page: every filter works and actually narrows the map."""

from __future__ import annotations

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


def test_map_filters_narrow_the_points(env):  # noqa: F811
    at = fresh(MAP)
    ok(at, "open")
    total = _count(at)
    assert total > 0
    assert len(at.dataframe) == 1  # the top-20 table
    # areas are grouped by municipality and labelled with counts
    areas = at.multiselect(key="map_areas")
    assert any(o.startswith("Χολαργός (") for o in areas.options), areas.options
    areas.set_value(["Χολαργός"]).run()
    ok(at, "area")
    by_area = _count(at)
    assert 0 < by_area < total
    seen = []
    for threshold in range(5, 100, 5):
        at.slider(key="map_score").set_value(threshold).run()
        ok(at, f"score {threshold}")
        seen.append(_count(at))
    assert seen == sorted(seen, reverse=True)
    assert any(0 < n < by_area for n in seen), seen  # the min score really narrows the map
    at.slider(key="map_score").set_value(100).run()
    ok(at, "score 100")
    assert _count(at) == 0
    assert any("χαλάρωσε τα φίλτρα" in i.value for i in at.info)
    at.slider(key="map_score").set_value(0).run()
    assert _count(at) == by_area


def test_map_other_filters_run(env):  # noqa: F811
    at = fresh(MAP)
    total = _count(at)
    lo, hi = at.slider(key="map_price").value
    at.slider(key="map_price").set_value((lo, lo + (hi - lo) // 20 * 10)).run()
    ok(at, "price")
    assert _count(at) < total
    at.slider(key="map_price").set_value((lo, hi)).run()
    at.slider(key="map_age").set_value(10).run()
    ok(at, "age")
    with_unknown = _count(at)
    at.checkbox(key="map_age_unknown").uncheck().run()
    ok(at, "age unknown")
    assert _count(at) <= with_unknown
    for key in ("map_fresh", "map_hide", "map_size"):
        at.checkbox(key=key).set_value(not at.checkbox(key=key).value).run()
        ok(at, key)
    assert _count(at) >= 0


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
