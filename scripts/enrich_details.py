"""Recover DEPTH for card-only listings — fetch detail pages to fill energy/year/date.

The all-Athens breadth sweep collected ~9k listings card-only (fast, no per-listing
detail fetch), so most lack energy_class, year_built, a real listed_date, and an exact
location. Quality-first scoring and the hedonic model both depend on those, so this
script re-visits detail pages for the rows that are missing them and back-fills:

    energy_class, year_built, bedrooms, heating, exact lat/lng, listed_date,
    and description-derived rented/private/rent.

XE rate-limits per IP, but DETAIL pages tolerate a steady ~5 s cadence cleanly (measured:
25/25 fetched with zero 403s at 4-7 s spacing) — the earlier blocks came from fetching too
fast (<3.5 s), not a hard cap. So a full-depth pass is HOURS, not weeks: ~650 pages/hour,
and only the top-scored listings users actually see need enriching. The run is capped
(--limit) and fully resumable: it always picks the still-incomplete rows, highest score
first, and cached detail pages are instant.

Usage (safe cadence — keep min ≥ 4 s to avoid rate-limiting):
    SCRAPE_REQUEST_MIN_S=4 SCRAPE_REQUEST_MAX_S=7 python scripts/enrich_details.py --limit 1500
"""

from __future__ import annotations

import argparse
import logging
import random
import time
from datetime import datetime

from sqlalchemy import or_, select

from scout.collectors.parse_helpers import parse_private_seller, parse_rent
from scout.collectors.xe import (
    XeCollector,
    parse_detail_coordinates,
    parse_detail_jsonld,
    parse_listed_date,
)
from scout.config import get_settings, load_strategy
from scout.db import init_db, session_scope
from scout.models import ListingRow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("enrich_details")


