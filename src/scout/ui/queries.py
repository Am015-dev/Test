"""Read-only DB access for the UI.

The UI never scrapes — it only reads the DB the pipeline populated. These helpers
return plain dicts / lists so the Streamlit layer can cache them with
``@st.cache_data``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from ..consistency import consistency_flags as _consistency_flags
from ..data_quality import listing_confidence
from ..data_quality_guards import clean_future_years, data_quality_flags
from ..db import session_scope
from ..deal import advise as _advise_deal
from ..investment import deal_grade as _deal_grade
from ..investment import yield_on_offer as _yield_on_offer
from ..models import HealthReportRow, ListingRow, PriceHistoryRow, RentCompRow
from ..recommendation import recommend as _recommend
from ..regions import region_of
from ..relative_value import annotate_relative_value
from ..scoring import investment_archetype
from ..strategy_fit import strategy_tags as _strategy_tags


def _market_age_days(row: ListingRow) -> int | None:
    """True days on market: from the portal's own posting date when known, else from when
    we first tracked it — whichever is earlier (the earliest evidence it was live)."""
    anchors = [d for d in (row.listed_date, row.first_seen) if d is not None]
    if not anchors:
        return None
    return max((datetime.utcnow() - min(anchors)).days, 0)


def _building_age(year_built: int | None, renovated_year: int | None) -> int | None:
    """Years since construction (or renovation, which resets the clock). None when unknown
    or implausible (before 1850 / in the future — data errors, not ages)."""
    year = renovated_year or year_built
    now = datetime.utcnow().year
    if not year or year < 1850 or year > now:
        return None
    return now - year


# A listing not re-seen within this many days of the newest scrape is probably sold.
FRESH_DAYS = 10


def _annotate_freshness(rows: list[dict]) -> None:
    """Set ``is_fresh`` relative to the NEWEST ``last_seen`` in the set (not wall-clock), so
    an old snapshot still shows its latest scrape as fresh instead of hiding everything."""
    seen = [d["last_seen"] for d in rows if d.get("last_seen") is not None]
    if not seen:
        return
    cutoff = max(seen) - timedelta(days=FRESH_DAYS)
    for d in rows:
        d["is_fresh"] = d.get("last_seen") is not None and d["last_seen"] >= cutoff


def _data_completeness(row: ListingRow) -> list[str]:
    """Which trust-critical fields are still MISSING for this listing (empty = complete).

    Card-only listings from the breadth sweep lack most of these; surfacing exactly what's
    unknown is the honest alternative to printing confident-looking numbers over gaps."""
    # Per-listing SCRAPE gaps only. Rent is a systemic estimate (flagged inline as "est."
    # on the yield chip, since real rent comps aren't yet available market-wide), so it is
    # deliberately NOT a per-listing completeness item — otherwise the badge would fire on
    # every listing and mean nothing.
    missing: list[str] = []
    if not (row.energy_class or "").strip():
        missing.append("ενεργειακή κλάση")
    if not (row.year_built or row.renovated_year):
        missing.append("έτος κατασκευής")
    if row.location_precision != "exact":
        missing.append("ακριβής τοποθεσία")
    return missing


def _row_to_dict(
    row: ListingRow,
    first_price: int | None,
    num_cuts: int = 0,
    area_median_ppm2: float | None = None,
) -> dict:
    price_dropped = bool(first_price and row.price < first_price)
    days_on_market = _market_age_days(row)
    # A confident fair value is exactly the case where value_gap_pct survived the
    # valuation confidence + real-attributes gate (None otherwise).
    value_confident = row.value_gap_pct is not None
    missing = _data_completeness(row)
    # One-line recommended offer + thesis — the actionable decision surfaced in the UI.
    deal = _advise_deal(
        asking=row.price,
        predicted_price=row.predicted_price,
        value_confident=value_confident,
        negotiation_score=row.negotiation_score or 0.0,
        days_on_market=days_on_market,
        num_cuts=num_cuts,
        net_yield=row.net_yield,
    )
    _confidence = listing_confidence(
        {
            "energy_class": row.energy_class,
            "year_built": row.year_built,
            "renovated_year": row.renovated_year,
            "location_precision": row.location_precision,
            "rent_estimated": row.rent_estimated,
            "listed_date": row.listed_date,
        }
    )
    _grade = _deal_grade(
        score=row.score or 0.0,
        data_complete=not missing,
        net_yield=row.net_yield,
        value_gap_pct=row.value_gap_pct,
        negotiation_score=row.negotiation_score or 0.0,
    )
    _consistency = _consistency_flags(
        {
            "price_per_m2": row.price_per_m2,
            "area_m2": row.area_m2,
            "price": row.price,
            "energy_class": row.energy_class,
            "year_built": row.year_built,
            "renovated_year": row.renovated_year,
            "area_median_ppm2": area_median_ppm2,
        }
    )
    d = {
        "archetype": investment_archetype(row.year_built, row.renovated_year, row.energy_class),
        "id": row.id,
        "source": row.source,
        "consistency_flags": _consistency,
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
        "region": region_of(row.search_area),
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
        "net_yield": row.net_yield,
        "rent_estimated": bool(row.rent_estimated),
        "location_precision": row.location_precision,
        "data_missing": missing,
        "data_complete": not missing,
        "predicted_price": row.predicted_price,
        "value_gap_pct": row.value_gap_pct,
        "value_confident": value_confident,
        "listed_date": row.listed_date,
        "days_on_market": days_on_market,
        "suggested_offer": deal.suggested_offer if deal else None,
        "offer_discount_pct": deal.discount_pct if deal else None,
        "deal_thesis": deal.thesis if deal else None,
        "data_confidence": _confidence,
        "deal_grade": _grade.grade,
        "deal_grade_reason": _grade.rationale,
        "yield_on_offer": _yield_on_offer(
            deal.suggested_offer if deal else None,
            (row.est_monthly_rent * 12) if row.est_monthly_rent else None,
            row.area_m2,
            bool(row.is_private_seller),
        ),
        "image_url": row.image_url,
        "score": row.score,
        "negotiation_score": row.negotiation_score,
        "is_opportunity": row.is_opportunity,
        "excluded": row.excluded,
        "exclusion_reason": row.exclusion_reason,
        "status": row.status,
        "is_watched": row.is_watched,
        "first_seen": row.first_seen,
        "last_seen": row.last_seen,
    }
    # Data-quality guards: flag DATA ERRORS (whole building priced as a flat, future year,
    # off-by-10x €/m²/yield) BEFORE nulling the future years below, so the future-year guard
    # can still see them. is_suspect demotes the listing in ranking and shows a badge — it is
    # never deleted (a human verifies on the portal).
    d["data_quality_flags"] = data_quality_flags(d)
    d["is_suspect"] = bool(d["data_quality_flags"])
    # Null any future build/reno year so the card/table never SHOW it and the recommendation
    # doesn't trust it. (Ingest guards new data at the source in normalize.py; this handles
    # rows already stored with a future year.)
    d["year_built"], d["renovated_year"] = clean_future_years(row.year_built, row.renovated_year)
    d["building_age"] = _building_age(d["year_built"], d["renovated_year"])
    d["is_unfinished"] = bool(row.is_unfinished)
    d["page_checked"] = row.detail_checked_at is not None
    d["is_fresh"] = True  # load_listings re-derives it against the whole loaded set
    d["strategy_tags"] = _strategy_tags(d)
    rec = _recommend(d)
    d["rec_verdict"] = rec.verdict
    d["rec_headline"] = rec.headline
    d["rec_play"] = rec.play
    d["rec_rationale"] = rec.rationale
    d["rec_risks"] = rec.risks
    return d


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


def _cut_counts(session, ids: list[int]) -> dict[int, int]:
    """Number of downward price steps in each listing's history (for the deal thesis)."""
    out: dict[int, int] = {}
    if not ids:
        return out
    rows = session.scalars(
        select(PriceHistoryRow)
        .where(PriceHistoryRow.listing_id.in_(ids))
        .order_by(PriceHistoryRow.listing_id, PriceHistoryRow.observed_at)
    ).all()
    prev: dict[int, int] = {}
    for ph in rows:
        last = prev.get(ph.listing_id)
        if last is not None and ph.price < last:
            out[ph.listing_id] = out.get(ph.listing_id, 0) + 1
        prev[ph.listing_id] = ph.price
    return out


