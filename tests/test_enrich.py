"""Unit tests for enrichment — pure helpers run offline (use_network=False)."""

from __future__ import annotations

from scout.enrich import (
    METRO_STATIONS,
    enrich_listing,
    estimate_monthly_rent,
    gross_yield,
    haversine_m,
    nearest_metro,
    neighborhood_centroid,
    price_per_m2,
)

from .conftest import make_listing


def test_neighborhood_centroid_matches_greek_and_latin():
    # XE's real label form.
    lat, lng = neighborhood_centroid("Χολαργός (Άνω Χολαργός)")
    assert lat is not None and 37.9 < lat < 38.1 and 23.7 < lng < 23.9
    # Latin transliteration resolves too.
    assert neighborhood_centroid("Ano Cholargos") == neighborhood_centroid(
        "Χολαργός (Άνω Χολαργός)"
    )
    # Bare-Cholargos catch-all still returns a point.
    assert neighborhood_centroid("Χολαργός") != (None, None)
    # Unknown / empty -> no guess.
    assert neighborhood_centroid("Kolonaki") == (None, None)
    assert neighborhood_centroid(None) == (None, None)


def test_geocode_circuit_breaker_trips_and_skips(monkeypatch):
    """After the first web-geocoder failure the breaker trips, so later listings skip
    the doomed network round-trip (what makes a region-wide run fast on cloud hosts)."""
    import geopy.geocoders

    import scout.enrich as en

    monkeypatch.setattr(en, "_web_geocode_available", True)
    calls = {"n": 0}

    class _Boom:
        def __init__(self, **kw):
            pass

        def geocode(self, query):
            calls["n"] += 1
            raise RuntimeError("HTTP 403")

    monkeypatch.setattr(geopy.geocoders, "Nominatim", _Boom)

    assert en.geocode("Somewhere") == (None, None)  # attempts once, fails, trips breaker
    assert calls["n"] == 1
    assert en._web_geocode_available is False
    assert en.geocode("Elsewhere") == (None, None)  # skipped, no new network call
    assert calls["n"] == 1


def test_enrich_falls_back_to_centroid_when_ungeocoded():
    """No lat/lng and no network -> the neighborhood centroid still yields a metro
    distance instead of leaving the listing unlocated."""
    lst = make_listing(
        lat=None, lng=None, neighborhood="Χολαργός (Πλατεία Δημοκρατίας)", metro_distance_m=None
    )
    enriched = enrich_listing(lst, use_network=False)
    assert enriched.lat is not None and enriched.lng is not None
    assert enriched.metro_distance_m is not None
    assert enriched.nearest_metro in METRO_STATIONS


def test_haversine_zero_distance():
    assert haversine_m(38.0, 23.8, 38.0, 23.8) == 0.0


def test_haversine_known_order_of_magnitude():
    # Holargos to Ethniki Amyna is roughly ~1km.
    h = METRO_STATIONS["Holargos"]
    e = METRO_STATIONS["Ethniki Amyna"]
    d = haversine_m(*h, *e)
    assert 500 < d < 2500


def test_price_per_m2():
    assert price_per_m2(200_000, 80.0) == 2500.0
    assert price_per_m2(200_000, 0) is None


def test_gross_yield():
    assert gross_yield(900, 200_000) == round(900 * 12 / 200_000, 4)
    assert gross_yield(None, 200_000) is None
    assert gross_yield(900, 0) is None


def test_estimate_rent_prefers_listed_rent():
    lst = make_listing(listed_rent=1000)
    assert estimate_monthly_rent(lst, median_rent_per_m2=10.0) == 1000


def test_estimate_rent_uses_median_when_no_listed():
    lst = make_listing(listed_rent=None, area_m2=80.0)
    assert estimate_monthly_rent(lst, median_rent_per_m2=10.0) == 800


def test_nearest_metro_haversine_fallback():
    # Coordinates right on the Holargos station -> nearest is Holargos.
    lat, lng = METRO_STATIONS["Holargos"]
    result = nearest_metro(lat, lng, use_osrm=False)
    assert result.nearest_metro == "Holargos"
    assert result.metro_distance_m == 0


def test_nearest_metro_none_without_coords():
    result = nearest_metro(None, None, use_osrm=False)
    assert result.nearest_metro is None
    assert result.metro_distance_m is None


def test_enrich_listing_offline_computes_derived_fields():
    lst = make_listing(
        lat=METRO_STATIONS["Holargos"][0],
        lng=METRO_STATIONS["Holargos"][1],
        price=200_000,
        area_m2=80.0,
        listed_rent=900,
        metro_distance_m=None,
        price_per_m2=None,
        gross_yield=None,
        est_monthly_rent=None,
    )
    enriched = enrich_listing(lst, median_rent_per_m2=10.0, use_network=False)
    assert enriched.price_per_m2 == 2500.0
    assert enriched.nearest_metro == "Holargos"
    assert enriched.metro_distance_m == 0
    assert enriched.est_monthly_rent == 900
    assert enriched.gross_yield == round(900 * 12 / 200_000, 4)
