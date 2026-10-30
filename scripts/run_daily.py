"""Daily cron entrypoint — runs the full pipeline against the live portals.

No demo/seed fallback: this stores real listings only. An empty run (e.g. XE
throttling) is left to the next run; the pipeline is fail-soft and never wipes
existing data.

    python scripts/run_daily.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.config import load_strategy  # noqa: E402
from scout.pipeline import run_for_area  # noqa: E402

logger = logging.getLogger(__name__)


def todays_shard(areas: list[str], shards: int) -> list[str]:
    """1/`shards` of the areas, rotating by day so the whole set is covered every
    `shards` days. A full 55-area × 2-portal sweep can't finish inside CI's budget
    (and would burn the private-repo Actions quota), so each run does a small slice
    and commits it; over a cycle every area is refreshed. shards<=1 → everything.
    """
    if shards <= 1:
        return areas
    idx = date.today().toordinal() % shards
    return areas[idx::shards]


def main() -> None:
    """Scrape a (rotating slice of) configured areas, one at a time (polite), on a single
    node.

    Iterates over ``search.municipality`` + ``search.areas`` via ``run_for_area``, which
    scopes retirement per area so one area's run never retires another's listings. Each
    area is fail-soft: a blocked/empty area logs and the rest still run. For horizontal
    scale-out across multiple IPs, use the ``enqueue`` + ``worker`` queue instead.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--shards",
        type=int,
        default=1,
        help="Split areas into N day-rotated groups and scrape only today's group "
        "(full coverage every N days). Default 1 = every area.",
    )
    parser.add_argument(
        "--areas",
        default="",
        help="Comma-separated areas to scrape instead of today's slice (e.g. 'Cholargos,Chalandri').",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    picked = [a.strip() for a in args.areas.split(",") if a.strip()]
    areas = picked or todays_shard(load_strategy().search.all_areas(), args.shards)
    totals: dict[str, int] = {}
    for area in areas:
        try:
            summary = run_for_area(area)
            logger.info("area %s: %s", area, summary)
            for key, value in summary.items():
                totals[key] = totals.get(key, 0) + value
        except Exception as exc:  # one bad area must not abort the whole daily run
            logger.warning("area %s failed: %s", area, exc)
    print(f"Daily complete over {len(areas)} area(s): {totals}")


if __name__ == "__main__":
    main()
