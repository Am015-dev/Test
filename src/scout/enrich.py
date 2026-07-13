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
from .finance import net_yield as _net_yield_after_costs
from .models import Listing

# Metro **Line 2 (red)** and **Line 3 (blue)** stations — the modern metro the strategy
# counts. The Line 1 / ISAP electric railway (Kifisia, Marousi, Nea Ionia) is deliberately
# excluded, so listings out there correctly fall outside the max-metro-distance filter.
# Coordinates are OSM station nodes (~11 m precision), cross-checked against Wikipedia.
METRO_STATIONS: dict[str, tuple[float, float]] = {
    # Line 3 (blue) — north-east corridor
    "Evangelismos": (37.9761, 23.7471),
    "Megaro Moussikis": (37.9790, 23.7530),
    "Ambelokipi": (37.9872, 23.7577),
    "Panormou": (37.9932, 23.7636),
    "Katehaki": (37.9931, 23.7764),
    "Ethniki Amyna": (37.9992, 23.7845),
    "Holargos": (38.0049, 23.7947),
    "Nomismatokopio": (38.0091, 23.8058),
    "Agia Paraskevi": (38.0171, 23.8125),
    "Chalandri": (38.0217, 23.8208),
    "Doukissis Plakentias": (38.0240, 23.8326),
    # Line 2 (red) — southern corridor
    "Syntagma": (37.9755, 23.7357),
    "Akropoli": (37.9689, 23.7295),
    "Syngrou-Fix": (37.9646, 23.7268),
    "Neos Kosmos": (37.9577, 23.7284),
    "Agios Ioannis": (37.9564, 23.7347),
    "Dafni": (37.9496, 23.7372),
    "Agios Dimitrios": (37.9404, 23.7407),
    "Ilioupoli": (37.9297, 23.7445),
    "Alimos": (37.9181, 23.7442),
    "Argyroupoli": (37.9030, 23.7455),
    "Elliniko": (37.8926, 23.7471),
    # Line 2 (red) — north-west leg (Peristeri)
    "Larissa Station": (37.9923, 23.7207),
    "Attiki": (37.9995, 23.7228),
    "Sepolia": (38.0026, 23.7140),
    "Agios Antonios": (38.0061, 23.6997),
    "Peristeri": (38.0129, 23.6958),
    "Anthoupoli": (38.0171, 23.6909),
    # Line 3 (blue) — west leg to Piraeus (Aigaleo / Nikaia / Korydallos / Piraeus)
    "Kerameikos": (37.9787, 23.7110),
    "Eleonas": (37.9878, 23.6934),
    "Aigaleo": (37.9914, 23.6818),
    "Agia Marina": (37.9969, 23.6671),
    "Nikaia": (37.9658, 23.6473),
    "Korydallos": (37.9771, 23.6504),
    "Maniatika": (37.9596, 23.6398),
    "Piraeus": (37.9481, 23.6423),
    "Dimotiko Theatro": (37.9429, 23.6476),
}

EARTH_RADIUS_M = 6_371_000
# Multiplier to approximate walking distance from straight-line (street grid detour).
WALK_DETOUR_FACTOR = 1.3

# Approximate centroids of Cholargos' sub-neighborhoods (WGS84). Used as a free,
# offline geocoding fallback when per-listing geocoding is unavailable — Nominatim
# 403s cloud/proxy IPs, which would otherwise leave every listing without a location
# (no map point, no metro distance). Keyed by accent-stripped substring so they match
# XE's labels like "Χολαργός (Άνω Χολαργός)". Order matters: more specific first, the
# bare-Cholargos town centroid last as a catch-all.
_NEIGHBORHOOD_CENTROIDS: tuple[tuple[str, tuple[float, float]], ...] = (
    ("ano cholargos", (38.0035, 23.7925)),
    ("ανω χολαργος", (38.0035, 23.7925)),
    ("τσακ", (38.0028, 23.8006)),  # Τσακός / Λόφος Τσακού (SE, toward Papagou)
    ("tsak", (38.0028, 23.8006)),
    ("δημοκρατ", (37.9998, 23.7952)),  # Πλατεία Δημοκρατίας (central, by the station)
    ("dimokrat", (37.9998, 23.7952)),
    ("φανερωμ", (38.0018, 23.7935)),  # Φανερωμένη
    ("faneromen", (38.0018, 23.7935)),
    ("χολαργ", (38.0003, 23.7950)),  # bare Cholargos town centre (catch-all)
    ("cholargos", (38.0003, 23.7950)),
)