def _relist_signature(d: dict):
    """Strong same-flat key, or None when the row is too sparse to safely collapse."""
    price = d.get("price")
    area = d.get("area_m2")
    if not price or not area:  # need both to be confident two rows are one flat
        return None
    return (
        d.get("source"),
        (d.get("neighborhood") or "").strip().lower(),
        int(price),
        round(float(area)),
        d.get("floor"),
        d.get("bedrooms"),
    )


def _collapse_relistings(rows: list[dict]) -> list[dict]:
    """Collapse same-flat relistings into one card.

    XE issues a fresh listing id when an owner re-posts the same flat, which resets the
    portal's days-on-market clock — a distress tell, not two flats. Two active rows with
    the same source, neighborhood, price, area, floor and bedrooms are almost certainly
    the same property, and showing both twice reads as junk data. We keep ONE
    representative — the richest-data record — but anchor its days-on-market to the
    EARLIEST posting (the flat has really been trying to sell that long) and expose a
    ``relist_count`` so the UI can treat repeats as a motivated-seller signal instead of
    silently double-counting inventory.
    """
    groups: dict = {}
    passthrough: list[dict] = []
    for d in rows:
        sig = _relist_signature(d)
        if sig is None:
            passthrough.append(d)
        else:
            groups.setdefault(sig, []).append(d)

    out = list(passthrough)
    for members in groups.values():
        if len(members) == 1:
            out.append(members[0])
            continue
        # Representative = fewest missing fields, then highest data confidence.
        rep = min(
            members,
            key=lambda m: (len(m.get("data_missing") or []), -(m.get("data_confidence") or 0)),
        )
        rep = dict(rep)
        doms = [m.get("days_on_market") for m in members if m.get("days_on_market") is not None]
        if doms:
            rep["days_on_market"] = max(doms)  # oldest posting = true time on market
        dates = [m.get("listed_date") for m in members if m.get("listed_date") is not None]
        if dates:
            rep["listed_date"] = min(dates)
        rep["relist_count"] = len(members)
        rep["is_fresh"] = any(m.get("is_fresh", True) for m in members)
        out.append(rep)
    return out


