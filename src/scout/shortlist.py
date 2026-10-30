"""Agent shortlist: save a plain-language buying mandate once; each daily run picks the best
new listings for it, sends a digest, and the owner approves or rejects them in the UI.

``pick`` is pure (testable); the rest persists as one JSON file in a private GitHub Gist.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

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


GIST_FILE = "mandates.json"
GIST_DESC = "holargos-mandates"
_API = "https://api.github.com"
_gist_id: str | None = None


class StorageNotConfigured(Exception):
    """No GITHUB_TOKEN: mandates can't be stored."""


def _gh(method: str, path: str, **kw):
    import os

    import requests

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise StorageNotConfigured("Λείπει το GITHUB_TOKEN (token με δικαίωμα gist).")
    r = requests.request(
        method,
        _API + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=15,
        **kw,
    )
    r.raise_for_status()
    return r.json()


def _find_or_create_gist() -> str:
    global _gist_id
    if _gist_id is None:
        for g in _gh("GET", "/gists?per_page=100"):
            if GIST_FILE in g["files"] and g.get("description") == GIST_DESC:
                _gist_id = g["id"]
                break
        else:
            body = {
                "description": GIST_DESC,
                "public": False,
                "files": {GIST_FILE: {"content": "[]"}},
            }
            _gist_id = _gh("POST", "/gists", json=body)["id"]
    return _gist_id


def _read() -> list[dict]:
    return json.loads(_gh("GET", f"/gists/{_find_or_create_gist()}")["files"][GIST_FILE]["content"])


def _write(rows: list[dict]) -> None:
    body = {"files": {GIST_FILE: {"content": json.dumps(rows, ensure_ascii=False)}}}
    _gh("PATCH", f"/gists/{_find_or_create_gist()}", json=body)


def _to_mandate(row: dict) -> Mandate:
    return Mandate(
        id=row["id"],
        text=row["text"],
        filters=SearchFilters.model_validate(row["filters"]),
        sent=set(row.get("sent", [])),
        approved=set(row.get("approved", [])),
        rejected=set(row.get("rejected", [])),
    )


def save_mandate(text: str, filters: SearchFilters) -> int:
    rows = _read()
    new_id = max((r["id"] for r in rows), default=0) + 1
    rows.append({"id": new_id, "text": text, "filters": filters.model_dump(mode="json")})
    _write(rows)
    return new_id


def list_mandates() -> list[Mandate]:
    return [_to_mandate(r) for r in _read()]


def delete_mandate(mandate_id: int) -> None:
    _write([r for r in _read() if r["id"] != mandate_id])


def _add_ids(mandate_id: int, key: str, ids: set[int]) -> None:
    rows = _read()
    for r in rows:
        if r["id"] == mandate_id:
            r[key] = sorted(set(r.get(key, [])) | ids)
    _write(rows)


def decide(mandate_id: int, listing_id: int, approve: bool) -> None:
    """Record the owner's review; approving also adds the listing to the watchlist."""
    _add_ids(mandate_id, "approved" if approve else "rejected", {listing_id})
    if approve:
        from .ui.queries import set_watched

        try:
            set_watched(listing_id, True)
        except Exception:  # approval is already saved; a DB hiccup must not lose it
            logging.getLogger(__name__).exception("could not add %s to the watchlist", listing_id)


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

    try:
        mandates = list_mandates()
    except StorageNotConfigured:
        return 0  # no token (e.g. the Actions runner): nothing to send
    listings = load_listings()
    sent = 0
    for m in mandates:
        picks = pick(m.filters, listings, m.seen)
        if picks and send_alert(
            digest(m, picks), subject="Holargos — shortlist", settings=settings
        ):
            _add_ids(m.id, "sent", {d["id"] for d, _, _ in picks})
            sent += 1
    return sent
