"""Backfill ``listed_date`` from detail pages we've ALREADY scraped — no re-scrape.

The answer to "why scrape the past daily?": each XE detail page already carries the
listing's own ``datePosted``, and we have ~2000 of them cached on disk from prior runs.
This one-shot script mines those cached pages for (source_id → posting date) and writes
``listed_date`` onto the matching DB rows, then re-scores so the negotiation / motivated-
seller signal reflects each listing's TRUE market age immediately — retroactively, from
data we already collected, instead of waiting weeks for the daily tracker to accumulate it.

Idempotent: re-running only fills rows still missing a ``listed_date`` (unless
``--force``). Safe to run any time.

Usage:
    python scripts/backfill_listed_date.py [--force] [--no-rescore]
"""

from __future__ import annotations

import argparse
import logging
import re
from html import unescape
from pathlib import Path

from sqlalchemy import select

from scout.collectors.base import RAW_HTML_DIR
from scout.collectors.xe import _ID_RE_D, _ID_RE_U, parse_listed_date
from scout.db import init_db, session_scope
from scout.models import ListingRow

logger = logging.getLogger(__name__)

# The canonical listing URL on a detail page (og:url first, then the JSON-LD "url").
_OG_URL_RE = re.compile(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']')
_JSON_URL_RE = re.compile(r'"url"\s*:\s*"(https://www\.xe\.gr/property/[^"]+)"')


def _source_id_from_html(html: str) -> str | None:
    """The XE source_id (detail UUID or numeric id) from a detail page's canonical URL."""
    m = _OG_URL_RE.search(html) or _JSON_URL_RE.search(unescape(html))
    if not m:
        return None
    url = m.group(1)
    mm = _ID_RE_D.search(url) or _ID_RE_U.search(url)
    return mm.group(1) if mm else None


def scan_cached_dates() -> dict[str, object]:
    """Map ``source_id -> latest datePosted`` across every cached XE detail page.

    When the same listing was cached more than once, keep the LATEST posting date seen
    (a relisting resets datePosted forward; the freshest is the honest current age)."""
    xe_dir = Path(RAW_HTML_DIR) / "xe"
    out: dict[str, object] = {}
    if not xe_dir.exists():
        return out
    scanned = 0
    for path in xe_dir.glob("*.html"):
        try:
            html = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "RealEstateListing" not in html:
            continue  # a results page, not a detail page
        scanned += 1
        sid = _source_id_from_html(html)
        if not sid:
            continue
        posted = parse_listed_date(html)
        if posted is None:
            continue
        prev = out.get(sid)
        if prev is None or posted > prev:
            out[sid] = posted
    logger.info("scanned %d cached detail pages, found %d dated listings", scanned, len(out))
    return out


def backfill(force: bool = False, rescore: bool = True) -> dict:
    """Write ``listed_date`` onto matching rows from the cached pages. Returns a summary."""
    init_db()
    dates = scan_cached_dates()
    updated = 0
    matched = 0
    with session_scope() as session:
        rows = session.scalars(select(ListingRow).where(ListingRow.source == "xe")).all()
        for row in rows:
            posted = dates.get(row.source_id)
            if posted is None:
                continue
            matched += 1
            if row.listed_date is not None and not force:
                continue
            row.listed_date = posted
            updated += 1
    summary = {"cached_dated": len(dates), "db_matched": matched, "updated": updated}
    logger.info("backfill summary: %s", summary)

    if rescore and updated:
        # Recompute scores/negotiation so the true market age takes effect immediately.
        from scout.pipeline import rescore_all

        n = rescore_all()
        summary["rescored"] = n
        logger.info("re-scored %d active listings with real market age", n)
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite existing listed_date")
    parser.add_argument("--no-rescore", action="store_true", help="skip re-scoring after backfill")
    args = parser.parse_args()
    summary = backfill(force=args.force, rescore=not args.no_rescore)
    print(f"Backfill complete: {summary}")


if __name__ == "__main__":
    main()
