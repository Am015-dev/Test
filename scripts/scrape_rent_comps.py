"""Scrape the RENTAL market per area → persist real €/m²/month comps.

The #1 data gap the audit flags: rent is 100% imputed (a flat baseline), so net yield is
just an inverse of €/m². This does a bounded rental sweep per area (card-only — the rent and
size are on the card, no detail fetch needed), computes the per-neighbourhood + area-wide
median €/m²/month, and stores it in ``rent_comp``. A rescore then applies real rent.

Fast and polite: rentals are a separate search (own rate-limit budget), card-only, adaptive
throttle. Resumable — re-running refreshes each area's comps.

Usage:
    SCRAPE_REQUEST_MIN_S=4 SCRAPE_REQUEST_MAX_S=7 python scripts/scrape_rent_comps.py
"""

from __future__ import annotations

import logging
import sys
import time

from scout.collectors.xe import XeCollector
from scout.config import load_strategy
from scout.db import init_db
from scout.rent_comps import compute_rent_comps_with_counts, save_rent_comps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rent_comps")


def main() -> None:
    init_db()
    strategy = load_strategy()
    areas = strategy.search.all_areas()
    log.info("scraping rental comps for %d areas", len(areas))
    grand = 0
    for i, area in enumerate(areas, 1):
        t0 = time.time()
        try:
            area_strategy = strategy.model_copy(deep=True)
            area_strategy.search.municipality = area
            collector = XeCollector(area_strategy)
            rows = list(collector.collect_rent_rows())
            comps, counts = compute_rent_comps_with_counts(rows)
            written = save_rent_comps(area, comps, counts) if comps else 0
            grand += written
            overall = comps.get("__overall__")
            log.info(
                "[%d/%d] %s: %d rental rows → %d comps (overall %.1f €/m²) in %.0fs",
                i,
                len(areas),
                area,
                len(rows),
                written,
                overall or 0.0,
                time.time() - t0,
            )
        except Exception as exc:  # one area must never stop the sweep
            log.warning("[%d/%d] %s FAILED: %s", i, len(areas), area, exc)
        sys.stdout.flush()
    log.info("RENT COMPS DONE — %d comp rows written", grand)


if __name__ == "__main__":
    main()
