"""Tests for upsert-with-history idempotency and price-drop detection."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.models import Base, PriceHistoryRow, StatusHistoryRow

from .conftest import make_listing


@pytest.fixture
def memory_session(monkeypatch):
    """In-memory SQLite session, isolated per test."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    yield session
    session.close()


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_first_upsert_seeds_history(memory_session):
    lst = make_listing(source_id="x1", price=200_000)
    db.upsert_listing_with_history(memory_session, lst, observed_at=datetime(2026, 6, 1))
    assert _count(memory_session, PriceHistoryRow) == 1
    assert _count(memory_session, StatusHistoryRow) == 1


def test_rerun_same_price_is_idempotent(memory_session):
    lst = make_listing(source_id="x1", price=200_000)
    db.upsert_listing_with_history(memory_session, lst, observed_at=datetime(2026, 6, 1))
    db.upsert_listing_with_history(memory_session, lst, observed_at=datetime(2026, 6, 2))
    # No new history rows when nothing changed.
    assert _count(memory_session, PriceHistoryRow) == 1
    assert _count(memory_session, StatusHistoryRow) == 1


def test_price_change_appends_one_history_row(memory_session):
    db.upsert_listing_with_history(
        memory_session,
        make_listing(source_id="x1", price=200_000),
        observed_at=datetime(2026, 6, 1),
    )
    db.upsert_listing_with_history(
        memory_session,
        make_listing(source_id="x1", price=185_000),
        observed_at=datetime(2026, 6, 2),
    )
    assert _count(memory_session, PriceHistoryRow) == 2
    prices = memory_session.scalars(
        select(PriceHistoryRow.price).order_by(PriceHistoryRow.observed_at)
    ).all()
    assert prices == [200_000, 185_000]


def test_unseen_listing_marked_gone(memory_session):
    db.upsert_listing_with_history(
        memory_session, make_listing(source_id="x1"), observed_at=datetime(2026, 6, 1)
    )
    db.upsert_listing_with_history(
        memory_session, make_listing(source_id="x2"), observed_at=datetime(2026, 6, 1)
    )
    # Next run only sees x1.
    n = db.mark_unseen_as_gone(
        memory_session, seen_keys={("spitogatos", "x1")}, observed_at=datetime(2026, 6, 2)
    )
    assert n == 1
    gone = memory_session.scalars(
        select(StatusHistoryRow.status).where(StatusHistoryRow.status == "gone")
    ).all()
    assert gone == ["gone"]


def test_gone_then_reappears_goes_active(memory_session):
    db.upsert_listing_with_history(
        memory_session, make_listing(source_id="x1"), observed_at=datetime(2026, 6, 1)
    )
    db.mark_unseen_as_gone(memory_session, seen_keys=set(), observed_at=datetime(2026, 6, 2))
    # Reappears.
    db.upsert_listing_with_history(
        memory_session, make_listing(source_id="x1"), observed_at=datetime(2026, 6, 3)
    )
    statuses = memory_session.scalars(
        select(StatusHistoryRow.status).order_by(StatusHistoryRow.observed_at)
    ).all()
    assert statuses == ["active", "gone", "active"]
