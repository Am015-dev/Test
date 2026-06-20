"""Tests for the scrape-job work queue and the worker drain loop."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout import queue
from scout.models import Base

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def queue_db(tmp_path, monkeypatch):
    """Point the global session factory at a file-based SQLite (shared across calls)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'q.db'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    yield


def test_enqueue_creates_and_dedups_in_flight(queue_db):
    assert queue.enqueue_areas(["Cholargos", "Papagou"]) == 2
    # Re-enqueue while both are still pending -> nothing added.
    assert queue.enqueue_areas(["Cholargos", "Papagou"]) == 0
    assert queue.job_stats() == {"pending": 2}


def test_claim_is_exclusive(queue_db):
    queue.enqueue_areas(["Cholargos"])
    first = queue.claim_job("worker-1")
    second = queue.claim_job("worker-2")
    assert first is not None and first.area == "Cholargos"
    assert first.attempts == 1
    assert second is None  # only one pending job; worker-2 gets nothing
    assert queue.job_stats() == {"running": 1}


def test_requeue_stale_returns_crashed_jobs(queue_db):
    queue.enqueue_areas(["Cholargos"])
    queue.claim_job("worker-1", lease_minutes=15)
    # Simulate the worker dying: look back from well after the lease expired.
    future = datetime.utcnow() + timedelta(hours=1)
    assert queue.requeue_stale(now=future) == 1
    assert queue.job_stats() == {"pending": 1}
    # And it can be re-claimed (attempts keeps climbing).
    again = queue.claim_job("worker-2")
    assert again is not None and again.attempts == 2


def test_complete_and_fail(queue_db):
    queue.enqueue_areas(["A", "B"])
    a = queue.claim_job("w")
    b = queue.claim_job("w")
    queue.complete_job(a.id, listings_found=7)
    queue.fail_job(b.id, error="boom")
    assert queue.job_stats() == {"done": 1, "failed": 1}


def test_complete_job_ignores_non_owner(queue_db):
    """A worker whose lease expired (job reclaimed by another) can't clobber it."""
    queue.enqueue_areas(["X"])
    job = queue.claim_job("w1")
    queue.complete_job(job.id, listings_found=5, worker_id="w2")  # not the owner -> no-op
    assert queue.job_stats() == {"running": 1}
    queue.complete_job(job.id, listings_found=5, worker_id="w1")  # owner -> closes it
    assert queue.job_stats() == {"done": 1}


def test_poison_job_is_failed_after_max_attempts(queue_db):
    """A job that keeps crashing its worker (lease expiry, never completes) is failed,
    not requeued forever."""
    queue.enqueue_areas(["X"])
    future = datetime.utcnow() + timedelta(hours=1)
    for _ in range(queue.MAX_ATTEMPTS):
        assert queue.claim_job("w") is not None
        queue.requeue_stale(now=future)
    assert queue.job_stats() == {"failed": 1}
    assert queue.claim_job("w") is None  # no longer reclaimable


def _load_worker():
    spec = importlib.util.spec_from_file_location("worker_mod", REPO_ROOT / "scripts" / "worker.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_worker_drains_all_jobs(queue_db, monkeypatch):
    worker = _load_worker()
    scraped: list[str] = []

    def fake_run_for_area(area, **kwargs):
        scraped.append(area)
        return {"stored": len(area)}  # arbitrary deterministic count

    monkeypatch.setattr(worker, "run_for_area", fake_run_for_area)
    queue.enqueue_areas(["Cholargos", "Papagou", "Agia Paraskevi"])

    processed = worker.drain_once("worker-1", lease_minutes=15)
    assert processed == 3
    assert sorted(scraped) == ["Agia Paraskevi", "Cholargos", "Papagou"]
    assert queue.job_stats() == {"done": 3}
    # Queue now empty -> a second drain is a no-op.
    assert worker.drain_once("worker-1", lease_minutes=15) == 0


def test_worker_marks_failure_on_exception(queue_db, monkeypatch):
    worker = _load_worker()

    def boom(area, **kwargs):
        raise RuntimeError("scrape exploded")

    monkeypatch.setattr(worker, "run_for_area", boom)
    queue.enqueue_areas(["Cholargos"])
    worker.drain_once("worker-1", lease_minutes=15)
    assert queue.job_stats() == {"failed": 1}
