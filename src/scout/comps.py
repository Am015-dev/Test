"""Comparable-listing search.

Pure functions only: no DB, no network, no Streamlit. Given a target listing
dict and a pool of candidate listing dicts, ``find_comparables`` picks the
listings that are genuine "comps" — same neighborhood, active, not excluded,
and within area/price tolerance of the target — ranked by how close their
price-per-square-meter is to the target's.
"""

from __future__ import annotations

from typing import Any


def _normalized_neighborhood(value: Any) -> str | None:
    """Lowercase + trim a neighborhood string; return None if unusable."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed.lower()


def _ppm2(listing: dict[str, Any]) -> float | None:
    """Price per square meter for a listing.

    Uses the listing's own ``price_per_m2`` when present, otherwise falls
    back to ``price / area_m2`` when both are usable positive numbers.
    """
    ppm2 = listing.get("price_per_m2")
    if isinstance(ppm2, int | float) and ppm2 > 0:
        return float(ppm2)

    price = listing.get("price")
    area = listing.get("area_m2")
    if isinstance(price, int | float) and isinstance(area, int | float) and price > 0 and area > 0:
        return float(price) / float(area)

    return None


def find_comparables(
    target: dict[str, Any],
    listings: list[dict[str, Any]],
    max_results: int = 5,
    area_tol_pct: float = 0.25,
    price_tol_pct: float = 0.30,
) -> list[dict[str, Any]]:
    """Find comparable listings for ``target`` among ``listings``.

    A candidate qualifies as a comparable when it:
      - is in the same neighborhood as ``target`` (case-insensitive, trimmed),
      - is not the target itself (different ``id``),
      - has ``status == "active"`` and ``excluded is False``,
      - has an area within ``area_tol_pct`` of the target's area, and
      - has a price within ``price_tol_pct`` of the target's price.

    Results are sorted by similarity: closest price-per-m2 to the target
    first, ties broken by closest area. At most ``max_results`` are returned.

    Each returned dict is a shallow copy of the comparable's own dict with an
    added ``ppm2_delta_pct`` key: the comparable's EUR/m2 relative to the
    target's, as a signed percent (negative means cheaper per m2 than the
    target). It is ``None`` when either ppm2 is unavailable.

    Fails soft: returns ``[]`` for any target that lacks a neighborhood, a
    positive price, or a computable area/ppm2. Never raises.
    """
    try:
        target_neighborhood = _normalized_neighborhood(target.get("neighborhood"))
        if target_neighborhood is None:
            return []

        target_price = target.get("price")
        if not isinstance(target_price, int | float) or target_price <= 0:
            return []

        target_area = target.get("area_m2")
        if not isinstance(target_area, int | float) or target_area <= 0:
            return []

        target_ppm2 = _ppm2(target)
        if target_ppm2 is None:
            return []

        target_id = target.get("id")

        candidates: list[tuple[float, float, dict[str, Any]]] = []
        for listing in listings:
            if listing.get("id") == target_id:
                continue
            if listing.get("status") != "active":
                continue
            if listing.get("excluded") is not False:
                continue

            neighborhood = _normalized_neighborhood(listing.get("neighborhood"))
            if neighborhood is None or neighborhood != target_neighborhood:
                continue

            price = listing.get("price")
            area = listing.get("area_m2")
            if not isinstance(price, int | float) or price <= 0:
                continue
            if not isinstance(area, int | float) or area <= 0:
                continue

            if abs(area - target_area) / target_area > area_tol_pct:
                continue
            if abs(price - target_price) / target_price > price_tol_pct:
                continue

            comp_ppm2 = _ppm2(listing)
            ppm2_delta_pct = (
                (comp_ppm2 - target_ppm2) / target_ppm2 * 100 if comp_ppm2 is not None else None
            )

            ppm2_rank = abs(comp_ppm2 - target_ppm2) if comp_ppm2 is not None else float("inf")
            area_rank = abs(area - target_area)

            result = dict(listing)
            result["ppm2_delta_pct"] = ppm2_delta_pct
            candidates.append((ppm2_rank, area_rank, result))

        candidates.sort(key=lambda c: (c[0], c[1]))

        if max_results < 0:
            max_results = 0

        return [result for _, _, result in candidates[:max_results]]
    except Exception:
        return []
