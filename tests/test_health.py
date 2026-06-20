"""Tests for the scraper healthcheck across healthy / stale / blocked scenarios."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.health import check_health
from scout.models import Base, ListingRow, ScrapeJobRow

from .conftest import make_listing


@pytest.fixture
def health_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'h.db'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    yield


def _add_listing(seen_at: datetime, source_id: str = "h1") -> None:
    lst = make_listing(source_id=source_id)
    with db.session_scope() as session:
        db.upsert_listing_with_history(session, lst, observed_at=seen_at)
        session.query(ListingRow).filter_by(source_id=source_id).update({"last_seen": seen_at})


def _add_job(area: str, status: str, listings_found: int | None, updated_at: datetime) -> None:
    with db.session_scope() as session:
        session.add(
            ScrapeJobRow(
                area=area,
                status=status,
                listings_found=listings_found,
                created_at=updated_at,
                updated_at=updated_at,
            )
        )


def test_empty_db_is_error(health_db):
    report = check_health()
    assert report.status == "error"
    assert any("no active listings" in i.lower() for i in report.issues)


def test_healthy(health_db):
    now = datetime.utcnow()
    _add_listing(now)
    _add_job("Cholargos", "done", listings_found=30, updated_at=now)
    report = check_health(now=now)
    assert report.status == "ok"
    assert report.ok and report.issues == []


def test_stale_data_is_error(health_db):
    now = datetime.utcnow()
    _add_listing(now - timedelta(hours=72))  # refreshed 3 days ago
    _add_job("Cholargos", "done", listings_found=30, updated_at=now - timedelta(hours=72))
    report = check_health(now=now)
    assert report.status == "error"
    assert any("stale" in i.lower() for i in report.issues)


def test_total_block_is_error(health_db):
    now = datetime.utcnow()
    _add_listing(now)  # data is fresh...
    # ...but every job this cycle returned zero — all IPs blocked.
    _add_job("Cholargos", "done", listings_found=0, updated_at=now)
    _add_job("Papagou", "done", listings_found=0, updated_at=now)
    report = check_health(now=now)
    assert report.status == "error"
    assert any("0 listings" in i for i in report.issues)


def test_partial_zero_is_warn(health_db):
    now = datetime.utcnow()
    _add_listing(now)
    _add_job("Cholargos", "done", listings_found=30, updated_at=now)
    _add_job("Papagou", "done", listings_found=0, updated_at=now)
    report = check_health(now=now)
    assert report.status == "warn"
    assert any("Papagou" in i for i in report.issues)
