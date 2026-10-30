"""Agent shortlist: save a plain-language buying mandate once; each daily run picks the best
new listings for it, sends a digest, and the owner approves or rejects them in the UI.

``pick`` is pure (testable); the rest persists to the ``mandate`` table.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from .nl_search import SearchFilters, advise, match

TOP_N = 5


@dataclass
class Mandate:
    id: int
    text: str
    filters: SearchFilters
    sent: set[int] = field(default_factory=set)
    approved: set[int] = field(default_factory=set)
    rejected: set[int] = field(default_factory=set)

    @property
    def seen(self) -> set[int]:
        return self.sent | self.approved | self.rejected


def pick(
    filters: SearchFilters, listings: list[dict], skip: set[int], n: int = TOP_N
) -> list[tuple[dict, dict, list[str]]]:
    """Top ``n`` live listings for the mandate as (listing, advice, reasons), best score first.
    Listings in ``skip`` (already sent / reviewed) and excluded ones never appear."""
    hits = []
    for d in listings:
        if d.get("excluded") or d["id"] in skip:
            continue
        m = match(d, filters)
        if m is not None:
            hits.append((d, advise(d), m[1]))
    hits.sort(key=lambda h: (-h[1]["score"], h[0]["price"]))
    return hits[:n]


_table_ready = False


def _ensure_table() -> None:
    """Create the ``mandate`` table if missing. The dashboard never runs ``init_db`` (only the
    pipeline does), so on an already-deployed DB the first Shortlist visit must make it."""
    global _table_ready
    if not _table_ready:
        from .db import get_engine
        from .models import MandateRow

        MandateRow.__table__.create(get_engine(), checkfirst=True)
        _table_ready = True


def _ids(raw: str | None) -> set[int]:
    return set(json.loads(raw)) if raw else set()


def _to_mandate(row) -> Mandate:
    return Mandate(
        id=row.id,
        text=row.text,
        filters=SearchFilters.model_validate_json(row.filters),
        sent=_ids(row.sent_ids),
        approved=_ids(row.approved_ids),
        rejected=_ids(row.rejected_ids),
    )


def save_mandate(text: str, filters: SearchFilters) -> int:
    from .db import session_scope
    from .models import MandateRow

    _ensure_table()
    with session_scope() as session:
        row = MandateRow(text=text, filters=filters.model_dump_json(), created_at=datetime.utcnow())
        session.add(row)
        session.flush()
        return row.id


def list_mandates() -> list[Mandate]:
    from sqlalchemy import select

    from .db import session_scope
    from .models import MandateRow

    _ensure_table()
    with session_scope() as session:
        return [_to_mandate(r) for r in session.scalars(select(MandateRow)).all()]


def delete_mandate(mandate_id: int) -> None:
    from .db import session_scope
    from .models import MandateRow

    with session_scope() as session:
        row = session.get(MandateRow, mandate_id)
        if row is not None:
            session.delete(row)


def _add_ids(mandate_id: int, column: str, ids: set[int]) -> None:
    from .db import session_scope
    from .models import MandateRow

    with session_scope() as session:
        row = session.get(MandateRow, mandate_id)
        if row is not None:
            merged = _ids(getattr(row, column)) | ids
            setattr(row, column, json.dumps(sorted(merged)))


def decide(mandate_id: int, listing_id: int, approve: bool) -> None:
    """Record the owner's review; approving also adds the listing to the watchlist."""
    _add_ids(mandate_id, "approved_ids" if approve else "rejected_ids", {listing_id})
    if approve:
        from .ui.queries import set_watched

        set_watched(listing_id, True)


def digest(m: Mandate, picks: list[tuple[dict, dict, list[str]]]) -> str:
    lines = [f"🏠 Shortlist — «{m.text}»", f"{len(picks)} νέες προτάσεις:", ""]
    for d, adv, _ in picks:
        gap = adv["gap"]
        lines.append(
            f"[{adv['score']}] {d['price']:,} € · {d.get('area_m2') or '?'} τ.μ. · "
            f"{d.get('neighborhood') or '—'}"
            + (f" · {gap:.0%} κάτω από την εκτιμώμενη αξία" if gap and gap > 0 else "")
            + f"\n  {d['url']}"
        )
    lines += ["", "Έλεγξε και έγκρινε/απόρριψε στη σελίδα Shortlist."]
    return "\n".join(lines)


def run_shortlists(settings=None) -> int:
    """Daily step: for every mandate send its new top picks (never repeating one). Returns the
    number of digests sent. Picks are marked sent only if the alert actually went out."""
    from .alerts import send_alert
    from .ui.queries import load_listings

    listings = load_listings()
    sent = 0
    for m in list_mandates():
        picks = pick(m.filters, listings, m.seen)
        if picks and send_alert(
            digest(m, picks), subject="Holargos — shortlist", settings=settings
        ):
            _add_ids(m.id, "sent_ids", {d["id"] for d, _, _ in picks})
            sent += 1
    return sent
