"""Scrape-job work queue.

The mechanism that lets several workers — each on its own Oracle instance / public
IP — drain areas into the one shared database without colliding or losing work:

- ``enqueue_areas`` adds a pending job per area (skipping areas already queued).
- ``claim_job`` atomically claims one pending job via a status-guarded UPDATE, so
  two workers never grab the same area (correct on both SQLite and Postgres).
- ``requeue_stale`` returns jobs whose worker died (lease expired) to ``pending``.
- ``complete_job`` / ``fail_job`` close a job out.

Claiming deliberately avoids ``FOR UPDATE SKIP LOCKED`` so the same code runs on the
SQLite used in tests and the Postgres used in production; the guarded UPDATE is still
race-free (only one transaction's ``WHERE status='pending'`` can win).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update

from .db import session_scope
from .models import ScrapeJobRow

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")
# A job claimed this many times without completing is treated as a poison pill (its
# work keeps hard-crashing the worker) and failed instead of requeued forever.
MAX_ATTEMPTS = 5
# Defensive cap on claim_job's re-query loop (10 candidates each) so it can never spin
# forever; far more than any realistic pending backlog a single claim needs to scan.
MAX_CLAIM_BATCHES = 100


@dataclass(frozen=True)
class ClaimedJob:
    id: int
    area: str
    attempts: int


def enqueue_areas(areas: list[str], now: datetime | None = None) -> int:
    """Add a pending job for each area without an in-flight (pending/running) job.

    Idempotent within a cycle: re-running while jobs are still queued won't pile up
    duplicates. Returns the number of jobs created.
    """
    now = now or datetime.utcnow()
    created = 0
    with session_scope() as session:
        for area in areas:
            in_flight = session.scalar(
                select(func.count())
                .select_from(ScrapeJobRow)
                .where(ScrapeJobRow.area == area, ScrapeJobRow.status.in_(ACTIVE_STATUSES))
            )
            if in_flight:
                continue
            session.add(ScrapeJobRow(area=area, status="pending", created_at=now, updated_at=now))
            created += 1
    logger.info("enqueue: %d new job(s) for %d area(s)", created, len(areas))
    return created


def requeue_stale(lease_grace_minutes: int = 0, now: datetime | None = None) -> int:
    """Return running jobs whose lease expired (crashed worker) to pending.

    A job that has burned through ``MAX_ATTEMPTS`` claims without completing is failed
    instead — a hard crash (OOM/SIGKILL) never runs ``fail_job``, so without this cap
    it would be reclaimed and re-crash forever, poisoning the queue. Returns the number
    requeued (not the number failed).
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(minutes=lease_grace_minutes)
    with session_scope() as session:
        poisoned = session.execute(
            update(ScrapeJobRow)
            .where(
                ScrapeJobRow.status == "running",
                ScrapeJobRow.lease_until < cutoff,
                ScrapeJobRow.attempts >= MAX_ATTEMPTS,
            )
            .values(
                status="failed",
                error="exceeded max attempts (worker keeps crashing)",
                updated_at=now,
            )
        ).rowcount
        requeued = session.execute(
            update(ScrapeJobRow)
            .where(
                ScrapeJobRow.status == "running",
                ScrapeJobRow.lease_until < cutoff,
                ScrapeJobRow.attempts < MAX_ATTEMPTS,
            )
            .values(status="pending", worker_id=None, updated_at=now)
        ).rowcount
    if poisoned:
        logger.error("requeue: failed %d poison job(s) (exceeded max attempts)", poisoned)
    if requeued:
        logger.warning("requeue: returned %d stale job(s) to pending", requeued)
    return requeued


def claim_job(
    worker_id: str, lease_minutes: int = 30, now: datetime | None = None
) -> ClaimedJob | None:
    """Atomically claim one pending job, or return None if the queue is empty."""
    now = now or datetime.utcnow()
    lease = now + timedelta(minutes=lease_minutes)
    with session_scope() as session:
        # Re-query past the first batch: under heavy contention every candidate in a
        # batch can be claimed by other workers before we win one. Returning None then
        # would wrongly report the queue empty (and a one-shot drain would stop) while
        # jobs 11..N are still pending. Loop until we claim one or the pending set is
        # genuinely exhausted; claimed jobs leave 'pending', so this always terminates.
        # The batch cap is a defensive bound against pathological spin.
        for _ in range(MAX_CLAIM_BATCHES):
            candidate_ids = session.scalars(
                select(ScrapeJobRow.id)
                .where(ScrapeJobRow.status == "pending")
                .order_by(ScrapeJobRow.created_at)
                .limit(10)
            ).all()
            if not candidate_ids:
                return None
            for jid in candidate_ids:
                # Status-guarded UPDATE: only the transaction that still sees this row as
                # 'pending' wins; a racing worker's UPDATE matches 0 rows and moves on.
                res = session.execute(
                    update(ScrapeJobRow)
                    .where(ScrapeJobRow.id == jid, ScrapeJobRow.status == "pending")
                    .values(
                        status="running",
                        worker_id=worker_id,
                        lease_until=lease,
                        updated_at=now,
                        attempts=ScrapeJobRow.attempts + 1,
                    )
                )
                if res.rowcount == 1:
                    row = session.get(ScrapeJobRow, jid)
                    logger.info("claim: worker %s took area %r (job %d)", worker_id, row.area, jid)
                    return ClaimedJob(id=row.id, area=row.area, attempts=row.attempts)
    return None


def _close_job(job_id: int, worker_id: str | None, values: dict) -> None:
    """Close a job out, guarded by ownership so a worker whose lease expired and whose
    job was reclaimed by another worker can't clobber the new owner's state."""
    with session_scope() as session:
        stmt = update(ScrapeJobRow).where(ScrapeJobRow.id == job_id)
        if worker_id is not None:
            stmt = stmt.where(ScrapeJobRow.worker_id == worker_id)
        session.execute(stmt.values(**values))


def complete_job(
    job_id: int, listings_found: int, worker_id: str | None = None, now: datetime | None = None
) -> None:
    now = now or datetime.utcnow()
    _close_job(
        job_id,
        worker_id,
        {"status": "done", "listings_found": listings_found, "error": None, "updated_at": now},
    )


def fail_job(
    job_id: int, error: str, worker_id: str | None = None, now: datetime | None = None
) -> None:
    now = now or datetime.utcnow()
    _close_job(job_id, worker_id, {"status": "failed", "error": error[:512], "updated_at": now})


def job_stats(now: datetime | None = None) -> dict[str, int]:
    """Counts per status — for the healthcheck / a future dashboard panel."""
    with session_scope() as session:
        rows = session.execute(
            select(ScrapeJobRow.status, func.count()).group_by(ScrapeJobRow.status)
        ).all()
    return {status: count for status, count in rows}
