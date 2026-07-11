"""Read-only DB access for the UI.

The UI never scrapes — it only reads the DB the pipeline populated. These helpers
return plain dicts / lists so the Streamlit layer can cache them with
``@st.cache_data``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from ..db import session_scope
from ..models import HealthReportRow, ListingRow, PriceHistoryRow


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
        "year_built": row.year_built,
        "renovated_year": row.renovated_year,
        "energy_class": row.energy_class,
        "heating": row.heating,
        "neighborhood": row.neighborhood,
        "address": row.address,
        "search_area": row.search_area,
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
        "predicted_price": row.predicted_price,
        "value_gap_pct": row.value_gap_pct,
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


def load_recent_price_drops(hours: int = 24) -> list[dict]:
    """Listings whose *latest* price change happened within the window and was a cut.

    This is the accurate "dropped today" signal for the digest — unlike the cumulative
    ``price_dropped`` flag (price below the first-ever price), which would re-report an
    old drop every day. Each dict carries the listing fields plus ``old_price`` /
    ``new_price`` / ``drop_pct``.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    with session_scope() as session:
        rows = session.scalars(select(ListingRow).where(ListingRow.status == "active")).all()
        ids = [r.id for r in rows]
        firsts = _first_prices(session, ids)
        history = session.scalars(
            select(PriceHistoryRow)
            .where(PriceHistoryRow.listing_id.in_(ids or [-1]))
            .order_by(PriceHistoryRow.listing_id, PriceHistoryRow.observed_at)
        ).all()
        by_listing: dict[int, list[PriceHistoryRow]] = {}
        for h in history:
            by_listing.setdefault(h.listing_id, []).append(h)

        drops = []
        for r in rows:
            hist = by_listing.get(r.id, [])
            if len(hist) < 2:
                continue
            latest, prev = hist[-1], hist[-2]
            if latest.observed_at >= cutoff and latest.price < prev.price:
                d = _row_to_dict(r, firsts.get(r.id))
                d["old_price"] = prev.price
                d["new_price"] = latest.price
                d["drop_pct"] = (prev.price - latest.price) / prev.price if prev.price else 0.0
                drops.append(d)
        drops.sort(key=lambda d: d["drop_pct"], reverse=True)
        return drops


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


def load_recent_health(limit: int = 20) -> list[dict]:
    """Most recent persisted health snapshots (newest first), for the UI health panel.

    Returns plain dicts (issues/metrics are the raw JSON strings the caller parses),
    so nothing detaches when the session closes. Empty list if the table is empty or
    absent (older DBs created before the health_report table existed).
    """
    try:
        with session_scope() as session:
            rows = session.scalars(
                select(HealthReportRow).order_by(HealthReportRow.checked_at.desc()).limit(limit)
            ).all()
            return [
                {
                    "checked_at": r.checked_at,
                    "status": r.status,
                    "issues": r.issues,
                    "metrics": r.metrics,
                }
                for r in rows
            ]
    except Exception:
        return []


def load_valuation_summary() -> dict:
    """Fit the hedonic model PER AREA over the current active set and report confidence.

    Returns an ``areas`` map (``area -> {r2, residual_std, is_confident, n}``) plus an
    ``overall`` aggregate, so the UI can be honest: a per-area ± band and a confidence
    read that matches how the stored valuations were actually produced (per submarket),
    never one pooled number that understates the real fit. ``residual_std`` per area lets
    the UI turn each listing's stored ``predicted_price`` into a ±1σ range with no schema
    change."""
    from ..pipeline import _row_to_listing
    from ..valuation import fit_and_apply_by_area

    with session_scope() as session:
        rows = session.scalars(select(ListingRow).where(ListingRow.status == "active")).all()
        listings = [_row_to_listing(r) for r in rows]
    models = fit_and_apply_by_area(listings)
    if not models:
        return {
            "fitted": False,
            "areas": {},
            "overall": {"is_confident": False, "n": len(listings)},
        }

    areas = {
        area: {
            "r2": round(m.r2, 3),
            "residual_std": m.residual_std,
            "is_confident": m.is_confident,
            "n": m.n_samples,
        }
        for area, m in models.items()
    }
    total_n = sum(m.n_samples for m in models.values()) or 1
    # Sample-weighted mean R² and a conservative (widest) residual band across areas.
    overall = {
        "r2": round(sum(m.r2 * m.n_samples for m in models.values()) / total_n, 3),
        "residual_std": max(m.residual_std for m in models.values()),
        "is_confident": all(m.is_confident for m in models.values()),
        "n": total_n,
        "n_areas": len(models),
    }
    return {"fitted": True, "areas": areas, "overall": overall}


def load_all_price_history() -> list[dict]:
    """Every price observation across all listings, for the market price index.

    Each dict is ``{observed_at, price}``; the analytics layer buckets them by month.
    """
    with session_scope() as session:
        rows = session.scalars(select(PriceHistoryRow)).all()
        return [{"observed_at": r.observed_at, "price": r.price} for r in rows]
