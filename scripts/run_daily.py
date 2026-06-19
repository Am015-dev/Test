"""Daily cron entrypoint.

Runs the full pipeline. If collectors yield nothing (e.g. portals unreachable or
markup changed), falls back to seeding so the app still has data to show.

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

    if summary["stored"] == 0:
        print("No listings collected — seeding demo data so the UI has content.")
        import seed  # local sibling script

        seed.main()


if __name__ == "__main__":
    main()
