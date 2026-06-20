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


def _db_is_empty() -> bool:
    from sqlalchemy import func, select

    from scout.db import init_db, session_scope
    from scout.models import ListingRow

    init_db()
    with session_scope() as session:
        return (session.scalar(select(func.count()).select_from(ListingRow)) or 0) == 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    summary = run()
    print(f"Pipeline complete: {summary}")

    # Only ever seed demo data into a genuinely EMPTY database (first boot, before any
    # real scrape). Never inject fake listings alongside real data — a run that
    # legitimately stores nothing new must not pollute a populated production DB.
    if summary["stored"] == 0 and _db_is_empty():
        print("Database empty and nothing collected — seeding demo data for first boot.")
        import seed  # local sibling script

        seed.main()


if __name__ == "__main__":
    main()
