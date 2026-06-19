"""Pipeline orchestration: collect -> normalize -> enrich -> dedup -> store -> score.

Fail-soft throughout: one bad listing (or one dead portal) logs and is skipped;
the run continues. Idempotent: running twice in a day adds no duplicate history
rows (the upsert appends history only on real change).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select

from .collectors import ALL_COLLECTORS
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
from .scoring import compute_market_stats, score

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


def run(
    strategy: Strategy | None = None,
    collectors: list[Collector] | None = None,
    use_network: bool = True,
    observed_at: datetime | None = None,
) -> dict:
    """Execute one full pipeline pass. Returns a small run summary."""
    strategy = strategy or load_strategy()
    now = observed_at or datetime.utcnow()
    init_db()

    if collectors is None:
        collectors = [cls(strategy) for cls in ALL_COLLECTORS]

    # 1. Collect + normalize.
    raws = _collect_all(collectors)
    listings: list[Listing] = []
    for raw in raws:
        lst = normalize(raw, now=now)
        if lst is not None:
            listings.append(lst)

    # 2. Enrich (network steps degrade gracefully). Fail-soft per listing.
    enriched: list[Listing] = []
    with session_scope() as session:
        # First pass to build rent comps from any listed rents.
        prelim_stats = compute_market_stats(listings)
        for lst in listings:
            try:
                n_stats = prelim_stats.by_neighborhood.get(lst.neighborhood or "")
                median_rent = n_stats.median_rent_per_m2 if n_stats else None
                enriched.append(
                    enrich_listing(
                        lst,
                        median_rent_per_m2=median_rent,
                        session=session,
                        use_network=use_network,
                    )
                )
            except Exception as exc:
                logger.warning("enrich failed for %s: %s", lst.dedup_key, exc)
                enriched.append(lst)

    # 3. Dedup (keep cheapest canonical per physical property).
    groups = deduplicate(enriched)
    canonical = [g.canonical for g in groups]

    # 4. Store with history + 5. recompute market stats + 6. rescore active listings.
    market_stats = compute_market_stats(canonical)
    seen_keys: set[tuple[str, str]] = set()
    stored = 0
    with session_scope() as session:
        for lst in canonical:
            try:
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

        gone = mark_unseen_as_gone(session, seen_keys, observed_at=now)

    summary = {
        "raw": len(raws),
        "normalized": len(listings),
        "deduped": len(canonical),
        "stored": stored,
        "marked_gone": gone,
    }
    logger.info("pipeline run summary: %s", summary)
    return summary


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
        rows = session.scalars(select(ListingRow)).all()
        listings = [_row_to_listing(r) for r in rows]
        market_stats = compute_market_stats(listings)
        for row, lst in zip(rows, listings, strict=True):
            first_price = _first_price(session, row.id)
            scored = score(lst, market_stats, strategy, first_price=first_price)
            row.score = scored.score
            row.is_opportunity = scored.is_opportunity
            row.excluded = scored.excluded
            row.exclusion_reason = scored.exclusion_reason
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
