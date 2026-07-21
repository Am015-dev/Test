"""Investor STRATEGY tags for a listing — the "how would I play this?" layer.

The deal grade (``investment.deal_grade``) answers *how good* a listing is; this answers
*what kind of play* it is, so the UI can group inventory by the thesis an investor would
actually pursue: buy for the rent (Cashflow), buy to renovate (Value-add), buy the
mispricing (Underpriced), lean on a motivated seller, or buy the location.

Pure and DB-free: it takes the same plain dict the UI builds in
``ui/queries._row_to_dict`` and returns zero or more tags. Thresholds are deliberately the
SAME Athens-calibrated cut-offs used elsewhere (``metrics.CAP_RATE_GOOD`` = 0.045 net,
``investment.deal_grade``'s 0.10 value gap / 45 negotiation score, ``scoring``'s energy
scale and pre-1990 "Dated" boundary) so a tag never contradicts the grade beside it.
"""

from __future__ import annotations

from collections.abc import Callable

# Strong NET yield: same bar as metrics.CAP_RATE_GOOD / deal_grade's yield point.
_CASHFLOW_NET_YIELD = 0.045
# Honest market-position rank (relative_value): "Underpriced" = the cheapest ~10% per m²
# among comparable active listings. Kept below the 20% deal-label line so it stays a
# meaningful minority, not an "everything is a deal" tag.
_UNDERPRICED_PERCENTILE = 0.90  # cheaper per m² than >=90% of comparable listings (top ~10%)
# Motivation: same negotiation-score bar as deal_grade; stale = 6 months on market.
_MOTIVATED_NEGOTIATION = 45.0
_MOTIVATED_DAYS = 180
# Renovation upside: energy worse than C, or built before the modern-code era.
_OLD_BUILD_YEAR = 1990
# Prime: exact location within a short walk of a metro station.
_PRIME_METRO_M = 500

# Energy classes D/E/F/G (Greek Δ/Ε/Ζ/Η, + Latin H alias) — the EPBD renovation-mandate
# band, mirroring scoring._ENERGY_SCORE. Kept as an explicit set so an UNKNOWN class (which
# scores 0.0, same as G) is never mistaken for a poor one.
_POOR_ENERGY = {"D", "Δ", "E", "Ε", "F", "Ζ", "G", "Η", "H"}

STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "Cashflow": "Strong real net yield — buy it for the rent it throws off.",
    "Value-add": "Poor energy or old un-renovated stock — renovation upside (EU EPBD).",
    "Underpriced": "Cheaper per m² than most comparable active listings for sale.",
    "Motivated seller": "Negotiable seller or long time on market — room to bargain.",
    "Prime location": "Exact address within a short walk of a metro station.",
}


def _num(value) -> float | None:
    """Best-effort numeric coercion; None/blank/garbage -> None (never raises)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_cashflow(d: dict) -> bool:
    """Strong NET yield backed by a REAL rent comp. An imputed/estimated rent makes the
    yield a deterministic inverse of €/m² (see scoring), so it must not earn a cashflow
    thesis — that's the "fake yield" trap."""
    if d.get("rent_estimated"):
        return False
    net = _num(d.get("net_yield"))
    return net is not None and net >= _CASHFLOW_NET_YIELD


def _is_value_add(d: dict) -> bool:
    """Renovation upside: a poor (D–G) energy class OR pre-1990 stock — but only when it
    hasn't ALREADY been renovated, since the upside is exactly the renovation still to do."""
    if d.get("renovated_year"):
        return False
    poor_energy = (d.get("energy_class") or "").strip().upper() in _POOR_ENERGY
    year = _num(d.get("year_built"))
    old_build = year is not None and year < _OLD_BUILD_YEAR
    return poor_energy or old_build


def _is_underpriced(d: dict) -> bool:
    """Cheaper per m² than most COMPARABLE ACTIVE listings — an honest market-position rank
    (relative_value.value_percentile), not an asking-vs-asking "below the model's fair value"
    claim. Falls back to nothing when the percentile is absent (needs the pool to annotate)."""
    vp = _num(d.get("value_percentile"))
    return vp is not None and vp >= _UNDERPRICED_PERCENTILE


def _is_motivated(d: dict) -> bool:
    """A negotiable seller or a listing that's been sitting long enough to soften."""
    neg = _num(d.get("negotiation_score"))
    if neg is not None and neg >= _MOTIVATED_NEGOTIATION:
        return True
    days = _num(d.get("days_on_market"))
    return days is not None and days >= _MOTIVATED_DAYS


def _is_prime_location(d: dict) -> bool:
    """Exact-located within a short walk of metro. A centroid-only ("exact" not set)
    distance is one value for a whole municipality, so it can't earn this per-listing tag."""
    if d.get("location_precision") != "exact":
        return False
    metro = _num(d.get("metro_distance_m"))
    return metro is not None and metro <= _PRIME_METRO_M


# Evaluated in this order so the returned list reads consistently across listings.
_TAGGERS: tuple[tuple[str, Callable[[dict], bool]], ...] = (
    ("Cashflow", _is_cashflow),
    ("Value-add", _is_value_add),
    ("Underpriced", _is_underpriced),
    ("Motivated seller", _is_motivated),
    ("Prime location", _is_prime_location),
)


def strategy_tags(d: dict) -> list[str]:
    """Classify a listing dict into zero or more investor strategy tags.

    Ordered (see ``_TAGGERS``), deduped, and total — a malformed/empty dict yields ``[]``
    rather than raising, so the UI can call it on any row unconditionally.
    """
    if not isinstance(d, dict):
        return []
    tags: list[str] = []
    for tag, predicate in _TAGGERS:
        try:
            if predicate(d) and tag not in tags:
                tags.append(tag)
        except Exception:
            # A single bad field must never sink the whole classification.
            continue
    return tags
