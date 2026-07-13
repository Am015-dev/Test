"""One-off maintenance: re-place approx listings and recompute metro distance.

Two data bugs left ~a third of listings reading "0 m to metro" (provably false):

  1. Several MUNICIPALITY_CENTROIDS were set to the area's metro-station coordinate, so
     every card-only (approx-located) listing landed on the station → 0 m and every map
     dot piled onto the station. The centroids are now real town centres.
  2. A degenerate OSRM distance (0) was taken at face value (now guarded in nearest_metro).

This re-places every ``approx`` listing at its corrected centroid, then recomputes the
metro distance for all located listings using the offline haversine×detour estimate
(deterministic, no network) — the same honest area-level fallback the app surfaces.

Usage:
    python scripts/recompute_metro.py
"""

from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("recompute_metro")


def recompute() -> dict:
    from sqlalchemy import select

    from scout.db import init_db, session_scope
    from scout.enrich import municipality_centroid, nearest_metro, neighborhood_centroid
    from scout.models import ListingRow

    init_db()
    relocated = 0
    metro_fixed = 0
    scanned = 0
    with session_scope() as session:
        rows = session.scalars(select(ListingRow)).all()
        for r in rows:
            scanned += 1
            # 1. Re-anchor approx-located listings to the corrected centroid (neighborhood
            #    first, then municipality). Exact per-listing coordinates are left alone.
            if r.location_precision == "approx":
                lat, lng = neighborhood_centroid(r.neighborhood)
                if lat is None or lng is None:
                    lat, lng = municipality_centroid(r.search_area)
                if lat is not None and lng is not None and (lat, lng) != (r.lat, r.lng):
                    r.lat, r.lng = lat, lng
                    relocated += 1
            # 2. Recompute metro distance from the (possibly updated) point.
            if r.lat is not None and r.lng is not None:
                res = nearest_metro(r.lat, r.lng, use_osrm=False)
                if res.metro_distance_m is not None and res.metro_distance_m != r.metro_distance_m:
                    r.metro_distance_m = res.metro_distance_m
                    r.nearest_metro = res.nearest_metro
                    metro_fixed += 1
        session.commit()
    log.info(
        "recompute_metro: scanned=%d relocated=%d metro_fixed=%d", scanned, relocated, metro_fixed
    )
    return {"scanned": scanned, "relocated": relocated, "metro_fixed": metro_fixed}


if __name__ == "__main__":
    print(recompute())
