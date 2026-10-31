"""Canonical data model.

Two layers:
- Pydantic ``Listing`` / ``ScoredListing``: the in-memory canonical schema used
  everywhere in the pipeline. Collectors emit raw dicts; ``normalize.py`` maps
  them onto ``Listing``.
- SQLAlchemy ORM tables: the persistent snapshot plus the price/status history
  that is the real signal (days-on-market, price cuts).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ListingStatus = Literal["active", "gone"]
ListingType = Literal["sale", "rent"]


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
    # Unfinished building / under construction ("ημιτελής", "υπό κατασκευή", "σε σκελετό")
    # detected from the card title + description. A home buyer can't move in, so the UI
    # must not recommend these as ready homes.
    is_unfinished: bool = False

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
    # What the listing's own page says, verbatim (JSON-LD description, whitespace-collapsed,
    # capped) and how many photos it has. Only the detail page carries these; a None means
    # the page was never read, so the upsert never lets a card-only sighting blank them.
    description: str | None = None
    photo_count: int | None = None

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        # Every portal's text is stored the same way: whitespace collapsed, capped.
        from .collectors.parse_helpers import clean_description

        return clean_description(value)

    # "rent" rows are rental ads (price = monthly rent). They live in the same table as
    # sales, under the same dedup/history/retire rules, but are never scored, never in sale
    # market stats and never comps for sale flats (scoring.score excludes them as "rent").
    listing_type: ListingType = "sale"
    # Rental-card facts, None when the ad does not say.
    furnished: bool | None = None
    available_from: date | None = None

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
    # Which signals were actually KNOWN (evaluable) for this listing vs dropped as unknown —
    # lets the UI show a transparent "why this score", real signals vs data gaps.
    signal_known: dict[str, bool] = Field(default_factory=dict)


# ---- SQLAlchemy ORM tables -------------------------------------------------


class Base(DeclarativeBase):
    pass


class ListingRow(Base):
    """Current snapshot — one row per unique listing."""

    __tablename__ = "listing"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_source_listing"),
        Index("ix_listing_type_status", "listing_type", "status"),
    )

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
    # See Listing.is_unfinished. Added by forward migration (DEFAULT FALSE) on old DBs.
    is_unfinished: Mapped[bool] = mapped_column(Boolean, default=False)

    # Portal posting date — the listing's real market age (see Listing.listed_date).
    listed_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # When the DETAIL page was last fetched+parsed for this row. Some pages genuinely
    # lack energy/year, so "still missing a field" is NOT "never checked" — without this
    # stamp the depth-enrichment queue re-selects the same unfillable rows forever and
    # never reaches the never-fetched ones.
    detail_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    # See Listing.description / photo_count. Added by forward migration on old DBs.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

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

    # See Listing.listing_type / furnished / available_from. Added by forward migration on
    # old DBs (listing_type DEFAULT 'sale', so every legacy row reads as a sale).
    listing_type: Mapped[str] = mapped_column(
        Text, nullable=False, default="sale", server_default="sale"
    )
    furnished: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)

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


class RentCompRow(Base):
    """Persisted real rental comp — median €/m²/month for an area (and neighbourhood).

    Scraped from the actual RENTAL market and stored so the yield signal uses a real local
    rent instead of the flat baseline — and so a rescore (which doesn't scrape) can still
    apply it. ``neighborhood`` NULL = the area-wide median (the fallback within an area).
    """

    __tablename__ = "rent_comp"
    __table_args__ = (UniqueConstraint("area", "neighborhood", name="uq_rent_comp_area_hood"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area: Mapped[str] = mapped_column(String(128), index=True)
    neighborhood: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rent_per_m2: Mapped[float] = mapped_column(Float)
    samples: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class SavedSearchRow(Base):
    """A persisted investor mandate — the recurring "watch THIS for me" that a monthly
    subscription is actually paying for. Filters are a region list (JSON) + price/yield/grade
    floors; the daily digest can then deliver only what matches, per saved search."""

    __tablename__ = "saved_search"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    regions: Mapped[str | None] = mapped_column(String(512), nullable=True)  # JSON list
    min_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_net_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_grade: Mapped[str | None] = mapped_column(String(2), nullable=True)  # "A"/"B"/"C"
    created_at: Mapped[datetime] = mapped_column(DateTime)


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
