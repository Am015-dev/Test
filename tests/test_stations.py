"""Station table (stations.json) and the exact-only distance rule (picks.station_text/near_rail)."""

from __future__ import annotations

import json

from scout import enrich, picks, stations

from .test_ui_gauntlet import env  # noqa: F401 — the gauntlet's seeded DB


def test_table_parses_with_provenance_and_unique_places():
    meta = stations.meta()
    assert meta["source_url"].startswith("https://") and meta["retrieved"] == "2026-10-31"
    all_ = stations.all_stations()
    assert len(all_) >= 70
    assert len({(s.lat, s.lng) for s in all_}) == len(all_)  # no duplicate coordinates
    assert len({s.label for s in all_}) == len(all_)  # a label names one station
    assert all(37.8 < s.lat < 38.2 and 23.5 < s.lng < 24.0 for s in all_)
    assert {s.mode for s in all_} == {"metro", "isap", "rail"}
    assert all(s.name and not s.name.isascii() for s in all_)  # Greek, never Latin
    raw = json.loads(stations.DATA_FILE.read_text(encoding="utf-8"))["stations"]
    assert all(r["wikidata"].startswith("Q") for r in raw)


def test_every_line_1_2_3_station_is_present():
    lines = {n: {s.name for s in stations.all_stations() if n in s.lines} for n in (1, 2, 3)}
    assert (len(lines[1]), len(lines[2]), len(lines[3])) == (24, 20, 23)
    assert {"Περισσός", "Άγιος Δημήτριος", "Χολαργός", "Μοναστηράκι"} <= set.union(*lines.values())


def test_legacy_latin_names_map_to_greek_labels():
    assert stations.label("Holargos") == "Μετρό Χολαργός"
    assert stations.label("Larissa Station") == "Μετρό Σταθμός Λαρίσης"
    assert stations.label("Μετρό Χολαργός") == "Μετρό Χολαργός"
    assert stations.label("Άγνωστο") == "Άγνωστο" and stations.label(None) is None
    for latin in ("Syngrou-Fix", "Katehaki", "Dimotiko Theatro", "Agios Ioannis"):
        assert stations.find(latin) is not None


def test_nearest_metro_uses_the_table_and_returns_greek():
    st = next(s for s in stations.all_stations() if s.name == "Περισσός")
    res = enrich.nearest_metro(st.lat, st.lng, use_osrm=False)
    assert res.nearest_metro == "ΗΣΑΠ Περισσός" and res.metro_distance_m == 0


def test_exact_listing_shows_station_and_distance_and_is_near_rail():
    d = {
        "location_precision": "exact",
        "nearest_metro": "Μετρό Άγιος Δημήτριος",
        "metro_distance_m": 450,
        "neighborhood": "Γαλάτσι (Λαμπρινή)",
    }
    assert picks.station_text(d) == "Μετρό Άγιος Δημήτριος · 450 μ."
    assert picks.near_rail(d) is True
    # an old Latin name on an exact row still reads in Greek; Greek thousands separator
    far = {**d, "nearest_metro": "Agios Dimitrios", "metro_distance_m": 1250}
    assert picks.station_text(far) == "Μετρό Άγιος Δημήτριος · 1.250 μ."
    assert picks.near_rail(far) is False  # exact and far: the neighbourhood name does not rescue it
    assert picks.near_rail({**d, "metro_distance_m": 800}) is True


def test_approx_listing_has_no_distance_and_uses_the_neighbourhood_name():
    d = {
        "location_precision": "approx",
        "nearest_metro": "Holargos",
        "metro_distance_m": 684,
        "neighborhood": "Περισσός",
    }
    text = picks.station_text(d)
    assert text == "ΗΣΑΠ Περισσός (από το όνομα της γειτονιάς)"
    assert "684" not in text and "μ." not in text
    assert picks.near_rail(d) is True
    nameless = {**d, "neighborhood": "Γαλάτσι (Λαμπρινή)"}  # no station in the name
    assert picks.station_text(nameless) == "" and picks.near_rail(nameless) is False


def test_station_keeps_working_for_existing_callers():
    assert picks.station({"neighborhood": "Αθήνα (Αμπελόκηποι)"}).startswith("Μετρό Αμπελόκηποι")


def test_gauntlet_fixture_keeps_a_non_zero_near_rail_count(env):  # noqa: F811
    from scout.ui import queries

    rows = queries.load_listings()
    near = [d for d in rows if picks.near_rail(d)]
    assert rows and near
    assert all(picks.station_text(d) for d in near)