# Approximate municipality centroids (WGS84) for every scraped area, keyed by the exact
# ``search_area`` string. Used as a free, offline location fallback so a CARD-ONLY listing
# (collected without a detail-page fetch) still gets a map point and a metro-distance
# estimate — the difference between "thousands of listings, all locatable" and "thousands
# with no location". Coarse by design (a municipality centre, ~1-2 km), refined to the real
# point whenever the detail page is later fetched.
# These are municipality/town CENTRES (main square or town hall), deliberately NOT the
# metro station — an area centroid placed on the station would make every card-only
# listing there read "0 m to metro" (provably false) and pile every map dot onto the
# station. Each point sits 0.4–1.5 km from its station, an honest area-level anchor.
MUNICIPALITY_CENTROIDS: dict[str, tuple[float, float]] = {
    # Κέντρο Αθήνας
    "Koukaki": (37.9635, 23.7278),
    "Pagkrati": (37.9685, 23.7530),
    "Ampelokipoi": (37.9880, 23.7640),
    "Exarcheia": (37.9862, 23.7330),
    "Kolonaki": (37.9795, 23.7440),
    "Neos Kosmos": (37.9555, 23.7250),
    "Metaxourgeio": (37.9865, 23.7205),
    "Gkyzi": (37.9930, 23.7420),
    "Kypseli": (37.9930, 23.7360),
    "Zografou": (37.9790, 23.7700),
    "Vyronas": (37.9610, 23.7560),
    "Kaisariani": (37.9660, 23.7660),
    "Galatsi": (38.0180, 23.7480),
    # Βόρεια Προάστια
    "Cholargos": (38.0003, 23.7950),
    "Papagou": (37.9950, 23.7960),
    "Agia Paraskevi": (38.0085, 23.8195),
    "Chalandri": (38.0235, 23.7990),
    "Vrilissia": (38.0330, 23.8320),
    "Marousi": (38.0500, 23.8070),
    # Νότια Προάστια
    "Nea Smyrni": (37.9450, 23.7140),
    "Agios Dimitrios": (37.9330, 23.7330),
    "Dafni": (37.9475, 23.7345),
    "Ilioupoli": (37.9300, 23.7540),
    "Alimos": (37.9095, 23.7300),
    "Argyroupoli": (37.9020, 23.7530),
    "Elliniko": (37.8870, 23.7420),
    "Kallithea": (37.9560, 23.7010),
    "Moschato": (37.9540, 23.6810),
    "Glyfada": (37.8650, 23.7540),
    # Δυτικά Προάστια
    "Aigaleo": (37.9955, 23.6810),
    "Peristeri": (38.0150, 23.6910),
    "Haidari": (38.0180, 23.6520),
    # Πειραιάς
    "Piraeus": (37.9435, 23.6500),
    "Nikaia": (37.9680, 23.6420),
    "Korydallos": (37.9800, 23.6500),
    "Agios Ioannis Rentis": (37.9640, 23.6690),
    "Tavros": (37.9640, 23.6960),
}


def municipality_centroid(search_area: str | None) -> tuple[float | None, float | None]:
    """Approximate (lat, lng) for a scraped municipality, or (None, None) if unknown."""
    if not search_area:
        return None, None
    coords = MUNICIPALITY_CENTROIDS.get(search_area)
    return coords if coords else (None, None)


def neighborhood_centroid(neighborhood: str | None) -> tuple[float | None, float | None]:
    """Best-effort (lat, lng) for a Cholargos sub-neighborhood label, else (None, None).

    Accent- and case-insensitive substring match, so both Greek and Latin labels work.
    Deliberately coarse: a centroid is a fallback for the map and a metro-distance
    estimate, not a precise per-listing fix.
    """
    if not neighborhood:
        return None, None
    from unicodedata import category, normalize

    norm = "".join(c for c in normalize("NFD", neighborhood.lower()) if category(c) != "Mn").strip()
    for key, coords in _NEIGHBORHOOD_CENTROIDS:
        if key in norm:
            return coords
    return None, None


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
    if not area_m2 or area_m2 <= 0 or not price or price <= 0:
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
    # A non-positive OSRM distance is a degenerate response (both points snapped to the
    # same node, or a malformed route), NOT a flat literally at the station entrance —
    # fall back to the straight-line estimate so we never surface an implausible "0 m".
    if dist is None or dist <= 0:
        dist = best_hav * WALK_DETOUR_FACTOR
    return MetroResult(best_name, int(round(dist)))


