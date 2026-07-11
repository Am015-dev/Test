"""Deployment readiness self-check. Run by hand to diagnose a misbehaving deploy.

    python scripts/doctor.py

Checks DB connectivity + schema, backend suitability, data presence, geocoder/alert
config, and collector coverage. Prints a report and exits non-zero if any check FAILs
(so it doubles as a container/CI smoke gate). Never prints secrets.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.doctor import as_text, diagnose, worst_status  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    checks = diagnose()
    print(as_text(checks))
    return 1 if worst_status(checks) == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
