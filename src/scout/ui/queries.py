"""Read-only DB access for the UI.

The UI never scrapes — it only reads the DB the pipeline populated. These helpers
return plain dicts / lists so the Streamlit layer can cache them with
``@st.cache_data``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from ..db import session_scope
from ..models import ListingRow, PriceHistoryRow


def _row_to_dict(row: ListingRow, first_price: int | None) -> dict:
    price_dropped = bool(first_price and row.price < first_price)
    return {
        "id": row.id,
        "source": row.source,
        "source_id": row.source_id,
        "url": row.url,
        "title": row.title,
        "price": row.price,
        "first_price": first_price,
        "price_dropped": price_dropped,
        "area_m2": row.area_m2,
        "rooms": row.rooms,
        "bedrooms": row.bedrooms,
        "floor": row.floor,
        "neighborhood": row.neighborhood,
        "address": row.address,
        "lat": row.lat,
        "lng": row.lng,
        "is_private_seller": row.is_private_seller,
        "is_currently_rented": row.is_currently_rented,
        "listed_rent": row.listed_rent,
        "metro_distance_m": row.metro_distance_m,
        "nearest_metro": row.nearest_metro,
        "price_per_m2": row.price_per_m2,
        "est_monthly_rent": row.est_monthly_rent,
        "gross_yield": row.gross_yield,
        "score": row.score,
        "is_opportunity": row.is_opportunity,
        "excluded": row.excluded,
        "exclusion_reason": row.exclusion_reason,
        "status": row.status,
        "is_watched": row.is_watched,
        "first_seen": row.first_seen,
        "last_seen": row.last_seen,
    }


def _first_prices(session, ids: list[int]) -> dict[int, int]:
    """Earliest recorded price per listing id."""
    out: dict[int, int] = {}
    if not ids:
        return out
    rows = session.scalars(
        select(PriceHistoryRow)
        .where(PriceHistoryRow.listing_id.in_(ids))
        .order_by(PriceHistoryRow.observed_at)
    ).all()
    for ph in rows:
        out.setdefault(ph.listing_id, ph.price)  # first (earliest) wins
    return out


def load_listings(include_excluded: bool = True, only_active: bool = True) -> list[dict]:
    """Load all listings as dicts, annotated with first_price / price_dropped / is_new."""
    with session_scope() as session:
        stmt = select(ListingRow)
        if only_active:
            stmt = stmt.where(ListingRow.status == "active")
        if not include_excluded:
            stmt = stmt.where(ListingRow.excluded.is_(False))
        rows = session.scalars(stmt).all()
        firsts = _first_prices(session, [r.id for r in rows])
        cutoff = datetime.utcnow() - timedelta(hours=24)
        out = []
        for r in rows:
            d = _row_to_dict(r, firsts.get(r.id))
            d["is_new"] = r.first_seen is not None and r.first_seen >= cutoff
            out.append(d)
        return out


def load_price_history(listing_id: int) -> list[tuple[datetime, int]]:
    with session_scope() as session:
        rows = session.scalars(
            select(PriceHistoryRow)
            .where(PriceHistoryRow.listing_id == listing_id)
            .order_by(PriceHistoryRow.observed_at)
        ).all()
        return [(r.observed_at, r.price) for r in rows]


def set_watched(listing_id: int, watched: bool) -> None:
    with session_scope() as session:
        row = session.get(ListingRow, listing_id)
        if row is not None:
            row.is_watched = watched
