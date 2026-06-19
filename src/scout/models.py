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

    is_private_seller: bool = False
    is_currently_rented: bool = False
    listed_rent: int | None = None  # if "currently rented for EUR X"

    # enriched (computed, not scraped)
    metro_distance_m: int | None = None
    nearest_metro: str | None = None
    price_per_m2: float | None = None
    est_monthly_rent: int | None = None
    gross_yield: float | None = None

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

    is_private_seller: Mapped[bool] = mapped_column(Boolean, default=False)
    is_currently_rented: Mapped[bool] = mapped_column(Boolean, default=False)
    listed_rent: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metro_distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nearest_metro: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_per_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    est_monthly_rent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_yield: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Latest computed score (denormalized for fast UI reads).
    score: Mapped[float] = mapped_column(Float, default=0.0)
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
