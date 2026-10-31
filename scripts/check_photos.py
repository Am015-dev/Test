"""Photo check — are a new-build listing's pictures of the flat, or renders / plans / site?

The text check (``xe.unfinished_on_detail``) cannot see that most «νεόδμητο» ads near stations
show 3D renders, floor plans or scaffolding. For recent new-build SALE listings whose page was
read, this fetches up to three of the listing's own photos and classifies them with one Claude
vision call (``claude-haiku-5-5``; ``ANTHROPIC_MODEL_VISION`` overrides) into

    photo | render | plan | site | stock

and stores the majority as ``photo_kind`` with ``photo_checked_at``. Deterministic pre-filters
run first and cost nothing:

* fewer than three images on the page → no call; ``photo_kind`` stays NULL (checked_at set);
* the same image file (by content hash) in several listings → ``stock`` (a logo or building
  render the agent re-uses; XE exposes no agent id, so "same agent" = "same file in more than
  one listing of this run").

Needs ``ANTHROPIC_API_KEY`` (never printed). Resumable: only rows with no ``photo_checked_at``.

Usage:
    python scripts/check_photos.py --limit 150 --max-minutes 13 --areas "Cholargos,Papagou"
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta

import requests
from sqlalchemy import or_, select

from scout.collectors.xe import UNFINISHED_CHECK_SINCE, XeCollector, parse_photo_urls
from scout.config import get_settings, load_strategy
from scout.db import init_db, session_scope
from scout.models import ListingRow
from scout.picks import STATIONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("check_photos")

KINDS = ("photo", "render", "plan", "site", "stock")
DEFAULT_MODEL = "claude-haiku-5-5"
MIN_IMAGES = 3
MAX_IMAGE_BYTES = 4_500_000  # API limit is 5 MB per image
# When no label has a majority, the least flattering one wins: a real photo needs a majority.
TIE_ORDER = ("render", "plan", "site", "stock", "photo")

PROMPT = (
    "Ένα ακίνητο προς πώληση έχει τις παρακάτω φωτογραφίες αγγελίας, με τη σειρά. "
    "Για κάθε εικόνα διάλεξε ΜΙΑ ετικέτα:\n"
    "photo = πραγματική φωτογραφία του διαμερίσματος ή της πολυκατοικίας όπως είναι σήμερα "
    "(εσωτερικό, μπαλκόνι, πρόσοψη)\n"
    "render = ψηφιακή απεικόνιση / 3D εικόνα\n"
    "plan = κάτοψη ή αρχιτεκτονικό σχέδιο\n"
    "site = εργοτάξιο, σκαλωσιές, γυμνό σκυρόδεμα, ημιτελής κατασκευή\n"
    "stock = λογότυπο, φωτογραφία αρχείου, χάρτης ή εικόνα που δεν δείχνει το ακίνητο\n"
    'Απάντησε ΜΟΝΟ με JSON: {"labels": ["...", ...]} με μία ετικέτα ανά εικόνα.'
)


def vision_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL_VISION") or DEFAULT_MODEL


def majority(labels: list[str]) -> str | None:
    """The label most images got; on a tie the least flattering (``TIE_ORDER``). None when
    there is no valid label."""
    valid = [x for x in labels if x in KINDS]
    if not valid:
        return None
    top = max(Counter(valid).values())
    tied = {k for k, n in Counter(valid).items() if n == top}
    return next(k for k in TIE_ORDER if k in tied)


def classify(client, images: list[tuple[str, bytes]]) -> str | None:
    """One vision call over ``images`` = [(media_type, bytes)] → majority label, or None
    when the answer cannot be read. ``client`` is an ``anthropic.Anthropic`` (or a stub)."""
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media,
                "data": base64.b64encode(raw).decode("ascii"),
            },
        }
        for media, raw in images
    ]
    content.append({"type": "text", "text": PROMPT})
    resp = client.messages.create(
        model=vision_model(),
        max_tokens=100,  # the SDK/API take no temperature for this model family
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(getattr(b, "text", "") for b in resp.content)
    found = re.search(r"\{.*\}", text, re.S)
    if not found:
        return None
    try:
        labels = json.loads(found.group(0)).get("labels")
    except (ValueError, AttributeError):
        return None
    if not isinstance(labels, list):
        return None
    return majority([str(x).strip().lower() for x in labels])


def stock_hashes(hashes_by_listing: dict[int, list[str]]) -> set[str]:
    """Image hashes that appear in more than one listing."""
    seen = Counter(h for hs in hashes_by_listing.values() for h in set(hs))
    return {h for h, n in seen.items() if n > 1}


def _media_type(raw: bytes) -> str | None:
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:4] == b"GIF8":
        return "image/gif"
    return None


def download(http: requests.Session, url: str) -> tuple[str, bytes] | None:
    """(media_type, bytes) of one image, or None (fail-soft: skipped, never raised)."""
    try:
        resp = http.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("image fetch failed: %s", type(exc).__name__)
        return None
    raw = resp.content
    media = _media_type(raw)
    if not media or not raw or len(raw) > MAX_IMAGE_BYTES:
        return None
    return media, raw


def candidate_rows(session, limit: int, areas: list[str] | None) -> list[ListingRow]:
    """Recent new-build sale listings whose page was read with the current check, not yet
    photo-checked; station neighbourhoods first, then cheapest per m² (as enrich_details)."""
    year = datetime.utcnow().year
    stmt = (
        select(ListingRow)
        .where(ListingRow.source == "xe", ListingRow.status == "active")
        .where(ListingRow.detail_checked_at >= UNFINISHED_CHECK_SINCE)
        .where(ListingRow.photo_checked_at.is_(None))
        .where(ListingRow.excluded.is_(False), ListingRow.is_unfinished.is_(False))
        .where(ListingRow.year_built >= year - 10)
        .where(ListingRow.last_seen >= datetime.utcnow() - timedelta(days=14))
        .order_by(
            or_(*(ListingRow.neighborhood.contains(k) for k in STATIONS)).desc(),
            ListingRow.price_per_m2,
        )
    )
    if hasattr(ListingRow, "listing_type"):  # rentals are never checked (round-4 C1)
        stmt = stmt.where(ListingRow.listing_type == "sale")
    if areas:
        stmt = stmt.where(ListingRow.search_area.in_(areas))
    return list(session.scalars(stmt.limit(limit)).all())


def check(
    limit: int = 150,
    areas: list[str] | None = None,
    max_minutes: float = 13,
    client=None,
    http: requests.Session | None = None,
    page_fetcher=None,
) -> dict:
    """Run the photo check. ``client`` / ``http`` / ``page_fetcher`` are injectable for tests."""
    init_db()
    deadline = time.monotonic() + max_minutes * 60
    settings = get_settings()
    if client is None:
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY itself; never logged
    if page_fetcher is None:
        collector = XeCollector(load_strategy())
        page_http = collector._new_session()

        def page_fetcher(url: str) -> str | None:
            return collector._fetch_detail(page_http, url)

    http = http or requests.Session()
    summary = {"rows": 0, "few_images": 0, "stock": 0, "classified": 0, "failed": 0}
    gathered: dict[int, list[tuple[str, bytes]]] = {}
    with session_scope() as db:
        rows = candidate_rows(db, limit, areas)
        summary["rows"] = len(rows)
        now = datetime.utcnow()
        # 1) pre-filter: page → image list; < 3 images means no call at all
        for row in rows:
            if time.monotonic() > deadline:
                break
            html = page_fetcher(row.url)
            if html is None:
                continue  # transient: stays in the queue
            urls = parse_photo_urls(html) if html else []
            if len(urls) < MIN_IMAGES:
                row.photo_checked_at, row.photo_kind = now, None
                summary["few_images"] += 1
                continue
            imgs = [i for u in urls[:MIN_IMAGES] if (i := download(http, u))]
            time.sleep(0.2)
            if len(imgs) < MIN_IMAGES:
                continue  # fetch trouble: retry next run
            gathered[row.id] = imgs
        # 2) identical files across listings → stock
        hashes = {
            rid: [hashlib.sha256(raw).hexdigest() for _, raw in imgs]
            for rid, imgs in gathered.items()
        }
        shared = stock_hashes(hashes)
        by_id = {r.id: r for r in rows}
        for rid, imgs in gathered.items():
            row = by_id[rid]
            if shared.intersection(hashes[rid]):
                row.photo_kind, row.photo_checked_at = "stock", now
                summary["stock"] += 1
                continue
            if time.monotonic() > deadline:
                break
            try:
                kind = classify(client, imgs)
            except Exception as exc:  # API/network trouble: leave for the next run
                log.warning("classify failed: %s", type(exc).__name__)
                summary["failed"] += 1
                continue
            if kind is None:
                summary["failed"] += 1
                continue
            row.photo_kind, row.photo_checked_at = kind, now
            summary["classified"] += 1
    log.info(
        "photo check summary: %s (cache ttl %s min)", summary, settings.scrape_cache_ttl_minutes
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--max-minutes", type=float, default=13)
    parser.add_argument("--areas", default="", help="comma-separated search areas (empty = all)")
    args = parser.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — photo check skipped")
        return
    areas = [a.strip() for a in args.areas.replace("\n", " ").split(",") if a.strip()]
    print(f"Photo check complete: {check(args.limit, areas or None, args.max_minutes)}")


if __name__ == "__main__":
    main()
