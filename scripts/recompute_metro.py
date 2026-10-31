"""One-off maintenance: recompute the nearest station for every listing with exact coordinates.

``nearest_metro`` / ``metro_distance_m`` were measured against the old Latin-named station list
(Line 2/3 only). The station table (``scout/stations.py``) now holds Lines 1–3 and the suburban
railway with Greek names. This script:

  * recomputes both fields for rows with ``location_precision = 'exact'`` (their own point);
  * only renames ``nearest_metro`` to the Greek label on ``approx`` rows (area-centroid points
    carry no real distance; the UI hides it) and leaves their stored distance alone.

Offline (haversine × detour, no OSRM), idempotent, cheap — run it after the collect step.

Usage:
    python scripts/recompute_metro.py [--dry-run]
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("recompute_metro")


def recompute(dry_run: bool = False) -> dict:
    from sqlalchemy import select

    from scout import stations
    from scout.db import init_db, session_scope
    from scout.enrich import nearest_metro
    from scout.models import ListingRow

    init_db()
    out = {
        "scanned": 0,
        "exact": 0,
        "station_changed": 0,  # a different station, not just its Greek name
        "distance_moved_25m": 0,
        "exact_changed": 0,  # any change at all, renames included
        "approx_renamed": 0,
    }
    with session_scope() as session:
        for r in session.scalars(select(ListingRow)).all():
            out["scanned"] += 1
            if r.location_precision == "exact" and r.lat is not None and r.lng is not None:
                out["exact"] += 1
                res = nearest_metro(r.lat, r.lng, use_osrm=False)
                if (res.nearest_metro, res.metro_distance_m) != (
                    r.nearest_metro,
                    r.metro_distance_m,
                ):
                    out["exact_changed"] += 1
                    out["station_changed"] += res.nearest_metro != stations.label(r.nearest_metro)
                    old = r.metro_distance_m
                    out["distance_moved_25m"] += (
                        old is None
                        or res.metro_distance_m is None
                        or abs(res.metro_distance_m - old) > 25
                    )
                    if not dry_run:
                        r.nearest_metro, r.metro_distance_m = (
                            res.nearest_metro,
                            res.metro_distance_m,
                        )
            elif r.nearest_metro:
                greek = stations.label(r.nearest_metro)
                if greek and greek != r.nearest_metro:
                    out["approx_renamed"] += 1
                    if not dry_run:
                        r.nearest_metro = greek
        if dry_run:
            session.rollback()
    log.info("recompute_metro%s: %s", " (dry run)" if dry_run else "", out)
    return out


if __name__ == "__main__":
    print(recompute(dry_run="--dry-run" in sys.argv))
