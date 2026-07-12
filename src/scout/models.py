"""Canonical data model.

Two layers:
- Pydantic ``Listing`` / ``ScoredListing``: the in-memory canonical schema used
  everywhere in the pipeline. Collectors emit raw dicts; ``normalize.py`` maps
  them onto ``Listing``.
- SQLAlchemy ORM tables: the persistent snapshot plus the price/status history
  that is the real signal (days-on-market, price cuts).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ListingStatus = Literal["active", "gone"]


# ---- Pydantic canonical model ---------------------------------------------


class Listing(BaseModel):
    """One canonical listing. Collectors never leak portal-specific fields past this."""

    source: str  # "spitogatos" | "xe" | "indomio"
    source_id: str  # portal's listing code
    url: str
    title: str | None = None

    price: int  # EUR
    area_m2: float
    rooms: int | None = None
    bedrooms: int | None = None
    floor: float | None = None  # ground=0, semi-basement=-1, mezzanine=0.5
    year_built: int | None = None
    renovated_year: int | None = None
    heating: str | None = None
    energy_class: str | None = None

    neighborhood: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    search_area: str | None = None  # municipality this was collected under

    is_private_seller: bool = False
    is_currently_rented: bool = False
    listed_rent: int | None = None  # if "currently rented for EUR X"

    # The portal's own posting date (XE detail-page ``datePosted``). This is the
    # listing's REAL market age, known on first sight — so days-on-market and the
    # negotiation signal work from day one instead of only after the daily tracker has
    # watched the listing for weeks.
    listed_date: datetime | None = None

    # enriched (computed, not scraped)
    metro_distance_m: int | None = None
    nearest_metro: str | None = None
    # How the (lat, lng) was obtained: "exact" (detail-page/geocoded point) or "approx"
    # (a municipality/neighbourhood centroid — same point for a whole area). The metro
    # signal and the map must not present an approx point as a precise per-listing figure.
    location_precision: str | None = None
    price_per_m2: float | None = None
    est_monthly_rent: int | None = None
    # True when est_monthly_rent is the flat fallback baseline (no real/neighbourhood rent
    # comp) — so yield is an estimate and must not be scored as if it were a real signal.
    rent_estimated: bool = True
    gross_yield: float | None = None
    # Net yield after Greek acquisition + holding costs and vacancy (finance.py). The
    # honest headline return an investor actually keeps, versus the naive gross figure.
    net_yield: float | None = None

    # Hedonic valuation (computed): the model's fair price given this property's own
    # attributes, and the gap to the asking price. value_gap_pct > 0 = priced below fair
    # value (a genuine bargain, not merely cheap because it's inferior stock).
    predicted_price: int | None = None
    value_gap_pct: float | None = None

    image_url: str | None = None  # a representative photo (card carousel / detail og:image)

    first_seen: datetime | None = None
    last_seen: datetime | None = None
    status: ListingStatus = "active"

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.source_id}"


class ScoredListing(BaseModel):
    """A listing plus its score and the reasoning behind it."""

    listing: Listing
    score: float = 0.0
    excluded: bool = False
    exclusion_reason: str | None = None
    is_opportunity: bool = False
    signals: dict[str, float] = Field(default_factory=dict)


# ---- SQLAlchemy ORM tables -------------------------------------------------


class Base(DeclarativeBase):
    pass


class ListingRow(Base):
    """Current snapshot — one row per unique listing."""

    __tablename__ = "listing"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_source_listing"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)

    price: Mapped[int] = mapped_column(Integer)
    area_m2: Mapped[float] = mapped_column(Float)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[float | None] = mapped_column(Float, nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renovated_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heating: Mapped[str | None] = mapped_column(String(64), nullable=True)
    energy_class: Mapped[str | None] = mapped_column(String(16), nullable=True)

    neighborhood: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The municipality this listing was collected under (the scrape job's area).
    # Scopes per-area retirement so one area's run can't retire another's listings.
    search_area: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)

    is_private_seller: Mapped[bool] = mapped_column(Boolean, default=False)
    is_currently_rented: Mapped[bool] = mapped_column(Boolean, default=False)
    listed_rent: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Portal posting date — the listing's real market age (see Listing.listed_date).
    listed_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    metro_distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nearest_metro: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_precision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    price_per_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    est_monthly_rent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rent_estimated: Mapped[bool] = mapped_column(Boolean, default=True)
    gross_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Net yield after Greek costs + vacancy (see Listing.net_yield). Denormalized for
    # fast UI reads and used by scoring's yield signal.
    net_yield: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Hedonic fair-value estimate and gap to asking price (see Listing above).
    predicted_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_gap_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Latest computed score (denormalized for fast UI reads).
    score: Mapped[float] = mapped_column(Float, default=0.0)
    # Negotiation / motivated-seller score (0-100) from price+status history — the
    # sellable "which owners will deal" signal. Denormalized like `score`.
    negotiation_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_opportunity: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    first_seen: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)

    is_watched: Mapped[bool] = mapped_column(Boolean, default=False)

    prices: Mapped[list[PriceHistoryRow]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )
    statuses: Mapped[list[StatusHistoryRow]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class PriceHistoryRow(Base):
    """Appended only when the price actually changes."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[int] = mapped_column(Integer)

    listing: Mapped[ListingRow] = relationship(back_populates="prices")


class StatusHistoryRow(Base):
    """Appended on status transitions (active <-> gone)."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listing.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16))

    listing: Mapped[ListingRow] = relationship(back_populates="statuses")


class GeocodeCacheRow(Base):
    """Aggressively cache geocoding — many addresses repeat across runs."""

    __tablename__ = "geocode_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)


JobStatus = Literal["pending", "running", "done", "failed"]


class ScrapeJobRow(Base):
    """One unit of scraping work — a single area to collect.

    The shared work queue that lets several workers (each on its own Oracle
    instance / public IP) drain areas into one database without colliding. A worker
    claims a ``pending`` job (an atomic status-guarded UPDATE), holds it with a
    time-boxed ``lease_until``, and marks it ``done``/``failed``. A crashed worker's
    lease expires and the job is requeued, so work is never silently lost.
    """

    __tablename__ = "scrape_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    listings_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class HealthReportRow(Base):
    """One healthcheck snapshot, written after every ``check_health()`` run.

    Persists health state across sessions so the agent can query recent history
    via the postgres MCP without needing log access::

        SELECT checked_at, status, issues
        FROM health_report
        ORDER BY checked_at DESC
        LIMIT 5;
    """

    __tablename__ = "health_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(16))
    issues: Mapped[str | None] = mapped_column(String(2048), nullable=True)  # JSON list
    metrics: Mapped[str | None] = mapped_column(String(4096), nullable=True)  # JSON dict
