"""Collect only the areas with no/low data yet — the new municipalities + the ones that
were configured but never populated. Idempotent; skips per-area nothing."""

from __future__ import annotations

import logging
import time

from sqlalchemy import func, select

from scout.collectors.xe import XeCollector
from scout.config import load_strategy
from scout.db import init_db, session_scope
from scout.models import ListingRow
from scout.pipeline import run
from scout.regions import region_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collect_missing")


def main():
    init_db()
    strategy = load_strategy()
    with session_scope() as s:
        counts = dict(
            s.execute(
                select(ListingRow.search_area, func.count()).group_by(ListingRow.search_area)
            ).all()
        )
    # Areas with < 200 listings = missing or thin → collect them.
    targets = [a for a in strategy.search.all_areas() if counts.get(a, 0) < 200]
    log.info("collecting %d thin/missing areas: %s", len(targets), targets)
    grand = 0
    for i, area in enumerate(targets, 1):
        t0 = time.time()
        try:
            a_s = strategy.model_copy(deep=True)
            a_s.search.municipality = area
            # use_network=False → offline centroids + haversine metro (no per-listing OSRM
            # call), so a card-only breadth sweep runs in ~2 min/area, not ~11. A single
            # recompute_metro at the end fixes any distances.
            summary = run(
                strategy=a_s, collectors=[XeCollector(a_s)], area=area, use_network=False
            )
            grand += summary.get("stored", 0)
            log.info(
                "[%d/%d] %s (%s): %s in %.0fs grand=%d",
                i,
                len(targets),
                area,
                region_of(area),
                summary,
                time.time() - t0,
                grand,
            )
        except Exception as exc:
            log.warning("[%d/%d] %s FAILED: %s", i, len(targets), area, exc)
    log.info("DONE. grand stored=%d", grand)


if __name__ == "__main__":
    main()
