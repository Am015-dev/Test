"""Recover DEPTH for card-only listings — fetch detail pages to fill energy/year/date.

The all-Athens breadth sweep collected ~9k listings card-only (fast, no per-listing
detail fetch), so most lack energy_class, year_built, a real listed_date, and an exact
location. Quality-first scoring and the hedonic model both depend on those, so this
script re-visits detail pages for the rows that are missing them and back-fills:

    energy_class, year_built, bedrooms, heating, exact lat/lng, listed_date,
    and description-derived rented/private/rent.

XE rate-limits per IP, so requests are spaced (SCRAPE_REQUEST_MIN_S/MAX_S) and the run is
capped (--limit) and fully resumable: it always picks the still-incomplete rows, highest
score first (enrich what users see soonest), and cached detail pages are instant. Run it
repeatedly (or from cron) to deepen coverage over time.

Usage:
    python scripts/enrich_details.py --limit 300
"""

from __future__ import annotations

import argparse
import logging
import random
import time

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
    """Active XE rows still missing depth fields, best (highest score) first."""
    stmt = (
        select(ListingRow)
        .where(ListingRow.source == "xe", ListingRow.status == "active")
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


def enrich(limit: int, rescore: bool = True) -> dict:
    init_db()
    settings = get_settings()
    collector = XeCollector(load_strategy())
    session_http = collector._new_session()

    filled = {"energy_class": 0, "year_built": 0, "listed_date": 0, "coords": 0}
    processed = 0
    with session_scope() as db:
        rows = _incomplete_xe_rows(db, limit)
        log.info("enriching %d incomplete XE listings", len(rows))
        for row in rows:
            processed += 1
            html = collector._fetch_detail(session_http, row.url)
            if not html:
                continue
            try:
                detail = parse_detail_jsonld(html)
            except Exception as exc:
                log.warning("parse error for %s: %s", row.url, exc)
                detail = {}
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
            # Polite spacing between detail fetches (XE rate-limits per IP). Cached pages
            # still pass through here; the small sleep keeps the crawl well under the limit.
            time.sleep(random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s))
    summary = {"processed": processed, **filled}
    log.info("enrich summary: %s", summary)

    if rescore and processed:
        from scout.pipeline import rescore_all

        summary["rescored"] = rescore_all()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=300, help="max listings to enrich this run")
    parser.add_argument("--no-rescore", action="store_true")
    args = parser.parse_args()
    summary = enrich(limit=args.limit, rescore=not args.no_rescore)
    print(f"Detail enrichment complete: {summary}")


if __name__ == "__main__":
    main()
