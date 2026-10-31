"""Real rental comparables → median €/m²/month per neighbourhood.

The gross-yield signal is only honest if the rent estimate is real. Scraping the
actual rental listings for an area and taking the median €/m²/month per
sub-neighbourhood replaces the flat ``est_rent_eur_per_m2`` guess, so yield reflects
the local market (Kifisia ≠ Metamorfosi, and a €24/m² micro-area ≠ a €9/m² one).

The medians are computed by pure functions (no DB, no network). Since rentals became
first-class ``listing`` rows (``listing_type="rent"``), the pipeline recomputes an area's
comps every run from the rentals stored in the last ``WINDOW_DAYS`` days
(``recompute_from_stored``), and stamps each row with ``samples`` and ``updated_at`` (the
newest sighting it rests on), so the UI can print ``basis_text`` — «ενοίκια έως 31/10,
42 αγγελίες» — next to every yield.
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
# Rentals older than this (by last sighting) no longer count towards the comps.
WINDOW_DAYS = 60


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
    area: str,
    comps: dict[str, float],
    samples: dict[str, int] | None = None,
    updated_at=None,
) -> int:
    """Upsert an area's neighbourhood + overall rent medians into ``rent_comp``. The
    area-wide overall is stored with ``neighborhood=None``. ``updated_at`` defaults to now.
    Rows not in ``comps`` are left as they are: their own older ``updated_at`` tells the UI
    how old they are. Returns rows written."""
    from datetime import datetime

    from sqlalchemy import select

    from .db import session_scope
    from .models import RentCompRow

    samples = samples or {}
    written = 0
    now = updated_at or datetime.utcnow()
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


# ---- recompute from stored rentals + the basis line the UI prints ---------


def recompute_from_stored(area: str, now=None, window_days: int = WINDOW_DAYS) -> dict[str, float]:
    """Recompute and persist ``area``'s comps from the rentals stored in the ``listing``
    table (``listing_type='rent'``, last seen within ``window_days`` of ``now``, active or
    gone: an asking rent from three weeks ago is still a market data point). ``updated_at``
    is the newest sighting among them. Returns the comps; ``{}`` (and nothing written) when
    the area has no recent rentals, so earlier comps are never wiped by an empty run."""
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from .db import session_scope
    from .models import ListingRow

    now = now or datetime.utcnow()
    since = now - timedelta(days=window_days)
    with session_scope() as session:
        found = session.execute(
            select(
                ListingRow.price, ListingRow.area_m2, ListingRow.neighborhood, ListingRow.last_seen
            ).where(
                ListingRow.listing_type == "rent",
                ListingRow.search_area == area,
                ListingRow.last_seen >= since,
            )
        ).all()
    rows = [{"rent": p, "area_m2": a, "neighborhood": h} for p, a, h, _ in found]
    comps, counts = compute_rent_comps_with_counts(rows)
    if not comps:
        return {}
    newest = max(seen for *_, seen in found if seen is not None)
    save_rent_comps(area, comps, counts, updated_at=newest)
    return comps


def basis_text(updated_at, samples: int | None) -> str:
    """«ενοίκια έως 31/10, 42 αγγελίες» — the date and count a rent median rests on.
    "" when either is unknown (the caller then says the rent is an estimate without
    a basis rather than inventing one)."""
    if updated_at is None or not samples:
        return ""
    noun = "αγγελία" if samples == 1 else "αγγελίες"
    return f"ενοίκια έως {updated_at:%d/%m}, {samples} {noun}"


def comp_basis(comp_rows: list[dict], area: str | None, neighborhood: str | None) -> str:
    """``basis_text`` for the comp a listing's rent estimate uses: its neighbourhood's row
    when one exists, else the area-wide row. ``comp_rows`` is
    ``queries.load_rent_comp_rows()``."""
    area_rows = [r for r in comp_rows if r.get("area") == area]
    row = next(
        (r for r in area_rows if neighborhood and r.get("neighborhood") == neighborhood), None
    )
    row = row or next((r for r in area_rows if r.get("neighborhood") is None), None)
    if row is None:
        return ""
    return basis_text(row.get("updated_at"), row.get("samples"))