# Circuit breaker: Nominatim 403s cloud/proxy IPs, and it does so persistently (it's
# IP-based). Without this, a region-wide run pays a doomed network round-trip for every
# single listing (hundreds × seconds). After the first failure we stop calling the web
# geocoder for the rest of the process and fall straight through to the offline centroid
# fallback. On a host where Nominatim works, it never trips.
_web_geocode_available = True


def geocode(address: str, session=None, settings: Settings | None = None):
    """Geocode an address via Nominatim, caching in ``geocode_cache``.

    ``session`` is an optional SQLAlchemy session for caching. Returns (lat, lng)
    or (None, None). Respects Nominatim's 1 req/s policy implicitly via caching.
    """
    global _web_geocode_available
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

    # A cache miss with the web geocoder already known-blocked: skip the round-trip.
    if not _web_geocode_available:
        return None, None

    lat = lng = None
    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent=settings.geocoder_user_agent, timeout=8)
        loc = geolocator.geocode(query)
        if loc:
            lat, lng = loc.latitude, loc.longitude
    except Exception:
        # Trip the breaker: on cloud hosts this is a persistent 403, not transient.
        _web_geocode_available = False
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
    rent_is_comp: bool = False,
) -> Listing:
    """Populate computed fields on a listing in place and return it.

    Pure computations (EUR/m2, rent, yield) always run. Network steps (geocode,
    OSRM) run only when ``use_network`` and degrade gracefully.

    ``rent_is_comp`` tells us whether ``median_rent_per_m2`` is a REAL local rent comp
    (a scraped/neighbourhood median) or the flat fallback baseline. It's recorded on
    ``rent_estimated`` so scoring won't treat a baseline-derived yield as a real signal.
    """
    settings = settings or get_settings()

    # Track how precisely we located the listing. A real point (its own coordinates, or a
    # geocoded street address) is "exact"; a centroid fallback is "approx" — the same point
    # for a whole area, which must not masquerade as a precise per-listing metro distance.
    had_own_point = listing.lat is not None and listing.lng is not None
    if not had_own_point and listing.address and use_network:
        listing.lat, listing.lng = geocode(listing.address, session=session, settings=settings)
    geocoded = not had_own_point and listing.lat is not None and listing.lng is not None

    # Free, offline fallback when per-listing geocoding didn't resolve (e.g. Nominatim
    # 403s cloud IPs, or a card-only listing with no detail-page coordinates): place the
    # listing at its neighborhood centroid, then at its municipality centroid, so the map
    # still shows an area — but flagged "approx" so metro distance isn't scored as precise.
    if listing.lat is None or listing.lng is None:
        listing.lat, listing.lng = neighborhood_centroid(listing.neighborhood)
    if listing.lat is None or listing.lng is None:
        listing.lat, listing.lng = municipality_centroid(listing.search_area)
    listing.location_precision = "exact" if (had_own_point or geocoded) else "approx"

    metro = nearest_metro(listing.lat, listing.lng, settings=settings, use_osrm=use_network)
    listing.nearest_metro = metro.nearest_metro
    listing.metro_distance_m = metro.metro_distance_m

    listing.price_per_m2 = price_per_m2(listing.price, listing.area_m2)
    listing.est_monthly_rent = estimate_monthly_rent(listing, median_rent_per_m2)
    # Rent is a real datapoint only if the listing stated its own rent, or the median we
    # applied was a genuine local comp; otherwise it's the flat baseline (an estimate).
    listing.rent_estimated = not (listing.listed_rent or rent_is_comp)
    listing.gross_yield = gross_yield(listing.est_monthly_rent, listing.price)
    # Net yield after Greek acquisition + holding costs and vacancy (finance.py) — the
    # honest return an investor keeps. Fails soft to None (blank field) on missing rent.
    annual_rent = listing.est_monthly_rent * 12 if listing.est_monthly_rent else None
    listing.net_yield = _net_yield_after_costs(
        listing.price, annual_rent, listing.area_m2, bool(listing.is_private_seller)
    )
    return listing
