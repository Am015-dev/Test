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

from scout.pipeline import run  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    summary = run()
    print(f"Pipeline complete: {summary}")


if __name__ == "__main__":
    main()
