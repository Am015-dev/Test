"""Healthcheck — alert if scraping has silently broken. Run from cron, twice daily.

    python scripts/healthcheck.py

Prints the report, persists it to the health_report table (readable by the agent
via the postgres MCP), and on WARN/ERROR sends it to any configured alert sink.
Exits non-zero on ERROR so external monitoring (or cron mail) also notices.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.alerts import send_alert  # noqa: E402
from scout.db import init_db  # noqa: E402
from scout.health import check_health, persist_health_report  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    report = check_health()
    persist_health_report(report)  # durable state for agent cross-session observability
    text = report.as_text()
    print(text)
    if not report.ok:
        send_alert(text, subject=f"🚨 Holargos Scout health: {report.status.upper()}")
    return 1 if report.status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
