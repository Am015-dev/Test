"""Drive a full all-Athens XE collection, one area at a time, with progress logs.

XE only (Green-Acres is scraped once by the normal pipeline; re-running it per area would
be 37× wasted fetches). Each area runs the pipeline scoped to itself, tagged with its
region. XE rate-limits per IP — ~3 rapid result pages then a temporary 403 — so page
requests are spaced (set SCRAPE_REQUEST_MIN_S/MAX_S higher) to go deeper before a block;
a blocked area simply stops early and the sweep moves on. Idempotent and resumable.
"""

from __future__ import annotations

import logging
import sys
import time

from scout.collectors.xe import XeCollector
from scout.config import load_strategy
from scout.pipeline import run
from scout.regions import REGIONS, region_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collect_all")


def main() -> None:
    strategy = load_strategy()
    areas = strategy.search.all_areas()
    log.info("collecting %d areas across %d regions (XE only)", len(areas), len(REGIONS))
    grand = 0
    for i, area in enumerate(areas, 1):
        t0 = time.time()
        try:
            area_strategy = strategy.model_copy(deep=True)
            area_strategy.search.municipality = area
            # XE only, scoped to this one area (no per-area Green-Acres re-scrape).
            summary = run(
                strategy=area_strategy,
                collectors=[XeCollector(area_strategy)],
                area=area,
            )
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
