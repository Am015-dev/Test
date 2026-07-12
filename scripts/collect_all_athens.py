"""Drive a full all-Athens collection, one region/area at a time, with progress logs.

Runs the pipeline per area (so a slow/blocked area can't stall the rest), tags each with
its region, and prints a running tally. Cached detail pages make re-runs fast; new deep
pages are fetched politely. Safe to interrupt and resume — each area is independent and
idempotent.
"""

from __future__ import annotations

import logging
import sys
import time

from scout.config import load_strategy
from scout.pipeline import run_for_area
from scout.regions import REGIONS, region_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collect_all")


def main() -> None:
    strategy = load_strategy()
    areas = strategy.search.all_areas()
    log.info("collecting %d areas across %d regions", len(areas), len(REGIONS))
    grand = 0
    for i, area in enumerate(areas, 1):
        t0 = time.time()
        try:
            summary = run_for_area(area, strategy=strategy)
            grand += summary.get("stored", 0)
            log.info(
                "[%d/%d] %s (%s): %s in %.0fs — grand stored=%d",
                i,
                len(areas),
                area,
                region_of(area),
                summary,
                time.time() - t0,
                grand,
            )
        except Exception as exc:  # one area must never stop the sweep
            log.warning("[%d/%d] %s FAILED: %s", i, len(areas), area, exc)
        sys.stdout.flush()
    log.info("ALL-ATHENS COLLECTION DONE — grand stored=%d", grand)


if __name__ == "__main__":
    main()
