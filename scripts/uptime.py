"""Uptime probe — GETs the dashboard URL and reports pass/fail.

    DASHBOARD_URL=http://localhost:8501 python scripts/uptime.py

Exits 0 on success (HTTP 2xx), 1 on failure (error or timeout). On failure sends
an alert via any configured sink (Telegram / email). Safe to add to cron with no
alert config — the send is a no-op when unconfigured.

Add to the host cron (optional, after SITE_ADDRESS is set):
    */15 * * * * DASHBOARD_URL=https://$SITE_ADDRESS python /opt/holargos/scripts/uptime.py
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests  # noqa: E402

from scout.alerts import send_alert  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.environ.get("DASHBOARD_URL", "http://localhost:8501")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        logging.info("uptime: %s → %d OK", url, r.status_code)
        return 0
    except Exception as exc:
        msg = f"🔴 Holargos dashboard unreachable at {url}: {exc}"
        logging.error(msg)
        send_alert(msg, subject="🔴 Holargos Scout: dashboard DOWN")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
