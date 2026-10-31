"""Guards for the '0 m to metro' bugs (station-coincident centroids + degenerate OSRM)."""

from scout.enrich import (
    METRO_STATIONS,
    MUNICIPALITY_CENTROIDS,
    haversine_m,
    nearest_metro,
)


def test_no_municipality_centroid_sits_on_a_station():
    """An area centroid placed on its metro station makes every card-only listing there
    read '0 m to metro' (false) and piles every map dot onto the station."""
    # 80 m catches the "station coordinate copied verbatim" bug (exact 0 m) while allowing
    # neighborhoods that genuinely hug their station (e.g. Koukaki ~150 m from Syngrou-Fix).
    offenders = []
    for area, (lat, lng) in MUNICIPALITY_CENTROIDS.items():
        nearest = min(haversine_m(lat, lng, s[0], s[1]) for s in METRO_STATIONS.values())
        if nearest < 80:
            offenders.append((area, round(nearest)))
    assert not offenders, f"centroids sitting on a station: {offenders}"


def test_nearest_metro_falls_back_when_osrm_returns_zero(monkeypatch):
    import scout.enrich as enrich

    # Force OSRM to return a degenerate 0-distance route.
    monkeypatch.setattr(enrich, "_osrm_walking_distance_m", lambda *a, **k: 0.0)
    # A point ~1 km from Agia Paraskevi station must NOT come back as 0 m.
    res = nearest_metro(38.0085, 23.8195, use_osrm=True)
    assert res.metro_distance_m is not None and res.metro_distance_m > 0


def test_nearest_metro_offline_is_plausible():
    res = nearest_metro(38.0085, 23.8195, use_osrm=False)
    assert res.nearest_metro == "Μετρό Αγία Παρασκευή"
    assert 500 < res.metro_distance_m < 3000
