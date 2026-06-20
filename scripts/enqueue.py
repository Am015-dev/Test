"""Enqueue a scrape job per configured area. Run from cron on the control VM.

    python scripts/enqueue.py

Areas come from ``strategy.yaml`` (``search.municipality`` + ``search.areas``).
Idempotent: areas with an in-flight job are skipped, so it's safe to run on a
schedule even while workers are still draining the queue.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.config import load_strategy  # noqa: E402
from scout.db import init_db  # noqa: E402
from scout.queue import enqueue_areas  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    areas = load_strategy().search.all_areas()
    created = enqueue_areas(areas)
    print(f"Enqueued {created} job(s) for areas: {areas}")


if __name__ == "__main__":
    main()
