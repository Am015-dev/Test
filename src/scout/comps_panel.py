"""Comparable-listings panel for a value estimate.

Pure functions only: no DB, no network, no Streamlit. Given a target listing
dict and a pool of candidate listing dicts (the shape produced by
``scout.ui.queries._row_to_dict``), ``comparable_listings`` returns the N most
comparable *active* listings so a buyer can see the comps behind a value
estimate — with each comp's EUR/m2 delta vs the target so the UI can render
"this flat is +12% EUR/m2 vs comp".

Where ``scout.comps.find_comparables`` is a strict same-neighborhood filter
with hard area/price tolerances, this panel is deliberately softer: it prefers
same-neighborhood comps, falls back to the same search_area/region, and ranks
everything by a weighted size + EUR/m2 similarity so a panel is never empty
just because nothing sat inside a tolerance band. Fails soft; never raises.
"""

from __future__ import annotations

from typing import Any

# Similarity weights: how much of the distance score comes from size vs price.
# Split evenly — a comp should be close in both floor area and EUR/m2.
_AREA_WEIGHT = 0.5
_PPM2_WEIGHT = 0.5

# Locality tiers, best first. Same neighborhood beats same area/region beats
# anywhere else, regardless of raw similarity.
_TIER_NEIGHBORHOOD = 0
_TIER_AREA = 1
_TIER_OTHER = 2

# Key fields copied onto each returned comp, plus the computed ``ppm2_delta_pct``.
_KEY_FIELDS = (
    "id",
    "neighborhood",
    "search_area",
    "region",
    "area_m2",
    "price",
    "price_per_m2",
    "energy_class",
    "year_built",
    "url",
    "title",
)


def _normalized(value: Any) -> str | None:
    """Lowercase + trim a string; return None if unusable."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed.lower() if trimmed else None


def _ppm2(listing: dict[str, Any]) -> float | None:
    """Price per square meter for a listing.

    Uses the listing's own ``price_per_m2`` when present, otherwise falls back
    to ``price / area_m2`` when both are usable positive numbers.
    """
    ppm2 = listing.get("price_per_m2")
    if isinstance(ppm2, int | float) and ppm2 > 0:
        return float(ppm2)

    price = listing.get("price")
    area = listing.get("area_m2")
    if isinstance(price, int | float) and isinstance(area, int | float) and price > 0 and area > 0:
        return float(price) / float(area)

    return None


def _area(listing: dict[str, Any]) -> float | None:
    """Usable positive floor area, else None."""
    area = listing.get("area_m2")
    if isinstance(area, int | float) and area > 0:
        return float(area)
    return None


def _is_active(listing: dict[str, Any]) -> bool:
    """A listing counts as active unless it is explicitly excluded or its
    ``status`` is set to something other than ``"active"`` (missing status is
    treated as active so a thin card-only pool still yields comps)."""
    if listing.get("excluded"):
        return False
    status = listing.get("status")
    return status is None or status == "active"


def _tier(listing: dict[str, Any], target: dict[str, Any]) -> int:
    """Locality tier for ``listing`` relative to ``target`` (lower = closer)."""
    t_neighborhood = _normalized(target.get("neighborhood"))
    l_neighborhood = _normalized(listing.get("neighborhood"))
    if t_neighborhood is not None and l_neighborhood == t_neighborhood:
        return _TIER_NEIGHBORHOOD

    t_locality = {
        loc
        for loc in (_normalized(target.get("search_area")), _normalized(target.get("region")))
        if loc is not None
    }
    l_locality = {
        loc
        for loc in (_normalized(listing.get("search_area")), _normalized(listing.get("region")))
        if loc is not None
    }
    if t_locality & l_locality:
        return _TIER_AREA

    return _TIER_OTHER


def comparable_listings(
    target: dict[str, Any],
    pool: list[dict[str, Any]],
    n: int = 5,
) -> list[dict[str, Any]]:
    """Return the ``n`` most comparable active listings for ``target``.

    A candidate qualifies when it is not the target (different ``id``), is
    active (see ``_is_active``), and has a usable positive ``area_m2`` and a
    computable EUR/m2 (own ``price_per_m2`` or ``price / area_m2``).

    Candidates are ordered by, in priority:
      1. locality tier — same neighborhood, then same search_area/region, then
         anywhere else;
      2. weighted similarity distance — a blend of relative size difference and
         relative EUR/m2 difference from the target (closer = better).

    Each returned dict carries the comp's key fields (id, neighborhood,
    search_area, region, area_m2, price, price_per_m2, energy_class,
    year_built, url, title — whichever are present) plus ``ppm2_delta_pct``:
    the comp's EUR/m2 relative to the target's as a signed percent (negative =
    cheaper per m2 than the target), or ``None`` when the target's EUR/m2 is
    unavailable.

    Fails soft: returns ``[]`` on a missing/empty pool or a target that lacks a
    usable area. Never raises.
    """
    try:
        if not pool:
            return []

        target_area = _area(target)
        if target_area is None:
            return []
        target_ppm2 = _ppm2(target)
        target_id = target.get("id")

        ranked: list[tuple[int, float, dict[str, Any]]] = []
        for listing in pool:
            if listing.get("id") == target_id:
                continue
            if not _is_active(listing):
                continue

            area = _area(listing)
            comp_ppm2 = _ppm2(listing)
            if area is None or comp_ppm2 is None:
                continue

            area_dist = abs(area - target_area) / target_area
            if target_ppm2 is not None and target_ppm2 > 0:
                ppm2_dist = abs(comp_ppm2 - target_ppm2) / target_ppm2
                ppm2_delta_pct = (comp_ppm2 - target_ppm2) / target_ppm2 * 100.0
            else:
                ppm2_dist = 0.0
                ppm2_delta_pct = None

            distance = _AREA_WEIGHT * area_dist + _PPM2_WEIGHT * ppm2_dist

            comp = {field: listing.get(field) for field in _KEY_FIELDS if field in listing}
            comp["ppm2_delta_pct"] = ppm2_delta_pct
            ranked.append((_tier(listing, target), distance, comp))

        ranked.sort(key=lambda r: (r[0], r[1]))

        if n < 0:
            n = 0
        return [comp for _, _, comp in ranked[:n]]
    except Exception:
        return []
