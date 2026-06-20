"""Enrichment: geocode, metro distance, EUR/m2, estimated rent, gross yield.

Network calls (Nominatim, OSRM) are isolated behind small functions and guarded
by a DB cache, so unit tests can run fully offline by exercising the pure helpers
(``haversine_m``, ``price_per_m2``, ``gross_yield``) or by stubbing the callers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import requests

from .config import Settings, get_settings
from .models import Listing

# Holargos-line (Metro Line 3) stations relevant to the strategy area.
METRO_STATIONS: dict[str, tuple[float, float]] = {
    "Holargos": (37.9997, 23.7960),
    "Nomismatokopio": (38.0060, 23.8090),
    "Ethniki Amyna": (37.9943, 23.7855),
    "Agia Paraskevi": (38.0167, 23.8230),
}

EARTH_RADIUS_M = 6_371_000
# Multiplier to approximate walking distance from straight-line (street grid detour).
WALK_DETOUR_FACTOR = 1.3


@dataclass
class MetroResult:
    nearest_metro: str | None
    metro_distance_m: int | None


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def price_per_m2(price: int, area_m2: float) -> float | None:
    if not area_m2 or area_m2 <= 0:
        return None
    return round(price / area_m2, 2)


def gross_yield(est_monthly_rent: int | None, price: int) -> float | None:
    if not est_monthly_rent or not price or price <= 0:
        return None
    return round((est_monthly_rent * 12) / price, 4)


def estimate_monthly_rent(listing: Listing, median_rent_per_m2: float | None) -> int | None:
    """Prefer a real listed rent (ground-truth comp); else median EUR/m2 * area."""
    if listing.listed_rent:
        return listing.listed_rent
    if median_rent_per_m2 and listing.area_m2:
        return int(round(median_rent_per_m2 * listing.area_m2))
    return None


# ---- Network-backed enrichment (cache-guarded) ----------------------------


def _osrm_walking_distance_m(
    lat: float, lng: float, slat: float, slng: float, settings: Settings
) -> float | None:
    """Walking distance via OSRM. Returns None on any failure (caller falls back)."""
    url = (
        f"{settings.osrm_base_url.rstrip('/')}/route/v1/foot/"
        f"{lng},{lat};{slng},{slat}?overview=false"
    )
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        routes = data.get("routes") or []
        if routes:
            return float(routes[0]["distance"])
    except (requests.RequestException, ValueError, KeyError):
        return None
    return None


def nearest_metro(
    lat: float | None,
    lng: float | None,
    settings: Settings | None = None,
    use_osrm: bool = True,
) -> MetroResult:
    """Nearest Holargos-line station and walking distance.

    Tries OSRM walking route; falls back to haversine * WALK_DETOUR_FACTOR. The
    nearest station is chosen by haversine first (cheap), then refined.
    """
    if lat is None or lng is None:
        return MetroResult(None, None)
    settings = settings or get_settings()

    # Pick nearest by straight-line, then compute walking distance to that one.
    best_name, best_hav = None, math.inf
    best_coords = None
    for name, (slat, slng) in METRO_STATIONS.items():
        d = haversine_m(lat, lng, slat, slng)
        if d < best_hav:
            best_name, best_hav, best_coords = name, d, (slat, slng)

    if best_coords is None:
        return MetroResult(None, None)

    dist: float | None = None
    if use_osrm:
        dist = _osrm_walking_distance_m(lat, lng, best_coords[0], best_coords[1], settings)
    if dist is None:
        dist = best_hav * WALK_DETOUR_FACTOR
    return MetroResult(best_name, int(round(dist)))


def geocode(address: str, session=None, settings: Settings | None = None):
    """Geocode an address via Nominatim, caching in ``geocode_cache``.

    ``session`` is an optional SQLAlchemy session for caching. Returns (lat, lng)
    or (None, None). Respects Nominatim's 1 req/s policy implicitly via caching.
    """
    from sqlalchemy import select

    from .models import GeocodeCacheRow

    settings = settings or get_settings()
    base = address.strip()
    if not base:
        return None, None
    # Give Nominatim a well-formed query: a bare Greek neighborhood token geocodes
    # poorly or to the wrong place. Append the country when not already present.
    query = base if "ελλ" in base.lower() or "greece" in base.lower() else f"{base}, Greece"

    if session is not None:
        cached = session.scalar(select(GeocodeCacheRow).where(GeocodeCacheRow.query == query))
        if cached is not None:
            return cached.lat, cached.lng

    lat = lng = None
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent=settings.geocoder_user_agent, timeout=8)
        loc = geolocator.geocode(query)
        if loc:
            lat, lng = loc.latitude, loc.longitude
    except Exception:
        lat = lng = None

    # Only cache successes. Caching a failure permanently (the table is unique on
    # query) would leave a listing un-geocoded forever after one transient timeout.
    if session is not None and lat is not None and lng is not None:
        session.add(GeocodeCacheRow(query=query, lat=lat, lng=lng, observed_at=datetime.utcnow()))
        session.flush()
    return lat, lng


def enrich_listing(
    listing: Listing,
    median_rent_per_m2: float | None = None,
    session=None,
    settings: Settings | None = None,
    use_network: bool = True,
) -> Listing:
    """Populate computed fields on a listing in place and return it.

    Pure computations (EUR/m2, rent, yield) always run. Network steps (geocode,
    OSRM) run only when ``use_network`` and degrade gracefully.
    """
    settings = settings or get_settings()

    if (listing.lat is None or listing.lng is None) and listing.address and use_network:
        listing.lat, listing.lng = geocode(listing.address, session=session, settings=settings)

    metro = nearest_metro(listing.lat, listing.lng, settings=settings, use_osrm=use_network)
    listing.nearest_metro = metro.nearest_metro
    listing.metro_distance_m = metro.metro_distance_m

    listing.price_per_m2 = price_per_m2(listing.price, listing.area_m2)
    listing.est_monthly_rent = estimate_monthly_rent(listing, median_rent_per_m2)
    listing.gross_yield = gross_yield(listing.est_monthly_rent, listing.price)
    return listing
