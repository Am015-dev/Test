"""Scrape worker — drains the area queue into the shared database.

Run one (or many) of these, one per Oracle instance, so each scrapes from its own
public IP. Each worker claims pending areas, scrapes them, and marks them done:

    python scripts/worker.py                 # drain the queue once, then exit
    python scripts/worker.py --poll 300      # keep polling every 300s
    python scripts/worker.py --worker-id oci-2 --lease-minutes 20

A claimed job is leased for ``--lease-minutes``; if this worker crashes, the lease
expires and another worker requeues and retakes the area, so no work is lost.
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.db import init_db  # noqa: E402
from scout.pipeline import run_for_area  # noqa: E402
from scout.queue import claim_job, complete_job, fail_job, requeue_stale  # noqa: E402

logger = logging.getLogger("worker")


def drain_once(worker_id: str, lease_minutes: int) -> int:
    """Process every currently-claimable job. Returns how many were processed."""
    requeue_stale()
    processed = 0
    while True:
        job = claim_job(worker_id, lease_minutes=lease_minutes)
        if job is None:
            break
        logger.info("processing area %r (job %d, attempt %d)", job.area, job.id, job.attempts)
        try:
            summary = run_for_area(job.area)
            complete_job(job.id, listings_found=summary.get("stored", 0))
            logger.info("done area %r: %s", job.area, summary)
        except Exception as exc:  # real error — mark failed; lease-requeue won't apply
            logger.exception("area %r failed", job.area)
            fail_job(job.id, error=str(exc))
        processed += 1
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Holargos scrape worker")
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{int(time.time())}")
    parser.add_argument("--lease-minutes", type=int, default=15)
    parser.add_argument(
        "--poll",
        type=int,
        default=0,
        help="Seconds to sleep between drains; 0 (default) drains once and exits.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()

    while True:
        n = drain_once(args.worker_id, args.lease_minutes)
        logger.info("worker %s drained %d job(s)", args.worker_id, n)
        if args.poll <= 0:
            break
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
