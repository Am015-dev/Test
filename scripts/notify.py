"""Send the daily digest. Run from cron after the scrape completes.

    python scripts/notify.py

A no-op (logs and exits 0) when no Telegram/SMTP sink is configured in .env, so it's
safe to wire into the cron unconditionally.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.alerts import send_digest  # noqa: E402
from scout.db import init_db  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    sent = send_digest()
    print("Digest sent." if sent else "No sink configured; digest not sent.")


if __name__ == "__main__":
    main()
