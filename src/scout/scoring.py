"""Scoring engine — the brain.

Pure and fully unit-tested. It NEVER reaches into the DB: ``market_stats`` is
computed elsewhere and passed in. Driven entirely by ``strategy.yaml`` so the
investor can tune weights and thresholds without touching code.

Flow (spec §7):
1. Hard filters -> excluded listings get score 0 and a reason.
2. Each signal normalized to 0..1, multiplied by its weight, summed to 0..100.
3. Opportunity flag set when EUR/m2 < pct * neighborhood median.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field

from .config import Strategy
from .models import Listing, ScoredListing

# Below this many price samples a neighborhood median is statistically meaningless
# (with 1 sample it equals the listing's own €/m², so the signal is always ~0).
_MIN_NEIGHBORHOOD_SAMPLES = 3


@dataclass
class NeighborhoodStats:
    median_price_per_m2: float | None = None
    median_rent_per_m2: float | None = None
    price_sample_count: int = 0


@dataclass
class MarketStats:
    """Per-neighborhood medians, computed from the DB each run and passed in."""

    by_neighborhood: dict[str, NeighborhoodStats] = field(default_factory=dict)
    overall_median_price_per_m2: float | None = None

    def price_per_m2_median_for(self, neighborhood: str | None) -> float | None:
        # Use the neighborhood median only when it rests on enough samples; small
        # sub-neighborhoods otherwise compare a listing against (mostly) itself.
        if neighborhood and neighborhood in self.by_neighborhood:
            ns = self.by_neighborhood[neighborhood]
            if ns.median_price_per_m2 is not None and (
                ns.price_sample_count >= _MIN_NEIGHBORHOOD_SAMPLES
            ):
                return ns.median_price_per_m2
        return self.overall_median_price_per_m2


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_market_stats(listings: Iterable[Listing]) -> MarketStats:
    """Compute per-neighborhood median EUR/m2 and median rent EUR/m2."""
    buckets: dict[str, list[float]] = {}
    rent_buckets: dict[str, list[float]] = {}
    all_ppm2: list[float] = []

    for lst in listings:
        ppm2 = lst.price_per_m2
        if ppm2 is None and lst.area_m2:
            ppm2 = lst.price / lst.area_m2
        if ppm2 and ppm2 > 0:
            all_ppm2.append(ppm2)
            if lst.neighborhood:
                buckets.setdefault(lst.neighborhood, []).append(ppm2)

        # Rent comps: only listings with a known rent contribute.
        rent = lst.listed_rent or lst.est_monthly_rent
        if rent and lst.area_m2 and lst.neighborhood:
            rent_buckets.setdefault(lst.neighborhood, []).append(rent / lst.area_m2)

    by_n: dict[str, NeighborhoodStats] = {}
    for n, vals in buckets.items():
        by_n[n] = NeighborhoodStats(
            median_price_per_m2=statistics.median(vals), price_sample_count=len(vals)
        )
    for n, vals in rent_buckets.items():
        by_n.setdefault(n, NeighborhoodStats()).median_rent_per_m2 = statistics.median(vals)

    overall = statistics.median(all_ppm2) if all_ppm2 else None
    return MarketStats(by_neighborhood=by_n, overall_median_price_per_m2=overall)


def _excluded(listing: Listing, reason: str) -> ScoredListing:
    return ScoredListing(listing=listing, score=0.0, excluded=True, exclusion_reason=reason)


def _yield_signal(listing: Listing, strategy: Strategy) -> float:
    if not listing.gross_yield:
        return 0.0
    ref = strategy.scoring_reference
    span = max(ref.yield_ceiling - ref.yield_floor, 1e-9)
    return _clamp01((listing.gross_yield - ref.yield_floor) / span)


def _price_vs_median_signal(listing: Listing, median_ppm2: float | None) -> float:
    """1.0 when much cheaper than the neighborhood median, 0 when at/above it."""
    ppm2 = listing.price_per_m2
    if ppm2 is None and listing.area_m2:
        ppm2 = listing.price / listing.area_m2
    if not ppm2 or not median_ppm2:
        return 0.0
    # ratio < 1 means cheaper; map [0.7 .. 1.0] -> [1 .. 0].
    ratio = ppm2 / median_ppm2
    return _clamp01((1.0 - ratio) / 0.3)


def _price_drop_signal(listing: Listing, first_price: int | None, strategy: Strategy) -> float:
    if not first_price or first_price <= 0 or listing.price >= first_price:
        return 0.0
    drop_pct = (first_price - listing.price) / first_price
    return _clamp01(drop_pct / max(strategy.scoring_reference.max_price_drop_pct, 1e-9))


def score(
    listing: Listing,
    market_stats: MarketStats,
    strategy: Strategy,
    first_price: int | None = None,
) -> ScoredListing:
    """Score a single listing. ``first_price`` enables the price-drop signal."""
    # 1. Hard filters.
    # Only exclude when the floor is KNOWN to be too low. An unknown floor (the portal
    # didn't report one) must not be treated as a basement and silently dropped — same
    # reasoning as the unknown-metro-distance case below; otherwise a portal that never
    # reports floor has every one of its listings wrongly excluded.
    if listing.floor is not None and listing.floor < strategy.hard_filters.min_floor:
        return _excluded(listing, "ground/low floor")
    metro = listing.metro_distance_m
    # Only exclude when we KNOW it's too far. Unknown distance (geocoding
    # unavailable) must not silently drop the listing under a false "too far"
    # reason — that empties the whole dashboard whenever geocoding hiccups. Such
    # listings are kept and surfaced with metro shown as unknown for the user to verify.
    if metro is not None and metro > strategy.hard_filters.max_metro_distance_m:
        return _excluded(listing, "too far from metro")

    # 2. Weighted, normalized signals.
    median_ppm2 = market_stats.price_per_m2_median_for(listing.neighborhood)
    signals = {
        "gross_yield": _yield_signal(listing, strategy),
        "price_vs_area_median": _price_vs_median_signal(listing, median_ppm2),
        "price_drop": _price_drop_signal(listing, first_price, strategy),
        "is_currently_rented": 1.0 if listing.is_currently_rented else 0.0,
        "is_private_seller": 1.0 if listing.is_private_seller else 0.0,
    }
    w = strategy.weights
    weights = {
        "gross_yield": w.gross_yield,
        "price_vs_area_median": w.price_vs_area_median,
        "price_drop": w.price_drop,
        "is_currently_rented": w.is_currently_rented,
        "is_private_seller": w.is_private_seller,
    }
    total_weight = w.total() or 1.0
    raw = sum(signals[k] * weights[k] for k in signals)
    final = raw / total_weight * 100.0

    # 3. Opportunity flag.
    is_opp = False
    ppm2 = listing.price_per_m2 or (listing.price / listing.area_m2 if listing.area_m2 else None)
    if ppm2 and median_ppm2:
        threshold = strategy.opportunity_flag.price_per_m2_below_median_pct * median_ppm2
        is_opp = ppm2 < threshold

    return ScoredListing(
        listing=listing,
        score=round(final, 2),
        excluded=False,
        is_opportunity=is_opp,
        signals=signals,
    )
