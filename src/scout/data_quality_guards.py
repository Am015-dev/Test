"""Data-quality guards — keep DATA ERRORS out of the top of the ranking.

The ranking's credibility dies the moment a whole apartment building priced as one flat
(€833/m², "12.8% yield", "49% under fair value") sits at #1. Those are not cheap
opportunities — they're artifacts of bad data: a Πολυκατοικία measured as a single unit,
a future build year, a €/m² off by 10x. This module FLAGS such listings so the UI can
demote and badge them (never delete — a human still verifies on the portal).

Pure functions over a listing dict (the shape from ``ui.queries._row_to_dict``). No DB,
no Streamlit. Each guard returns a short reason string or ``None``; ``data_quality_flags``
aggregates them and ``is_suspect`` is simply "any guard fired".

Thresholds were calibrated from the live active set (17,953 non-excluded listings, 2026-07;
€/m² p1≈1,000 / p50≈3,050 / p99.9≈8,400, area p99.9≈460 m², gross-yield p99≈11%). Each is a
heuristic band, not a law — see the ``# ponytail:`` notes for the ceiling and when to move it.
"""

from __future__ import annotations

from datetime import datetime

# Apartment-BUILDING / building words in a title. A "Πολυκατοικία" (apartment block) or
# "Κτίριο" (building) priced and measured as ONE unit produces a fake €/m² and yield — the
# exact artifact that topped the ranking. Deliberately NOT here: "Μονοκατοικία" (a detached
# house) and "Μεζονέτα" (maisonette) — those ARE single dwellings and legitimately large, so
# they only fire via the area / €-per-m² guards below, never on the word alone (avoids
# flagging every one of the ~330 real detached houses).
_BUILDING_WORDS = ("πολυκατοικ", "κτίριο", "κτιριο", "building", "polykatoik")

# A flat above this is almost always a whole building or a mis-parsed area (live p99.9 ≈
# 460 m²; genuine flats sit well under it).
# ponytail: flat ceiling; a real 450 m² penthouse is rarer than a mis-listed building — raise
# only if such listings start appearing.
_MAX_FLAT_AREA_M2 = 400.0

# "Big AND very cheap per m²" = the whole-building tell: a 250 m²+ place under €1,000/m² in
# Athens is a building/plot/ruin, not a bargain flat. BOTH conditions are required so a normal
# large flat (250 m² @ €3,000/m²) and a normal cheap small flat (60 m² @ €900/m²) don't fire.
_BIG_AREA_M2 = 250.0
_CHEAP_PPM2 = 1_000.0

# Sane Athens residential €/m² band. Live set spans ~€1,000 (p1) to ~€8,400 (p99.9); outside
# this it's a data error (a dropped digit, or a building/plot priced as a flat).
_PPM2_MIN = 400.0
_PPM2_MAX = 12_000.0

# Sane gross/net yield band for Athens residential. Real yields top out ~11% (p99); above 15%
# means a broken rent or price, below 0.5% is a mis-parse.
# ponytail: yield cap; raise if genuine >15% deals ever appear (none in 17,953 rows today).
_YIELD_MAX = 0.15
_YIELD_MIN = 0.005


def _ppm2(listing: dict) -> float | None:
    """The listing's €/m², preferring the stored value and falling back to price/area."""
    ppm2 = listing.get("price_per_m2")
    if ppm2 is None:
        price, area = listing.get("price"), listing.get("area_m2")
        if price and area:
            ppm2 = price / area
    return ppm2


def whole_building_flag(listing: dict) -> str | None:
    """Fires when the listing is (or looks like) a whole building priced as one flat."""
    title = (listing.get("title") or "").lower()
    if any(w in title for w in _BUILDING_WORDS):
        return "titled as a building, not a flat — its €/m² and yield are for the whole block"
    area = listing.get("area_m2")
    if area and area > _MAX_FLAT_AREA_M2:
        return f"{area:.0f} m² is too large for a flat — likely a whole building"
    ppm2 = _ppm2(listing)
    if area and ppm2 and area > _BIG_AREA_M2 and ppm2 < _CHEAP_PPM2:
        return "large and very cheap per m² — likely a whole building priced as one unit"
    return None


def future_year_flag(listing: dict, current_year: int | None = None) -> str | None:
    """Fires when a build/renovation year is in the future (a data error — the YEAR is wrong)."""
    current_year = current_year or datetime.utcnow().year
    for field in ("year_built", "renovated_year"):
        y = listing.get(field)
        if y and y > current_year:
            return f"{field.replace('_', ' ')} {y} is in the future — data error"
    return None


def implausible_yield_flag(listing: dict) -> str | None:
    """Fires when gross or net yield is outside a sane band (broken rent or price)."""
    for field in ("gross_yield", "net_yield"):
        y = listing.get(field)
        if y is not None and (y > _YIELD_MAX or y < _YIELD_MIN):
            return f"{y * 100:.1f}% {field.replace('_', ' ')} looks wrong for Athens residential"
    return None


def implausible_ppm2_flag(listing: dict) -> str | None:
    """Fires when €/m² is outside the plausible Athens residential range."""
    ppm2 = _ppm2(listing)
    if ppm2 is not None and (ppm2 < _PPM2_MIN or ppm2 > _PPM2_MAX):
        return f"€{ppm2:,.0f}/m² is outside the plausible range — verify area and price"
    return None


_GUARDS = (whole_building_flag, future_year_flag, implausible_yield_flag, implausible_ppm2_flag)


def data_quality_flags(listing: dict) -> list[str]:
    """Every data-quality reason that fired for this listing (empty = looks clean)."""
    return [reason for guard in _GUARDS if (reason := guard(listing)) is not None]


def is_suspect(listing: dict) -> bool:
    """True when any guard fired — the listing should be demoted from the top and badged."""
    return bool(data_quality_flags(listing))


def clean_future_years(
    year_built: int | None,
    renovated_year: int | None,
    current_year: int | None = None,
) -> tuple[int | None, int | None]:
    """Return (year_built, renovated_year) with any FUTURE value nulled.

    A future build/reno year is a data error — the YEAR is wrong, not the listing — so it
    must not feed valuation/scoring or be shown as-is. The future-year FLAG is raised
    separately by ``future_year_flag`` so the listing is still surfaced as suspect."""
    current_year = current_year or datetime.utcnow().year

    def _keep(y: int | None) -> int | None:
        return y if (y is None or y <= current_year) else None

    return _keep(year_built), _keep(renovated_year)


def _demo() -> None:
    """Runnable self-check (ponytail: the guard's one runnable proof)."""
    whole = {
        "title": "Πολυκατοικία 300 τ.μ.",
        "area_m2": 300,
        "price": 250_000,
        "price_per_m2": 833.33,
        "gross_yield": 0.128,
    }
    assert is_suspect(whole) and whole_building_flag(whole)
    normal = {
        "title": "Διαμέρισμα 85 τ.μ.",
        "area_m2": 85,
        "price": 250_000,
        "price_per_m2": 2941,
        "gross_yield": 0.042,
        "year_built": 2005,
    }
    assert not is_suspect(normal), data_quality_flags(normal)
    assert future_year_flag({"year_built": 2028}, current_year=2026)
    assert future_year_flag({"year_built": 2026}, current_year=2026) is None
    assert implausible_yield_flag({"gross_yield": 0.69})
    assert implausible_ppm2_flag({"price_per_m2": 300})
    assert clean_future_years(2028, 2020, current_year=2026) == (None, 2020)
    print("data_quality_guards self-check ok")


if __name__ == "__main__":
    _demo()
