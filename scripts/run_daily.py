"""Daily cron entrypoint — runs the full pipeline against the live portals.

No demo/seed fallback: this stores real listings only. An empty run (e.g. XE
throttling) is left to the next run; the pipeline is fail-soft and never wipes
existing data.

    python scripts/run_daily.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.config import load_strategy  # noqa: E402
from scout.pipeline import run_for_area  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    """Scrape EVERY configured area, one at a time (polite), on a single node.

    Iterates over ``search.municipality`` + ``search.areas`` via ``run_for_area``, which
    scopes retirement per area so one area's run never retires another's listings. Each
    area is fail-soft: a blocked/empty area logs and the rest still run. For horizontal
    scale-out across multiple IPs, use the ``enqueue`` + ``worker`` queue instead.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    areas = load_strategy().search.all_areas()
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