def _area_median_ppm2(rows) -> dict[str, float]:
    """Median €/m² per search_area — feeds the relative consistency check (a listing under
    half its own area's median is probably a whole building / plot / data error)."""
    import statistics

    by_area: dict[str, list[float]] = {}
    for r in rows:
        if r.price_per_m2 and r.search_area:
            by_area.setdefault(r.search_area, []).append(r.price_per_m2)
    return {a: statistics.median(v) for a, v in by_area.items() if len(v) >= 5}


def load_listings(
    include_excluded: bool = True,
    only_active: bool = True,
    collapse_relistings: bool = True,
) -> list[dict]:
    """Load all listings as dicts, annotated with first_price / price_dropped / is_new.

    ``collapse_relistings`` merges same-flat re-postings into one card (see
    ``_collapse_relistings``); the Debug page turns it off to inspect raw inventory.
    """
    with session_scope() as session:
        stmt = select(ListingRow)
        if only_active:
            stmt = stmt.where(ListingRow.status == "active")
        if not include_excluded:
            stmt = stmt.where(ListingRow.excluded.is_(False))
        rows = session.scalars(stmt).all()
        ids = [r.id for r in rows]
        firsts = _first_prices(session, ids)
        cuts = _cut_counts(session, ids)
        medians = _area_median_ppm2(rows)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        out = []
        for r in rows:
            d = _row_to_dict(
                r,
                firsts.get(r.id),
                num_cuts=cuts.get(r.id, 0),
                area_median_ppm2=medians.get(r.search_area),
            )
            d["is_new"] = r.first_seen is not None and r.first_seen >= cutoff
            out.append(d)
        _annotate_freshness(out)
        if collapse_relistings:
            out = _collapse_relistings(out)
        # Honest market-position ranks (price and yield percentile vs comparable active
        # listings, same area + size band) need the WHOLE pool, so they're computed once
        # here rather than per-row above. strategy_tags and the BUY/WATCH/PASS
        # recommendation both key off yield_percentile (an "Underpriced" tag, and the BUY
        # yield gate), so both are recomputed after annotation — the per-row versions
        # computed above (before the pool existed) only stand for listings whose peer
        # group didn't qualify anyway.
        annotate_relative_value(out)
        for d in out:
            d["strategy_tags"] = _strategy_tags(d)
            rec = _recommend(d)
            d["rec_verdict"] = rec.verdict
            d["rec_headline"] = rec.headline
            d["rec_play"] = rec.play
            d["rec_rationale"] = rec.rationale
            d["rec_risks"] = rec.risks
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
        medians = _area_median_ppm2(rows)
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
                d = _row_to_dict(r, firsts.get(r.id), area_median_ppm2=medians.get(r.search_area))
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


def load_rent_comp_rows() -> list[dict]:
    """Every persisted rent comparable as ``{area, neighborhood, rent_per_m2, samples}``
    (``samples`` 0 = count not recorded). Feeds ``area_insights.rank_areas``."""
    with session_scope() as session:
        return [
            {
                "area": r.area,
                "neighborhood": r.neighborhood,
                "rent_per_m2": r.rent_per_m2,
                "samples": r.samples,
            }
            for r in session.scalars(select(RentCompRow)).all()
        ]


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

    # Report the HONEST out-of-sample cv_r2 (not the optimistic in-sample r2), so the UI
    # never overstates how much to trust a fair-value figure.
    areas = {
        area: {
            "r2": round(m.cv_r2, 3),
            "residual_std": m.residual_std,
            "is_confident": m.is_confident,
            "n": m.n_samples,
        }
        for area, m in models.items()
    }
    total_n = sum(m.n_samples for m in models.values()) or 1
    # Sample-weighted mean out-of-sample R² and a conservative (widest) residual band.
    overall = {
        "r2": round(sum(m.cv_r2 * m.n_samples for m in models.values()) / total_n, 3),
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
