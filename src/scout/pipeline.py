"""Pipeline orchestration: collect -> normalize -> enrich -> dedup -> store -> score.

Fail-soft throughout: one bad listing (or one dead portal) logs and is skipped;
the run continues. Idempotent: running twice in a day adds no duplicate history
rows (the upsert appends history only on real change).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select, update

from .collectors import default_collectors
from .collectors.base import Collector
from .config import Strategy, load_strategy
from .db import (
    init_db,
    mark_unseen_as_gone,
    session_scope,
    upsert_listing_with_history,
)
from .dedup import deduplicate
from .enrich import enrich_listing
from .models import Listing, ListingRow, PriceHistoryRow
from .normalize import normalize
from .rent_comps import compute_rent_comps
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


def _fetch_rent_comps(collectors: Iterable[Collector]) -> dict[str, float]:
    """Scrape the area's rental market from any collector that supports it and reduce it
    to neighbourhood → median €/m²/month. Fail-soft: returns {} on any failure so yield
    falls back to sale-listing rents / the configured baseline."""
    rows: list[dict] = []
    for collector in collectors:
        fetch = getattr(collector, "collect_rent_rows", None)
        if not callable(fetch):
            continue
        try:
            rows.extend(fetch())
        except Exception as exc:
            logger.warning("rent comps: %s failed: %s", collector.source, exc)
    comps = compute_rent_comps(rows)
    if comps:
        logger.info(
            "rent comps: %d neighbourhoods, overall %.1f €/m²/mo",
            len(comps) - 1,
            comps.get("__overall__", 0.0),
        )
    return comps


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
            listings.append(lst)
    # Portals that produced *usable* listings this run. Only these are eligible for
    # retirement below, so a portal that returned nothing — or only junk that failed
    # to normalize — never wipes its previously-collected listings.
    active_sources = {lst.source for lst in listings}

    # 1b. Real rent comparables: scrape the area's RENTAL market so gross yield uses an
    # actual local €/m²/month median per neighbourhood, not a flat guess. Fail-soft.
    rent_comps: dict[str, float] = {}
    if use_network:
        rent_comps = _fetch_rent_comps(collectors)

    # 2. Enrich (network steps degrade gracefully). Fail-soft per listing.
    enriched: list[Listing] = []
    with session_scope() as session:
        # Fallback rent comps from any sale listings that stated a rent (rare).
        prelim_stats = compute_market_stats(listings)
        for lst in listings:
            try:
                # Prefer the real rental-market median for this neighbourhood/area.
                median_rent = rent_comps_for(rent_comps, lst.neighborhood)
                if not median_rent:
                    n_stats = prelim_stats.by_neighborhood.get(lst.neighborhood or "")
                    median_rent = n_stats.median_rent_per_m2 if n_stats else None
                # Fall back to the configured baseline so yield is always computable.
                if not median_rent:
                    median_rent = strategy.search.est_rent_eur_per_m2
                # SAVEPOINT per listing: enrich_listing writes the geocode cache via
                # session.flush(); a failed flush (e.g. a duplicate-query race) would
                # otherwise poison the whole session. Isolating it here means one bad
                # geocode can't crash enrichment for the rest of the batch.
                with session.begin_nested():
                    result = enrich_listing(
                        lst,
                        median_rent_per_m2=median_rent,
                        session=session,
                        use_network=use_network,
                    )
                enriched.append(result)
            except Exception as exc:
                logger.warning("enrich failed for %s: %s", lst.dedup_key, exc)
                enriched.append(lst)

    # 3. Dedup (keep cheapest canonical per physical property).
    groups = deduplicate(enriched)
    canonical = [g.canonical for g in groups]

    # 3b. Hedonic valuation: fit a fair-price model PER AREA and annotate each listing
    # with predicted_price + value_gap_pct. This is what lets scoring tell a genuine
    # bargain (priced below what its own attributes justify) from a flat that is merely
    # cheap because it's old/small/low. Per-area fits are far more accurate than one
    # pooled model (R²≈0.7-0.8 vs ≈0.3). Fails soft: too few comps → the undervaluation
    # signal falls back to the naive €/m²-vs-median.
    val_models = fit_and_apply_by_area(canonical)
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
    seen_keys: set[tuple[str, str]] = {
        (lst.source, lst.source_id) for g in groups for lst in [g.canonical, *g.duplicates]
    }
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
        for lst in canonical:
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
    }
    logger.info("pipeline run summary: %s", summary)
    return summary


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


def rescore_all(strategy: Strategy | None = None) -> int:
    """Re-score every active listing from the current DB (used by the UI Strategy editor)."""
    strategy = strategy or load_strategy()
    with session_scope() as session:
        # Active rows only: gone listings must not skew the medians the UI scores
        # against (the pipeline computes stats over active/canonical listings).
        rows = session.scalars(select(ListingRow).where(ListingRow.status == "active")).all()
        listings = [_row_to_listing(r) for r in rows]
        # Refit the hedonic model PER AREA over the current active set so the
        # undervaluation signal (and the Fair value / Value gap the UI shows) reflect the
        # live market with per-submarket accuracy.
        fit_and_apply_by_area(listings)
        market_stats = compute_market_stats(listings)
        for row, lst in zip(rows, listings, strict=True):
            first_price = _first_price(session, row.id)
            scored = score(lst, market_stats, strategy, first_price=first_price)
            row.score = scored.score
            row.is_opportunity = scored.is_opportunity
            row.excluded = scored.excluded
            row.exclusion_reason = scored.exclusion_reason
            row.predicted_price = lst.predicted_price
            row.value_gap_pct = lst.value_gap_pct
        return len(rows)


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
