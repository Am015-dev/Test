"""Rewrite Latin and all-caps place names on stored listings to the Greek form
(``scout/place_names.py``).

``normalize`` maps new listings; this repairs the rows stored before it did. For every row it
applies ``greek_place`` to ``neighborhood`` and ``address``; a value the table cannot map is
left exactly as it is and reported under ``skipped``. Brand words (``BRAND_WORDS``) are not
counted as leftovers. Offline, idempotent (a second run changes nothing), cheap — the weekly
workflow runs it before the rescore.

Usage:
    python scripts/repair_place_names.py [--dry-run]
"""

from __future__ import annotations

import logging
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("repair_place_names")

_LATIN = re.compile(r"[A-Za-z]")


def latin_left(value: str | None) -> bool:
    """True when ``value`` still has Latin letters once the brand words are taken out."""
    from scout.place_names import BRAND_WORDS

    if not value:
        return False
    for word in BRAND_WORDS:
        value = value.replace(word, "")
    return bool(_LATIN.search(value))


def repair(dry_run: bool = False) -> dict:
    from sqlalchemy import select

    from scout.db import init_db, session_scope
    from scout.models import ListingRow
    from scout.place_names import greek_place

    init_db()
    out = {"scanned": 0, "neighborhood": 0, "address": 0, "rows": 0}
    skipped: Counter[str] = Counter()
    with session_scope() as session:
        for r in session.scalars(select(ListingRow)).all():
            out["scanned"] += 1
            changed = False
            for col in ("neighborhood", "address"):
                old = getattr(r, col)
                new = greek_place(old)
                if new != old:
                    out[col] += 1
                    changed = True
                    if not dry_run:
                        setattr(r, col, new)
                elif col == "neighborhood" and latin_left(old):
                    skipped[old] += 1
            out["rows"] += changed
        if dry_run:
            session.rollback()
    out["skipped"] = dict(skipped.most_common())
    log.info("repair_place_names%s: %s", " (dry run)" if dry_run else "", out)
    for value, n in skipped.most_common():
        log.info("skipped (no Greek form in place_names.py): %r × %d", value, n)
    return out


if __name__ == "__main__":
    print(repair(dry_run="--dry-run" in sys.argv))
