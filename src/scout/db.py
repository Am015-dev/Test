"""Engine, session, and the upsert-with-history core.

The history tables are the point: ``upsert_listing_with_history`` appends a
price_history row *only when the price changed* and a status_history row *only on
status transitions*. Running the pipeline twice in a day is idempotent — no
duplicate history rows are created.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import (
    Base,
    Listing,
    ListingRow,
    PriceHistoryRow,
    StatusHistoryRow,
)

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None

# Snapshot fields copied from a Listing onto a ListingRow (excludes history-managed
# and identity fields).
_SNAPSHOT_FIELDS = (
    "url",
    "title",
    "price",
    "area_m2",
    "rooms",
    "bedrooms",
    "floor",
    "year_built",
    "renovated_year",
    "heating",
    "energy_class",
    "neighborhood",
    "address",
    "lat",
    "lng",
    "search_area",
    "is_private_seller",
    "is_currently_rented",
    "listed_rent",
    "metro_distance_m",
    "nearest_metro",
    "price_per_m2",
    "est_monthly_rent",
    "gross_yield",
)


def get_engine() -> Engine:
    global _engine, _SessionFactory
    if _engine is None:
        _engine = create_engine(get_settings().db_url, future=True)
        _SessionFactory = sessionmaker(bind=_engine, future=True)
    return _engine


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context manager."""
    if _SessionFactory is None:
        get_engine()
    assert _SessionFactory is not None
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upsert_listing_with_history(
    session: Session, listing: Listing, observed_at: datetime | None = None
) -> ListingRow:
    """Insert or update a listing, appending history rows only on real changes.

    - New listing: insert row, seed one price_history row and one status_history row.
    - Existing listing: update the snapshot; append price_history only if price
      changed; append status_history only if status changed. Always bump last_seen.
    """
    now = observed_at or datetime.utcnow()
    row = session.scalar(
        select(ListingRow).where(
            ListingRow.source == listing.source,
            ListingRow.source_id == listing.source_id,
        )
    )

    if row is None:
        row = ListingRow(
            source=listing.source,
            source_id=listing.source_id,
            first_seen=listing.first_seen or now,
            last_seen=now,
            status="active",
        )
        for field in _SNAPSHOT_FIELDS:
            setattr(row, field, getattr(listing, field))
        session.add(row)
        session.flush()  # assign row.id
        session.add(PriceHistoryRow(listing_id=row.id, observed_at=now, price=listing.price))
        session.add(StatusHistoryRow(listing_id=row.id, observed_at=now, status="active"))
        return row

    # Existing: detect a genuine price change before overwriting the snapshot.
    price_changed = row.price != listing.price
    status_was = row.status

    for field in _SNAPSHOT_FIELDS:
        setattr(row, field, getattr(listing, field))
    row.last_seen = now

    if price_changed:
        session.add(PriceHistoryRow(listing_id=row.id, observed_at=now, price=listing.price))

    # A listing seen this run is active again.
    if status_was != "active":
        row.status = "active"
        session.add(StatusHistoryRow(listing_id=row.id, observed_at=now, status="active"))

    session.flush()
    return row


def mark_unseen_as_gone(
    session: Session,
    seen_keys: set[tuple[str, str]],
    observed_at: datetime | None = None,
    active_sources: set[str] | None = None,
    area: str | None = None,
) -> int:
    """Mark active listings not seen this run as ``gone`` and append status history.

    ``seen_keys`` is a set of (source, source_id).

    ``active_sources`` is the set of portals that actually returned data this run.
    Only listings from those portals are eligible for retirement: a portal that
    returned nothing (blocked, down, or markup changed) must NOT cause its
    previously-collected listings to be wiped — otherwise a single failed scrape
    empties the app. When ``active_sources`` is ``None`` every source is eligible
    (legacy behavior, used by direct unit tests); when it is empty, nothing is
    retired.

    Returns the number transitioned.
    """
    now = observed_at or datetime.utcnow()
    query = select(ListingRow).where(ListingRow.status == "active")
    # Scope retirement to one area's run so a per-area worker never retires listings
    # collected for a different area (which it didn't scrape this run).
    if area is not None:
        query = query.where(ListingRow.search_area == area)
    rows = session.scalars(query).all()
    transitioned = 0
    for row in rows:
        if active_sources is not None and row.source not in active_sources:
            continue  # this portal produced no results this run — leave its data intact
        if (row.source, row.source_id) not in seen_keys:
            row.status = "gone"
            session.add(StatusHistoryRow(listing_id=row.id, observed_at=now, status="gone"))
            transitioned += 1
    session.flush()
    return transitioned
