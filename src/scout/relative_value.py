"""Honest relative-value signal — no sold-price data required.

The hedonic "fair value" model rests on ASKING prices (Greece has no open sold register)
and carries a ±44% band, so "+49% under fair value" is pseudo-precise noise. This module
replaces it with a statement that is simply TRUE: where does a listing's €/m² sit among
*comparable active listings for sale right now*?

"Priced below 82% of similar flats currently for sale in this area" is not a claimed
discount or a valuation — it's the listing's rank in today's asking market, which is
exactly what a buyer uses to judge whether a price is competitive. Pure function, no
DB/network. Requires enough peers to be meaningful, else returns None (never guesses).
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_PEERS = 8  # below this the percentile is noise — report nothing rather than mislead
SIZE_BAND = 0.30  # compare like-with-like: peers within ±30% floor area


def _ppm2(d: dict) -> float | None:
    v = d.get("price_per_m2")
    if isinstance(v, (int, float)) and v > 0:
        return float(v)
    price, area = d.get("price"), d.get("area_m2")
    if (
        isinstance(price, (int, float))
        and isinstance(area, (int, float))
        and price > 0
        and area > 0
    ):
        return price / area
    return None


def _area_key(d: dict) -> str | None:
    return d.get("search_area") or d.get("region") or d.get("neighborhood")


@dataclass(frozen=True)
class RelativeValue:
    percentile: (
        float  # 0..1 — fraction of comparable listings priced HIGHER per m² (cheaper=higher)
    )
    peers: int
    headline: str


def _annotate(listings: list[dict]) -> None:
    """Attach `value_percentile` (0..1 or None) and `value_peers` to each listing in place.
    Peers = active, same area, floor area within ±30%. Percentile = share of peers with a
    strictly higher €/m² (so 0.82 => cheaper than 82% of comparable listings for sale)."""
    # Bucket by area once so each listing is compared only within its local asking market.
    by_area: dict[str, list[dict]] = {}
    for d in listings:
        key = _area_key(d)
        if key and _ppm2(d) is not None and d.get("area_m2"):
            by_area.setdefault(key, []).append(d)

    for d in listings:
        d["value_percentile"] = None
        d["value_peers"] = 0
        key = _area_key(d)
        ppm = _ppm2(d)
        area = d.get("area_m2")
        if not key or ppm is None or not area:
            continue
        lo, hi = area * (1 - SIZE_BAND), area * (1 + SIZE_BAND)
        peers = [
            p
            for p in by_area.get(key, [])
            if p is not d and lo <= (p.get("area_m2") or 0) <= hi and _ppm2(p) is not None
        ]
        if len(peers) < MIN_PEERS:
            continue
        higher = sum(1 for p in peers if _ppm2(p) > ppm)  # peers more expensive per m²
        d["value_percentile"] = higher / len(peers)
        d["value_peers"] = len(peers)


def annotate_relative_value(listings: list[dict]) -> list[dict]:
    """Annotate and return the same list (convenience for call sites)."""
    _annotate(listings)
    return listings


def relative_value(d: dict) -> RelativeValue | None:
    """Human-facing summary for a single already-annotated listing, or None if too few peers."""
    pct = d.get("value_percentile")
    peers = d.get("value_peers") or 0
    if pct is None or peers < MIN_PEERS:
        return None
    share = round(pct * 100)
    if share >= 50:
        headline = f"Priced below {share}% of {peers} similar flats for sale here"
    else:
        headline = f"Priced above {100 - share}% of {peers} similar flats for sale here"
    return RelativeValue(pct, peers, headline)
