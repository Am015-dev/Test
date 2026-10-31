"""Pipeline orchestration: collect -> normalize -> enrich -> dedup -> store -> score.

Fail-soft throughout: one bad listing (or one dead portal) logs and is skipped;
the run continues. Idempotent: running twice in a day adds no duplicate history
rows (the upsert appends history only on real change).

Rentals. A collector with ``collect_rentals()`` (XE) also yields full rental cards
(``listing_type="rent"``, price = monthly rent). They are stored in the same ``listing``
table, per area, under the same upsert/history rules, and retired in their own pass
(``mark_unseen_as_gone(listing_type="rent")``), so a failed rental search never retires
sales and vice versa. Rentals are kept out of everything sale-side by ONE mechanism:
``scoring.score`` returns them excluded with reason ``"rent"`` (score 0, never an
opportunity), and they are never passed to the sale market stats, the hedonic valuation
or the sale dedup. After the rentals are stored, ``rent_comp`` is recomputed for the area
from every rental seen in the last ``rent_comps.WINDOW_DAYS`` days
(``rent_comps.recompute_from_stored``), and the sale yields use those medians.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select, update

from . import negotiation
from .collectors import default_collectors
from .collectors.base import Collector
from .config import Strategy, load_strategy
from .db import (
    get_engine,
    init_db,
    mark_unseen_as_gone,
    session_scope,
    upsert_listing_with_history,
)
from .dedup import deduplicate
from .enrich import enrich_listing
from .enrich import gross_yield as _gross_yield
from .finance import net_yield as _net_yield_after_costs
from .models import Listing, ListingRow, PriceHistoryRow
from .normalize import normalize
from .rent_comps import OVERALL_KEY, load_rent_comps
from .rent_comps import rent_for as rent_comps_for
from .scoring import compute_market_stats, score
from .valuation import fit_and_apply_by_area

logger = logging.getLogger(__name__)


def _collect_all(collectors: Iterable[Collector]) -> list[dict]:
    """Run each collector one at a time (polite), collecting raw dicts. Fail-soft."""
    raws: list[dict] = []
    for collector in collectors:
        try:
            count = 0
            for raw in collector.collect():
                raws.append(raw)
                count += 1
            logger.info("%s: collected %d raw listings", collector.source, count)
        except Exception as exc:  # one dead portal must not kill the run
            logger.warning("collector %s failed: %s", collector.source, exc)
    return raws


def _collect_rentals(collectors: Iterable[Collector]) -> tuple[list[dict], set[str]]:
    """Rental cards from every collector that has ``collect_rentals``. Fail-soft per
    collector. Returns the raws and the sources that were asked (a source that raised is
    left out, so its stored rentals are not retired)."""
    raws: list[dict] = []
    asked: set[str] = set()
    for collector in collectors:
        fetch = getattr(collector, "collect_rentals", None)
        if not callable(fetch):
            continue
        try:
            got = [{**raw, "listing_type": "rent"} for raw in fetch()]
        except Exception as exc:
            logger.warning("rentals: %s failed: %s", collector.source, exc)
            continue
        raws.extend(got)
        asked.add(collector.source)
        logger.info("%s: collected %d raw rentals", collector.source, len(got))
    return raws, asked


def _enrich_all(listings: list[Listing], rent_per_m2, use_network: bool) -> list[Listing]:
    """Enrich each listing (fail-soft, SAVEPOINT per listing). ``rent_per_m2(lst)`` gives
    the €/m²/month the sale yield is estimated from. Rentals keep their own €/m² (=
    monthly rent per m²) and get no rent estimate or yield: they are not investments."""
    enriched: list[Listing] = []
    with session_scope() as session:
        for lst in listings:
            is_rent = lst.listing_type == "rent"
            try:
                # SAVEPOINT per listing: enrich_listing writes the geocode cache via
                # session.flush(); a failed flush (e.g. a duplicate-query race) would
                # otherwise poison the whole session. Isolating it here means one bad
                # geocode can't crash enrichment for the rest of the batch.
                with session.begin_nested():
                    result = enrich_listing(
                        lst,
                        median_rent_per_m2=None if is_rent else rent_per_m2(lst),
                        session=session,
                        use_network=use_network,
                    )
            except Exception as exc:
                logger.warning("enrich failed for %s: %s", lst.dedup_key, exc)
                result = lst
            if is_rent:
                result.est_monthly_rent = result.gross_yield = result.net_yield = None
            enriched.append(result)
    return enriched


def run(
    strategy: Strategy | None = None,
    collectors: list[Collector] | None = None,
    use_network: bool = True,
    observed_at: datetime | None = None,
    area: str | None = None,
) -> dict:
    """Execute one full pipeline pass. Returns a small run summary.

    When ``area`` is set, this pass is scoped to that municipality: collected
    listings are tagged with it and only that area's listings are eligible for
    retirement, so concurrent per-area workers don't retire each other's data.
    """
    strategy = strategy or load_strategy()
    now = observed_at or datetime.utcnow()
    init_db()

    # A run only ever scrapes ONE municipality (the collector uses it), so retirement
    # must be scoped to it — otherwise an unscoped run() would retire every *other*
    # area's still-live listings. Default to the strategy's municipality when no area
    # was given, so the boot/refresh/cron run() paths are scoped too, not just workers.
    #
    # Only a truly unscoped/default run (no `area` given) owns the one-time backfill of
    # legacy NULL-tagged rows below. `run_for_area` passes area=area AND sets
    # municipality=area, so gating the backfill on "effective_area == municipality"
    # would be true for every worker — letting any area steal-and-retire another area's
    # NULL-tagged live rows. Gate on `area is None` (captured before defaulting) instead.
    is_default_run = area is None
    effective_area = area or strategy.search.municipality

    if collectors is None:
        collectors = default_collectors(strategy)

    # 1. Collect + normalize.
    raws = _collect_all(collectors)
    listings: list[Listing] = []
    for raw in raws:
        lst = normalize(raw, now=now)
        if lst is not None:
            # Tag the area NOW (not only at store time) so enrichment's municipality-
            # centroid location fallback can use it for card-only listings.
            lst.search_area = effective_area
            listings.append(lst)
    # Portals that produced *usable* listings this run. Only these are eligible for
    # retirement below, so a portal that returned nothing — or only junk that failed
    # to normalize — never wipes its previously-collected listings.
    active_sources = {lst.source for lst in listings}

    # 1b. Rentals: full rental cards, stored like sales (see the module docstring).
    rent_raws, _ = _collect_rentals(collectors)
    rentals: list[Listing] = []
    for raw in rent_raws:
        lst = normalize(raw, now=now)
        if lst is not None and lst.listing_type == "rent":
            lst.search_area = effective_area
            rentals.append(lst)
    rent_sources = {lst.source for lst in rentals}
    rentals = _enrich_all(rentals, lambda _lst: None, use_network)
    rent_stored, rent_gone = _store_rentals(rentals, rent_sources, effective_area, now, strategy)

    # 1c. Rent comps from the STORED rentals of the last 60 days (this run's included), so
    # the yield uses a real local €/m²/month median per neighbourhood. When the area has no
    # recent rentals the comps stored earlier stand (fail-soft, never wiped).
    from .rent_comps import recompute_from_stored

    rent_comps: dict[str, float] = {}
    try:
        rent_comps = recompute_from_stored(effective_area, now=now)
    except Exception as exc:  # comps must never break a run
        logger.warning("rent comps: recompute failed for %s: %s", effective_area, exc)
    if not rent_comps:
        try:
            rent_comps = load_rent_comps().get(effective_area, {})
        except Exception:
            rent_comps = {}

    # 2. Enrich (network steps degrade gracefully). Fail-soft per listing.
    # Fallback rent comps from any sale listings that stated a rent (rare).
    prelim_stats = compute_market_stats(listings)

    def _sale_rent(lst: Listing) -> float:
        # Prefer the real rental-market median for this neighbourhood/area so the rent
        # ESTIMATE tracks the local market (not a flat guess). It is still an estimate for
        # this listing — honesty is set from its own listed_rent only.
        median_rent = rent_comps_for(rent_comps, lst.neighborhood)
        if not median_rent:
            n_stats = prelim_stats.by_neighborhood.get(lst.neighborhood or "")
            median_rent = n_stats.median_rent_per_m2 if n_stats else None
        # Fall back to the configured baseline so yield is always computable.
        return median_rent or strategy.search.est_rent_eur_per_m2

    enriched = _enrich_all(listings, _sale_rent, use_network)

    # 3. Dedup (cheapest canonical per physical property) — used ONLY so market stats
    # count each flat once. Every portal's listing is still stored: the fuzzy match here
    # (m² ±3, price ±5 %, any shared area word; no floor/year) is too loose to drop data
    # on, and the UI groups cross-portal copies with the stricter ``market_intel.twins``
    # (same municipality, m², floor, year, price ±10 %), so a buyer sees «και σε N ακόμα
    # πηγές» instead of losing the second portal's link.
    groups = deduplicate(enriched)
    canonical = [g.canonical for g in groups]
    to_store = [lst for g in groups for lst in (g.canonical, *g.duplicates)]

    # 3b. Hedonic valuation: fit a fair-price model PER AREA and annotate each listing
    # with predicted_price + value_gap_pct. This is what lets scoring tell a genuine
    # bargain (priced below what its own attributes justify) from a flat that is merely
    # cheap because it's old/small/low. Per-area fits are far more accurate than one
    # pooled model (R²≈0.7-0.8 vs ≈0.3). Fails soft: too few comps → the undervaluation
    # signal falls back to the naive €/m²-vs-median.
    val_models = fit_and_apply_by_area(to_store)
    for area, m in val_models.items():
        logger.info(
            "valuation model [%s]: %d comps, R²=%.2f, ±%.0f%% band",
            area or "(default)",
            m.n_samples,
            m.r2,
            (2.718281828**m.residual_std - 1) * 100,
        )

    # 4. Store with history + 5. recompute market stats + 6. rescore active listings.
    market_stats = compute_market_stats(canonical)
    # Every collected listing counts as "seen" — including the non-canonical
    # duplicates — so a run where the cheaper source flips canonical doesn't leave
    # the other source's still-live row looking unseen and retire it.
    seen_keys: set[tuple[str, str]] = {(lst.source, lst.source_id) for lst in to_store}
    stored = 0
    with session_scope() as session:
        # One-time backfill: rows created before per-area tagging have search_area
        # NULL. They all predate multi-area support, so they belong to the default
        # municipality — tag them on its run so scoped retirement can reach them
        # (otherwise they'd stay 'active' forever). No-op once none remain.
        if is_default_run:
            session.execute(
                update(ListingRow)
                .where(ListingRow.search_area.is_(None))
                .values(search_area=effective_area)
            )
        for lst in to_store:
            try:
                # SAVEPOINT per listing so a single failed flush (a UNIQUE/NOT NULL
                # violation, a cross-area duplicate-key race, an oversized field) rolls
                # back ONLY this listing. Without it the failed flush leaves the whole
                # session in "pending rollback", so every later item AND the final
                # commit raise too — turning one bad row into a full-run rollback and an
                # uncaught crash, the opposite of the documented fail-soft behavior.
                with session.begin_nested():
                    lst.search_area = effective_area
                    row = upsert_listing_with_history(session, lst, observed_at=now)
                    seen_keys.add((lst.source, lst.source_id))
                    first_price = _first_price(session, row.id)
                    scored = score(lst, market_stats, strategy, first_price=first_price)
                    row.score = scored.score
                    row.is_opportunity = scored.is_opportunity
                    row.excluded = scored.excluded
                    row.exclusion_reason = scored.exclusion_reason
                    row.predicted_price = lst.predicted_price
                    row.value_gap_pct = lst.value_gap_pct
                    hist = [
                        (p.observed_at, p.price)
                        for p in session.scalars(
                            select(PriceHistoryRow)
                            .where(PriceHistoryRow.listing_id == row.id)
                            .order_by(PriceHistoryRow.observed_at)
                        ).all()
                    ]
                    row.negotiation_score = negotiation.analyze(
                        price_history=hist,
                        first_seen=row.first_seen,
                        now=now,
                        current_price=row.price,
                        ppm2=lst.price_per_m2,
                        area_median_ppm2=market_stats.price_per_m2_median_for(lst.neighborhood),
                        is_private_seller=bool(lst.is_private_seller),
                        listed_date=lst.listed_date,
                    ).score
                stored += 1
            except Exception as exc:
                logger.warning("store/score failed for %s: %s", lst.dedup_key, exc)

        # Retirement runs on its own SAVEPOINT and try/except: a failure here (or a
        # session poisoned despite the guards above) degrades to "retired nothing this
        # pass" instead of rolling back every listing just stored and crashing the run.
        try:
            with session.begin_nested():
                gone = mark_unseen_as_gone(
                    session,
                    seen_keys,
                    observed_at=now,
                    active_sources=active_sources,
                    area=effective_area,
                    listing_type="sale",
                )
        except Exception as exc:
            logger.warning("retirement pass failed: %s", exc)
            gone = 0

    summary = {
        "raw": len(raws),
        "normalized": len(listings),
        "deduped": len(canonical),
        "stored": stored,
        "marked_gone": gone,
        "rentals": len(rentals),
        "rentals_stored": rent_stored,
        "rentals_gone": rent_gone,
        "rent_comps": len(rent_comps),
    }
    logger.info("pipeline run summary: %s", summary)
    return summary


def _store_rentals(
    rentals: list[Listing],
    rent_sources: set[str],
    area: str,
    now: datetime,
    strategy: Strategy,
) -> tuple[int, int]:
    """Upsert rentals with history (SAVEPOINT each) and retire this area's unseen rentals
    from the portals that returned rentals. Every rental is "scored" through
    ``scoring.score``, which excludes it with reason ``"rent"``. Returns (stored, gone)."""
    stored = gone = 0
    seen: set[tuple[str, str]] = set()
    empty_stats = compute_market_stats([])
    with session_scope() as session:
        for lst in rentals:
            try:
                with session.begin_nested():
                    lst.search_area = area
                    row = upsert_listing_with_history(session, lst, observed_at=now)
                    seen.add((lst.source, lst.source_id))
                    scored = score(lst, empty_stats, strategy)
                    row.score = scored.score
                    row.is_opportunity = scored.is_opportunity
                    row.excluded = scored.excluded
                    row.exclusion_reason = scored.exclusion_reason
                    row.negotiation_score = 0.0
                stored += 1
            except Exception as exc:
                logger.warning("store failed for rental %s: %s", lst.dedup_key, exc)
        try:
            with session.begin_nested():
                gone = mark_unseen_as_gone(
                    session,
                    seen,
                    observed_at=now,
                    active_sources=rent_sources,
                    area=area,
                    listing_type="rent",
                )
        except Exception as exc:
            logger.warning("rental retirement pass failed: %s", exc)
            gone = 0
    return stored, gone


def run_for_area(
    area: str,
    strategy: Strategy | None = None,
    use_network: bool = True,
    observed_at: datetime | None = None,
) -> dict:
    """Run the pipeline scoped to a single municipality (one worker job).

    Builds a per-area copy of the strategy (only the municipality differs) so the XE
    collector resolves that area's geo_place_id; everything else — scoring thesis,
    filters, weights — is shared across areas.
    """
    strategy = strategy or load_strategy()
    area_strategy = strategy.model_copy(deep=True)
    area_strategy.search.municipality = area
    return run(strategy=area_strategy, use_network=use_network, observed_at=observed_at, area=area)


def _first_price(session, listing_id: int) -> int | None:
    """The earliest recorded price, enabling the price-drop signal."""
    return session.scalar(
        select(PriceHistoryRow.price)
        .where(PriceHistoryRow.listing_id == listing_id)
        .order_by(PriceHistoryRow.observed_at)
        .limit(1)
    )


def rescore_all(strategy: Strategy | None = None, chunk: int = 2000) -> int:
    """Re-score every active listing from the current DB (used by the UI Strategy editor).

    Writes are committed in chunks (``expire_on_commit=False`` so row values survive each
    commit) rather than as one giant transaction — at ~9k listings a single commit held a
    long write lock and blocked the UI; chunking bounds both.
    """
    from sqlalchemy.orm import Session

    strategy = strategy or load_strategy()
    with Session(get_engine(), expire_on_commit=False) as session:
        # Active rows only: gone listings must not skew the medians the UI scores
        # against (the pipeline computes stats over active/canonical listings).
        # Sale rows only: rentals are never scored (their exclusion was set at store time)
        # and must not enter the sale medians or the valuation fit.
        rows = session.scalars(
            select(ListingRow).where(
                ListingRow.status == "active", ListingRow.listing_type == "sale"
            )
        ).all()
        listings = [_row_to_listing(r) for r in rows]
        # Refit the hedonic model PER AREA over the current active set so the
        # undervaluation signal (and the Fair value / Value gap the UI shows) reflect the
        # live market with per-submarket accuracy.
        fit_and_apply_by_area(listings)
        market_stats = compute_market_stats(listings)
        # Persisted real rental comps → a real rent for the yield signal without re-scraping.
        rent_store = load_rent_comps()
        histories = _all_price_histories(session, [r.id for r in rows])
        now = datetime.utcnow()
        for i, (row, lst) in enumerate(zip(rows, listings, strict=True), 1):
            hist = histories.get(row.id, [])
            first_price = hist[0][1] if hist else None
            # Apply a local rent comp when we have one (neighbourhood, else area-wide) so the
            # yield tracks the local rental market instead of a flat €/m² guess. This is still
            # an ESTIMATE for this listing (it has no own rent), so rent_estimated stays True —
            # only a listing's own listed_rent counts as a real, measured rent.
            area_comps = rent_store.get(lst.search_area or "")
            if area_comps and lst.area_m2 and not lst.listed_rent:
                ppm = area_comps.get(lst.neighborhood) or area_comps.get(OVERALL_KEY)
                if ppm:
                    lst.est_monthly_rent = int(round(ppm * lst.area_m2))
                    lst.rent_estimated = True
                    row.est_monthly_rent = lst.est_monthly_rent
                    row.rent_estimated = True
                    row.gross_yield = lst.gross_yield = _gross_yield(
                        lst.est_monthly_rent, lst.price
                    )
            # Recompute net yield from the (now possibly real) rent so the after-cost figure
            # is honest without a re-scrape.
            annual_rent = lst.est_monthly_rent * 12 if lst.est_monthly_rent else None
            lst.net_yield = _net_yield_after_costs(
                lst.price, annual_rent, lst.area_m2, bool(lst.is_private_seller)
            )
            row.net_yield = lst.net_yield
            scored = score(lst, market_stats, strategy, first_price=first_price)
            row.score = scored.score
            row.is_opportunity = scored.is_opportunity
            row.excluded = scored.excluded
            row.exclusion_reason = scored.exclusion_reason
            row.predicted_price = lst.predicted_price
            row.value_gap_pct = lst.value_gap_pct
            # Negotiation / motivated-seller intelligence (the sellable signal).
            neg = negotiation.analyze(
                price_history=hist,
                first_seen=row.first_seen,
                now=now,
                current_price=row.price,
                ppm2=lst.price_per_m2,
                area_median_ppm2=market_stats.price_per_m2_median_for(lst.neighborhood),
                is_private_seller=bool(row.is_private_seller),
                listed_date=row.listed_date,
            )
            row.negotiation_score = neg.score
            if i % chunk == 0:
                session.commit()  # bound the write-lock duration at scale
        session.commit()
        return len(rows)


def _all_price_histories(session, ids: list[int]) -> dict[int, list[tuple]]:
    """Bulk-load {listing_id: [(observed_at, price), ...]} ascending, for negotiation."""
    out: dict[int, list[tuple]] = {}
    if not ids:
        return out
    rows = session.scalars(
        select(PriceHistoryRow)
        .where(PriceHistoryRow.listing_id.in_(ids))
        .order_by(PriceHistoryRow.listing_id, PriceHistoryRow.observed_at)
    ).all()
    for ph in rows:
        out.setdefault(ph.listing_id, []).append((ph.observed_at, ph.price))
    return out


def _row_to_listing(row: ListingRow) -> Listing:
    fields = {k: getattr(row, k) for k in Listing.model_fields if hasattr(row, k)}
    return Listing(**fields)


def main() -> None:
    """Console-script / cron entrypoint."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    summary = run()
    print(f"Pipeline complete: {summary}")


if __name__ == "__main__":
    main()
