"""Saved searches — the recurring investor mandate a €19/mo subscription pays for.

A saved search is a named filter (regions + price/yield/grade floors). The daily digest can
then deliver *only what matches my mandate, before I'd see it myself* — the timeliness +
personalisation a portal's undifferentiated feed can't provide, and the reason to keep
paying month after month.

CRUD persists to the ``saved_search`` table; ``matches`` is a pure predicate so it's
trivially testable and reusable by the digest and the UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

_GRADE_ORDER = {"A": 3, "B": 2, "C": 1, "D": 0}


@dataclass
class SavedSearch:
    id: int | None
    name: str
    regions: list[str]
    min_price: int | None = None
    max_price: int | None = None
    min_net_yield: float | None = None
    min_grade: str | None = None


def matches(search: SavedSearch, listing: dict) -> bool:
    """True if a listing dict satisfies the mandate. Pure — no DB."""
    if search.regions and listing.get("region") not in search.regions:
        return False
    price = listing.get("price")
    if search.min_price is not None and (price is None or price < search.min_price):
        return False
    if search.max_price is not None and (price is None or price > search.max_price):
        return False
    if search.min_net_yield is not None and (listing.get("net_yield") or 0) < search.min_net_yield:
        return False
    if search.min_grade is not None:
        want = _GRADE_ORDER.get(search.min_grade, 0)
        have = _GRADE_ORDER.get(listing.get("deal_grade", "D"), 0)
        if have < want:
            return False
    return True


def matching_listings(search: SavedSearch, listings: list[dict]) -> list[dict]:
    """Listings satisfying the mandate, best score first."""
    return sorted(
        (d for d in listings if matches(search, d)), key=lambda d: d.get("score") or 0, reverse=True
    )


# ---- persistence ----------------------------------------------------------


def _to_model(row) -> SavedSearch:
    return SavedSearch(
        id=row.id,
        name=row.name,
        regions=json.loads(row.regions) if row.regions else [],
        min_price=row.min_price,
        max_price=row.max_price,
        min_net_yield=row.min_net_yield,
        min_grade=row.min_grade,
    )


def create_saved_search(search: SavedSearch) -> int:
    from .db import session_scope
    from .models import SavedSearchRow

    with session_scope() as session:
        row = SavedSearchRow(
            name=search.name,
            regions=json.dumps(search.regions, ensure_ascii=False) if search.regions else None,
            min_price=search.min_price,
            max_price=search.max_price,
            min_net_yield=search.min_net_yield,
            min_grade=search.min_grade,
            created_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        return row.id


def list_saved_searches() -> list[SavedSearch]:
    from sqlalchemy import select

    from .db import session_scope
    from .models import SavedSearchRow

    with session_scope() as session:
        return [_to_model(r) for r in session.scalars(select(SavedSearchRow)).all()]


def delete_saved_search(search_id: int) -> None:
    from .db import session_scope
    from .models import SavedSearchRow

    with session_scope() as session:
        row = session.get(SavedSearchRow, search_id)
        if row is not None:
            session.delete(row)