def _incomplete_xe_rows(session, limit: int) -> list[ListingRow]:
    """Active XE rows still missing depth fields, best (highest score) first.

    Rows whose detail page was ALREADY fetched+parsed (detail_checked_at set) are
    excluded: some pages genuinely never state energy/year, so re-selecting them every
    run just churns the queue on unfillable rows while never-fetched ones wait."""
    stmt = (
        select(ListingRow)
        .where(ListingRow.source == "xe", ListingRow.status == "active")
        .where(ListingRow.detail_checked_at.is_(None))
        .where(
            or_(
                ListingRow.energy_class.is_(None),
                ListingRow.year_built.is_(None),
                ListingRow.listed_date.is_(None),
            )
        )
        .order_by(ListingRow.score.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def enrich(limit: int, rescore: bool = True, max_fetches: int | None = None) -> dict:
    """``max_fetches`` bounds LIVE network fetches only — cached pages replay free and
    unlimited. This keeps a run's wall-clock inside a predictable window regardless of
    how much cache-stamping backlog it clears first."""
    init_db()
    settings = get_settings()
    collector = XeCollector(load_strategy())
    session_http = collector._new_session()

    filled = {"energy_class": 0, "year_built": 0, "listed_date": 0, "coords": 0}
    processed = 0
    fetched = 0
    # Circuit-breaker: XE redirects removed ads AND (when it has bot-flagged the IP) live
    # ads. A redirect streak is ambiguous — the never-enriched tail of the queue is where
    # stale listings cluster, so 10+ genuinely-dead ads in a row is common there. The
    # discriminator is a CANARY: a known-live ad (served JSON-LD recently). On a streak,
    # fetch the canary — 200 means the client is fine and the streak is real dead ads
    # (keep the stamps, continue); a redirect on the canary means WE are blocked (revert
    # the streak's stamps and stop).
    _GONE_STREAK_LIMIT = 10
    gone_streak: list = []
    with session_scope() as db:
        rows = _incomplete_xe_rows(db, limit)
        log.info("enriching %d incomplete XE listings", len(rows))
        canaries = list(
            db.scalars(
                select(ListingRow.url)
                .where(
                    ListingRow.source == "xe",
                    ListingRow.status == "active",
                    ListingRow.energy_class.is_not(None),
                    ListingRow.listed_date.is_not(None),
                )
                .order_by(ListingRow.first_seen.desc())
                .limit(2)
            ).all()
        )
        ttl = settings.scrape_cache_ttl_minutes
        for row in rows:
            processed += 1
            # Periodic commit: the sandbox restarts every few hours, and a multi-hour run
            # that only commits at scope exit loses ALL its fills/stamps to a restart —
            # each resume then re-pays the whole dead-ad tail. Committing every 100 rows
            # makes an interruption lose minutes of work, not hours.
            if processed % 100 == 0:
                db.commit()
            # A page already cached on disk needs no network round-trip — so don't pay the
            # polite sleep for it. This makes resumed runs fly through the pages a previous
            # run already fetched, only spacing the genuinely new network fetches.
            cached = collector._read_cache(row.url, ttl)
            was_cached = cached is not None and collector._has_jsonld(cached)
            html = collector._fetch_detail(session_http, row.url)
            # Polite spacing after EVERY live network attempt — successful or not. Sleeping
            # only on success let a redirect/failure streak fire back-to-back (10 requests
            # in one second in the 2026-07-16 log), which instantly re-triggered XE's block.
            if not was_cached:
                fetched += 1
                if max_fetches is not None and fetched >= max_fetches:
                    log.info("max_fetches=%d reached — stopping this run", max_fetches)
                    break
                time.sleep(
                    random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s)
                )
            if html is None:
                # Transient failure (block page / network) — leave the row in the queue
                # for a later run; stamping here would permanently skip LIVE ads whenever
                # XE temporarily blocks the IP.
                continue
            if not html:
                # "" = the ad redirected — gone, IF we're not in a block window. Stamp it
                # out of the queue, but track the streak so a block window can be undone.
                row.detail_checked_at = datetime.utcnow()
                gone_streak.append(row)
                if len(gone_streak) >= _GONE_STREAK_LIMIT:
                    # Ambiguous streak — ask the canary whether the client is healthy.
                    canary_ok = False
                    for cu in canaries:
                        time.sleep(
                            random.uniform(
                                settings.scrape_request_min_s, settings.scrape_request_max_s
                            )
                        )
                        if collector._fetch_detail(session_http, cu):
                            canary_ok = True
                            break
                    if canary_ok:
                        log.info(
                            "%d consecutive redirects but the canary serves fine — a real "
                            "dead-ad cluster; stamps kept, continuing.",
                            len(gone_streak),
                        )
                        gone_streak.clear()
                        continue
                    for r in gone_streak:
                        r.detail_checked_at = None
                    log.warning(
                        "%d consecutive redirects AND the canary redirects too — IP block "
                        "window. Reverted those stamps and stopping this run.",
                        len(gone_streak),
                    )
                    break
                continue
            gone_streak.clear()
            try:
                detail = parse_detail_jsonld(html)
            except Exception as exc:
                log.warning("parse error for %s: %s", row.url, exc)
                detail = {}
            # Stamp the check regardless of what filled: a parsed page that lacks
            # energy/year is DONE, not pending — it must leave the enrichment queue.
            row.detail_checked_at = datetime.utcnow()
            if row.energy_class is None and detail.get("energy_class"):
                row.energy_class = detail["energy_class"]
                filled["energy_class"] += 1
            if row.year_built is None and detail.get("year_built"):
                row.year_built = detail["year_built"]
                filled["year_built"] += 1
            if row.renovated_year is None and detail.get("renovated_year"):
                row.renovated_year = detail["renovated_year"]
            if row.bedrooms is None and detail.get("bedrooms"):
                row.bedrooms = detail["bedrooms"]
            if not row.heating and detail.get("heating"):
                row.heating = detail["heating"]
            if row.listed_date is None:
                posted = parse_listed_date(html)
                if posted is not None:
                    row.listed_date = posted
                    filled["listed_date"] += 1
            lat, lng = parse_detail_coordinates(html)
            if lat is not None and lng is not None:
                row.lat, row.lng = lat, lng
                # A detail-page coordinate is the listing's real point — mark it EXACT so
                # the metro signal + map treat it precisely (a card-only row is "approx").
                row.location_precision = "exact"
                filled["coords"] += 1
            desc = detail.get("description")
            if desc:
                rented, rent = parse_rent(desc)
                if rented:
                    row.is_currently_rented = True
                if rent:
                    row.listed_rent = rent
                if parse_private_seller(desc):
                    row.is_private_seller = True
    summary = {"processed": processed, "fetched": fetched, **filled}
    log.info("enrich summary: %s", summary)

    if rescore and processed:
        from scout.pipeline import rescore_all

        summary["rescored"] = rescore_all()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=300, help="max listings to enrich this run")
    parser.add_argument(
        "--max-fetches",
        type=int,
        default=None,
        help="stop after this many LIVE fetches (cached replays are free and unbounded)",
    )
    parser.add_argument("--no-rescore", action="store_true")
    args = parser.parse_args()
    summary = enrich(limit=args.limit, rescore=not args.no_rescore, max_fetches=args.max_fetches)
    print(f"Detail enrichment complete: {summary}")


if __name__ == "__main__":
    main()
