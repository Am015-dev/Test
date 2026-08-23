"""Honest relative-value signals — no sold-price data required, always area-scoped.

The hedonic "fair value" model rests on ASKING prices (Greece has no open sold register)
and carries a ±44% band, so "+49% under fair value" is pseudo-precise noise. This module
replaces it with statements that are simply TRUE: where does a listing's €/m² — and its
yield — sit among *comparable active listings for sale right now, in the same area*?

"Priced below 82% of similar flats currently for sale in this area" is not a claimed
discount or a valuation — it's the listing's rank in today's local asking market, which
is exactly what a buyer uses to judge whether a price is competitive.

Why area-scoped, always: a flat national yield threshold treats 5.5% as equally strong
everywhere, when 5.5% is exceptional in a prime low-yield neighborhood and mediocre in a
peripheral high-yield one. Comparing within the SAME local peer group (area + similar
floor size) is what makes both the price and yield percentiles honest — never against a
citywide blend. Pure function, no DB/network. Requires enough peers to be meaningful,
else returns None (never guesses).
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


def _yield(d: dict) -> float | None:
    """Net yield preferred (after Greek acquisition/holding costs — what the investor
    actually keeps); gross as a fallback. Mirrors scoring._yield_signal's preference
    order, so this indicator and the score/verdict never disagree about which number
    "the yield" means."""
    ny = d.get("net_yield")
    if isinstance(ny, (int, float)):
        return float(ny)
    gy = d.get("gross_yield")
    if isinstance(gy, (int, float)) and gy > 0:
        return float(gy)
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


@dataclass(frozen=True)
class RelativeYield:
    percentile: float  # 0..1 — fraction of comparable listings with a LOWER yield
    peers: int
    headline: str


def _annotate(listings: list[dict]) -> None:
    """Attach, per listing:
      - `value_percentile` / `value_peers` — share of comparable active listings (same
        area, floor area within ±30%) priced HIGHER per m² (so 0.82 => cheaper than 82%).
      - `yield_percentile` / `yield_peers` — among that SAME local peer group, the share
        with a LOWER yield (so 0.75 => a better yield than 75% of comparable listings
        here). Answers "is this yield good FOR THIS AREA", not against a flat national
        band — the gap the fixed BUY_YIELD/scoring-reference thresholds don't cover.

    Both percentiles share one area+size peer group (computed once) so a "peer" means
    the same thing for both signals, and adding the yield signal costs no extra O(n*k)
    pass beyond what was already needed for price."""
    by_area: dict[str, list[tuple[dict, float, float, float | None]]] = {}
    for d in listings:
        d["value_percentile"] = None
        d["value_peers"] = 0
        d["yield_percentile"] = None
        d["yield_peers"] = 0
        key = _area_key(d)
        ppm = _ppm2(d)
        area = d.get("area_m2")
        if key and ppm is not None and area:
            by_area.setdefault(key, []).append((d, ppm, float(area), _yield(d)))

    for group in by_area.values():
        for d, ppm, area, yld in group:
            lo, hi = area * (1 - SIZE_BAND), area * (1 + SIZE_BAND)
            n_price_peers = 0
            higher_price = 0
            n_yield_peers = 0
            lower_yield = 0
            for other, other_ppm, other_area, other_yld in group:
                if other is d or not (lo <= other_area <= hi):
                    continue
                n_price_peers += 1
                if other_ppm > ppm:
                    higher_price += 1
                if yld is not None and other_yld is not None:
                    n_yield_peers += 1
                    if other_yld < yld:
                        lower_yield += 1
            if n_price_peers >= MIN_PEERS:
                d["value_percentile"] = higher_price / n_price_peers
                d["value_peers"] = n_price_peers
            if yld is not None and n_yield_peers >= MIN_PEERS:
                d["yield_percentile"] = lower_yield / n_yield_peers
                d["yield_peers"] = n_yield_peers


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


def relative_yield(d: dict) -> RelativeYield | None:
    """Human-facing summary of how this listing's yield ranks among comparable active
    listings IN THE SAME AREA — answers "is this yield actually good here", since a flat
    national yield threshold treats every neighborhood as equally yield-rich. None when
    there's no usable yield or too few local peers with one to compare against."""
    pct = d.get("yield_percentile")
    peers = d.get("yield_peers") or 0
    if pct is None or peers < MIN_PEERS:
        return None
    share = round(pct * 100)
    if share >= 50:
        headline = f"Higher yield than {share}% of {peers} comparable listings here"
    else:
        headline = f"Lower yield than {100 - share}% of {peers} comparable listings here"
    return RelativeYield(pct, peers, headline)
