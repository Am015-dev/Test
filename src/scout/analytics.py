"""Market analytics over collections of listings.

Pure functions only — no DB, no network, no Streamlit. Everything here takes
plain listing dicts (or price-observation dicts) in and returns plain lists
of dicts out, so it is safe to call from the UI, the pipeline, or a test
without any side effects.

All functions FAIL SOFT: given empty, missing, or malformed input they return
``[]`` (or skip the offending record) rather than raising, so a batch of
listings with incomplete data simply produces thinner stats instead of
crashing the run.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any


def _positive_or_none(value: Any) -> float | None:
    """Return ``value`` as a float when it is a positive number, else ``None``."""

    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _median(values: list[float]) -> float | None:
    """``statistics.median`` over ``values``, or ``None`` when there are none."""

    if not values:
        return None
    return statistics.median(values)


def neighborhood_stats(listings: list[dict]) -> list[dict]:
    """Aggregate ``listings`` into per-neighborhood market stats.

    Listings whose ``neighborhood`` is falsy (``None``, ``""``, etc.) are
    skipped entirely — they cannot be attributed to a market.

    Returns a list of dicts, one per neighborhood, each with:
        - ``neighborhood``: str
        - ``count``: int — number of listings in the group
        - ``median_price``: float | None
        - ``median_ppm2``: float | None — median price per m2, falling back
          to ``price / area_m2`` for listings where ``price_per_m2`` is
          missing but ``area_m2`` is a positive number
        - ``median_yield_pct``: float | None — median gross yield, as a
          percentage (i.e. the fraction * 100)
        - ``opportunities``: int — count where ``is_opportunity`` is True
        - ``rented``: int — count where ``is_currently_rented`` is True

    Sorted by ``count`` descending, then ``neighborhood`` ascending.
    """

    if not listings:
        return []

    groups: dict[str, list[dict]] = defaultdict(list)
    for listing in listings:
        if not isinstance(listing, dict):
            continue
        neighborhood = listing.get("neighborhood")
        if not neighborhood:
            continue
        groups[neighborhood].append(listing)

    results: list[dict] = []
    for neighborhood, group in groups.items():
        prices = [
            p for listing in group if (p := _positive_or_none(listing.get("price"))) is not None
        ]

        ppm2_values: list[float] = []
        for listing in group:
            ppm2 = _positive_or_none(listing.get("price_per_m2"))
            if ppm2 is None:
                price = _positive_or_none(listing.get("price"))
                area = _positive_or_none(listing.get("area_m2"))
                if price is not None and area is not None:
                    ppm2 = price / area
            if ppm2 is not None:
                ppm2_values.append(ppm2)

        yield_values = [
            gy * 100
            for listing in group
            if (gy := _positive_or_none(listing.get("gross_yield"))) is not None
        ]

        opportunities = sum(1 for listing in group if listing.get("is_opportunity") is True)
        rented = sum(1 for listing in group if listing.get("is_currently_rented") is True)
        # Real deal-supply signals from data we already hold: flats sitting >180 days
        # (motivated sellers) and flats the model prices below fair value beyond its band.
        long_sitting = sum(1 for listing in group if (listing.get("days_on_market") or 0) > 180)
        below_model = sum(1 for listing in group if (listing.get("value_gap_pct") or 0) > 0)

        results.append(
            {
                "neighborhood": neighborhood,
                "count": len(group),
                "median_price": _median(prices),
                "median_ppm2": _median(ppm2_values),
                "median_yield_pct": _median(yield_values),
                "opportunities": opportunities,
                "long_sitting": long_sitting,
                "below_model": below_model,
                "rented": rented,
            }
        )

    results.sort(key=lambda r: (-r["count"], r["neighborhood"]))
    return results


def market_price_index(history: list[dict]) -> list[dict]:
    """Build a monthly market price index from flat price observations.

    ``history`` is a flat list of price-observation dicts (typically spanning
    many listings), each with ``observed_at: datetime`` and ``price: int``.
    Entries with a missing/non-positive ``price`` or missing ``observed_at``
    are skipped.

    Returns a time series sorted ascending by month, one dict per month with:
        - ``month``: str formatted "YYYY-MM"
        - ``median_price``: float
        - ``samples``: int — number of observations in that month
    """

    if not history:
        return []

    buckets: dict[str, list[float]] = defaultdict(list)
    for entry in history:
        if not isinstance(entry, dict):
            continue
        observed_at = entry.get("observed_at")
        if not isinstance(observed_at, datetime):
            continue
        price = _positive_or_none(entry.get("price"))
        if price is None:
            continue
        month = f"{observed_at.year:04d}-{observed_at.month:02d}"
        buckets[month].append(price)

    results = [
        {
            "month": month,
            "median_price": statistics.median(prices),
            "samples": len(prices),
        }
        for month, prices in buckets.items()
    ]
    results.sort(key=lambda r: r["month"])
    return results


def area_ppm2_distributions(listings: list[dict]) -> dict[str, list[float]]:
    """Sorted €/m² per municipality (``search_area``) — the distribution a listing's price
    percentile is read against. Only listings with a usable €/m² contribute."""
    from collections import defaultdict

    buckets: dict[str, list[float]] = defaultdict(list)
    for d in listings:
        area = d.get("search_area")
        ppm2 = _positive_or_none(d.get("price_per_m2"))
        if area and ppm2:
            buckets[area].append(ppm2)
    return {a: sorted(v) for a, v in buckets.items()}


def ppm2_percentile_cheaper(ppm2: float | None, sorted_ppm2: list[float]) -> float | None:
    """Share of the area's listings this one is CHEAPER than, 0..1 (transparent, checkable).

    A value of 0.78 means "cheaper per m² than 78% of listings in this municipality" — an
    honest, portal-derivable value signal that works even for card-only listings with no
    hedonic model. Needs a few comps to be meaningful."""
    if not ppm2 or len(sorted_ppm2) < 5:
        return None
    dearer = sum(1 for v in sorted_ppm2 if v > ppm2)
    return round(dearer / len(sorted_ppm2), 3)
