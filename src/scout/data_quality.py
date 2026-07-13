"""Data-quality audit — the "observe" step of the autonomous improvement loop.

Measures, from the live DB, how much the product actually KNOWS: field completeness,
per-region coverage, freshness, and where the ranking rests on complete vs. card-only data.
The improvement-loop skill reads this to decide what to fix next (deepen data, retry an area,
wire rent comps), and sellability-review uses it to keep the score honest.

Pure measurement — no writes, no scraping. Returns plain dicts so it's easy to print, test,
or serialise.
"""

from __future__ import annotations

from datetime import datetime

# Per-listing SCRAPE fields whose presence makes a listing "trustworthy enough to rank
# confidently" — matches the UI's "limited data" badge. Real rent is tracked separately
# below as a SYSTEMIC gap (it's market-wide, not a per-listing scrape miss).
_COMPLETENESS_FIELDS = ("energy_class", "year_or_reno", "exact_location")
_SYSTEMIC_FIELDS = ("real_rent",)


def _has(row: dict, field: str) -> bool:
    if field == "energy_class":
        return bool((row.get("energy_class") or "").strip())
    if field == "year_or_reno":
        return bool(row.get("year_built") or row.get("renovated_year"))
    if field == "exact_location":
        return row.get("location_precision") == "exact"
    if field == "real_rent":
        return not row.get("rent_estimated", True)
    return False


def audit(listings: list[dict] | None = None) -> dict:
    """Return a structured data-quality report over the active, non-excluded listings.

    Pass ``listings`` (UI-shaped dicts) to audit an in-memory set; omit to load from the DB.
    """
    if listings is None:
        from .ui.queries import load_listings

        listings = [d for d in load_listings(only_active=True) if not d.get("excluded")]

    n = len(listings)
    if not n:
        return {"total": 0, "fields": {}, "regions": {}, "top_gap": None}

    # Field-level completeness across the whole set (per-listing scrape fields + systemic).
    fields = {
        f: round(sum(1 for d in listings if _has(d, f)) / n, 3)
        for f in (*_COMPLETENESS_FIELDS, *_SYSTEMIC_FIELDS)
    }
    complete = sum(1 for d in listings if all(_has(d, f) for f in _COMPLETENESS_FIELDS))

    # Per-region coverage + freshness.
    regions: dict[str, dict] = {}
    now = datetime.utcnow()
    by_region: dict[str, list[dict]] = {}
    for d in listings:
        by_region.setdefault(d.get("region") or "—", []).append(d)
    for region, ds in by_region.items():
        m = len(ds)
        newest = max((d["last_seen"] for d in ds if d.get("last_seen")), default=None)
        regions[region] = {
            "listings": m,
            "energy_pct": round(sum(1 for d in ds if _has(d, "energy_class")) / m, 3),
            "exact_loc_pct": round(sum(1 for d in ds if _has(d, "exact_location")) / m, 3),
            "complete_pct": round(
                sum(1 for d in ds if all(_has(d, f) for f in _COMPLETENESS_FIELDS)) / m, 3
            ),
            "stale_days": (now - newest).days if newest else None,
        }

    # How much the RANKING rests on complete data (the number sellability cares about).
    top = sorted(listings, key=lambda d: d.get("score") or 0, reverse=True)[:100]
    top_complete = sum(1 for d in top if all(_has(d, f) for f in _COMPLETENESS_FIELDS))

    # The single lowest field — where the loop should invest next.
    top_gap = min(fields, key=fields.get) if fields else None

    return {
        "total": n,
        "complete": complete,
        "complete_pct": round(complete / n, 3),
        "fields": fields,
        "regions": regions,
        "top100_complete": top_complete,
        "top_gap": top_gap,
    }


def format_report(report: dict) -> str:
    """A compact human-readable summary of ``audit()`` for the skill / CLI."""
    if not report.get("total"):
        return "No active listings to audit."
    lines = [
        f"Data-quality audit — {report['total']} listings, "
        f"{report['complete_pct'] * 100:.0f}% fully complete "
        f"({report['top100_complete']}/100 of the top-ranked are complete).",
        "Field completeness: "
        + ", ".join(f"{k} {v * 100:.0f}%" for k, v in report["fields"].items()),
        f"Biggest gap → invest here next: **{report['top_gap']}**",
    ]
    return "\n".join(lines)
