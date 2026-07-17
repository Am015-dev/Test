"""Scrape-health monitor — catch a silently-broken scrape before it rots the data.

A scrape can "succeed" (no crash) yet return nothing for an area (rate-limited, markup
changed, geo id broke). Left unwatched, the dashboard slowly goes stale while looking fine.
This inspects the DB freshness per area and flags problems, so the daily run can alert.

Pure-ish: reads listing dicts (or the DB) and returns a structured report; no writes.
"""

from __future__ import annotations

from datetime import datetime

# An area whose newest listing hasn't been refreshed in this many hours is "stale".
_STALE_HOURS = 48
# An area with fewer than this many active listings is "thin" (probably under-scraped).
_THIN_MIN = 20


def check(listings: list[dict] | None = None) -> dict:
    """Return {healthy: bool, issues: [...], areas: {area: {...}}} over active listings."""
    if listings is None:
        from .ui.queries import load_listings

        listings = [d for d in load_listings(only_active=True)]

    now = datetime.utcnow()
    by_area: dict[str, list[dict]] = {}
    for d in listings:
        by_area.setdefault(d.get("search_area") or "—", []).append(d)

    areas: dict[str, dict] = {}
    issues: list[str] = []
    for area, ds in by_area.items():
        newest = max((d["last_seen"] for d in ds if d.get("last_seen")), default=None)
        stale_h = (now - newest).total_seconds() / 3600 if newest else None
        thin = len(ds) < _THIN_MIN
        stale = stale_h is not None and stale_h > _STALE_HOURS
        areas[area] = {
            "listings": len(ds),
            "stale_hours": round(stale_h, 1) if stale_h else None,
            "thin": thin,
            "stale": stale,
        }
        if stale:
            issues.append(f"{area}: not refreshed in {stale_h:.0f}h")
        if thin:
            issues.append(f"{area}: only {len(ds)} active listings")
    return {"healthy": not issues, "issues": issues, "areas": areas, "checked_at": now.isoformat()}
