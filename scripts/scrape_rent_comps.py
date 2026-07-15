"""Scrape the RENTAL market per area → persist real €/m²/month comps.

The #1 data gap the audit flags: rent is 100% imputed (a flat baseline), so net yield is
just an inverse of €/m². This does a bounded rental sweep per area (card-only — the rent and
size are on the card, no detail fetch needed), computes the per-neighbourhood + area-wide
median €/m²/month, and stores it in ``rent_comp``. A rescore then applies real rent.

Fast and polite: rentals are a separate search (own rate-limit budget), card-only, adaptive
throttle. Resumable — re-running refreshes each area's comps.

Usage:
    SCRAPE_REQUEST_MIN_S=4 SCRAPE_REQUEST_MAX_S=7 python scripts/scrape_rent_comps.py
    # only areas with no comps yet (top-up after expanding coverage):
    python scripts/scrape_rent_comps.py --only-missing
    # or an explicit subset:
    python scripts/scrape_rent_comps.py "Nea Ionia" "Vouliagmeni"
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from scout.collectors.xe import XeCollector
from scout.config import load_strategy
from scout.db import init_db
from scout.rent_comps import compute_rent_comps_with_counts, save_rent_comps

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rent_comps")


def _areas_without_comps(areas: list[str]) -> list[str]:
    """The configured areas that have no rent_comp rows yet — the top-up worklist."""
    from sqlalchemy import text

    from scout.db import session_scope

    with session_scope() as s:
        have = {r[0] for r in s.execute(text("select distinct area from rent_comp")).all()}
    return [a for a in areas if a not in have]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("areas", nargs="*", help="explicit area subset (default: all configured)")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="only areas with no rent_comp rows yet",
    )
    args = parser.parse_args()

    init_db()
    strategy = load_strategy()
    areas = strategy.search.all_areas()
    if args.areas:
        areas = [a for a in areas if a in set(args.areas)]
    elif args.only_missing:
        areas = _areas_without_comps(areas)
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
