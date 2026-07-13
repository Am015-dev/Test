"""Real rental comparables → median €/m²/month per neighbourhood.

The gross-yield signal is only honest if the rent estimate is real. Scraping the
actual rental listings for an area and taking the median €/m²/month per
sub-neighbourhood replaces the flat ``est_rent_eur_per_m2`` guess, so yield reflects
the local market (Kifisia ≠ Metamorfosi, and a €24/m² micro-area ≠ a €9/m² one).

Pure function — no DB, no network. The collector supplies the rent rows.
"""

from __future__ import annotations

import statistics

# Sanity band for a residential monthly rent in €/m²/month: below/above this is a
# mis-parse (a sale price leaking in, or a garbage figure) and is dropped.
_MIN_RENT_PER_M2 = 3.0
_MAX_RENT_PER_M2 = 60.0
# A neighbourhood median needs at least this many samples to be trustworthy; otherwise
# the caller falls back to the area-wide median.
_MIN_SAMPLES = 3

OVERALL_KEY = "__overall__"


def compute_rent_comps(rent_rows: list[dict]) -> dict[str, float]:
    """Map neighbourhood → median €/m²/month from rental rows, plus an ``__overall__``
    area-wide median. Rows are ``{rent, area_m2, neighborhood}``; junk is skipped."""
    by_hood: dict[str, list[float]] = {}
    all_ppm: list[float] = []
    for row in rent_rows:
        rent = row.get("rent")
        area = row.get("area_m2")
        if not rent or not area or area <= 0:
            continue
        ppm = rent / area
        if not (_MIN_RENT_PER_M2 <= ppm <= _MAX_RENT_PER_M2):
            continue
        all_ppm.append(ppm)
        hood = row.get("neighborhood")
        if hood:
            by_hood.setdefault(hood, []).append(ppm)

    comps: dict[str, float] = {
        hood: statistics.median(vals) for hood, vals in by_hood.items() if len(vals) >= _MIN_SAMPLES
    }
    if all_ppm:
        comps[OVERALL_KEY] = statistics.median(all_ppm)
    return comps


def rent_for(comps: dict[str, float], neighborhood: str | None) -> float | None:
    """Best rent €/m²/month for a neighbourhood: its own median, else the area-wide
    median, else None (caller uses the configured flat baseline)."""
    if neighborhood and neighborhood in comps:
        return comps[neighborhood]
    return comps.get(OVERALL_KEY)


# ---- persistence (so a rescore can reuse comps without re-scraping) -------


def save_rent_comps(
    area: str, comps: dict[str, float], samples: dict[str, int] | None = None
) -> int:
    """Upsert an area's neighbourhood + overall rent medians into ``rent_comp``. The
    area-wide overall is stored with ``neighborhood=None``. Returns rows written."""
    from datetime import datetime

    from sqlalchemy import select

    from .db import session_scope
    from .models import RentCompRow

    samples = samples or {}
    written = 0
    now = datetime.utcnow()
    with session_scope() as session:
        for key, ppm in comps.items():
            hood = None if key == OVERALL_KEY else key
            row = session.scalar(
                select(RentCompRow).where(
                    RentCompRow.area == area,
                    (
                        RentCompRow.neighborhood.is_(hood)
                        if hood is None
                        else RentCompRow.neighborhood == hood
                    ),
                )
            )
            if row is None:
                row = RentCompRow(area=area, neighborhood=hood)
                session.add(row)
            row.rent_per_m2 = float(ppm)
            row.samples = int(samples.get(key, 0))
            row.updated_at = now
            written += 1
    return written


def load_rent_comps() -> dict[str, dict[str, float]]:
    """All persisted comps as ``{area: {neighbourhood|__overall__: €/m²/month}}``."""
    from sqlalchemy import select

    from .db import session_scope
    from .models import RentCompRow

    out: dict[str, dict[str, float]] = {}
    with session_scope() as session:
        for row in session.scalars(select(RentCompRow)).all():
            key = row.neighborhood or OVERALL_KEY
            out.setdefault(row.area, {})[key] = row.rent_per_m2
    return out


def compute_rent_comps_with_counts(
    rent_rows: list[dict],
) -> tuple[dict[str, float], dict[str, int]]:
    """Like ``compute_rent_comps`` but also returns per-key sample counts (for storage)."""
    by_hood: dict[str, list[float]] = {}
    all_ppm: list[float] = []
    for row in rent_rows:
        rent = row.get("rent")
        area = row.get("area_m2")
        if not rent or not area or area <= 0:
            continue
        ppm = rent / area
        if not (_MIN_RENT_PER_M2 <= ppm <= _MAX_RENT_PER_M2):
            continue
        all_ppm.append(ppm)
        hood = row.get("neighborhood")
        if hood:
            by_hood.setdefault(hood, []).append(ppm)
    comps: dict[str, float] = {}
    counts: dict[str, int] = {}
    for hood, vals in by_hood.items():
        if len(vals) >= _MIN_SAMPLES:
            comps[hood] = statistics.median(vals)
            counts[hood] = len(vals)
    if all_ppm:
        comps[OVERALL_KEY] = statistics.median(all_ppm)
        counts[OVERALL_KEY] = len(all_ppm)
    return comps, counts
