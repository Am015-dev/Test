"""Agent shortlist: save a plain-language buying mandate once; each daily run picks the best
new listings for it, sends a digest, and the owner approves or rejects them in the UI.

``pick`` is pure (testable); the rest persists as one JSON file in a private GitHub Gist.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field

from .nl_search import SearchFilters, advise, match

TOP_N = 5


@dataclass
class Mandate:
    id: int
    text: str
    filters: SearchFilters
    sent: set[str] = field(default_factory=set)
    approved: set[str] = field(default_factory=set)
    rejected: set[str] = field(default_factory=set)

    @property
    def seen(self) -> set[str]:
        return self.sent | self.approved | self.rejected


def lkey(d: dict) -> str:
    """Stable id of a listing across DB rebuilds (row ids are not)."""
    return f"{d['source']}:{d['source_id']}"


def pick(
    filters: SearchFilters, listings: list[dict], skip: set[str], n: int = TOP_N
) -> list[tuple[dict, dict, list[str]]]:
    """Top ``n`` live listings for the mandate as (listing, advice, reasons), best score first.
    Listings in ``skip`` (already sent / reviewed) and excluded ones never appear."""
    hits = []
    for d in listings:
        if (
            d.get("excluded")
            or d.get("is_suspect")
            or not d.get("is_fresh", True)
            or lkey(d) in skip
        ):
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


_recent: tuple[float, dict] | None = None
_FRESH_S = 60  # GitHub can serve the pre-write gist for a few seconds after a PATCH


def _read_all() -> dict:
    """The whole stored document: {"mandates": [...], "watch": [...]} (old files were a bare
    list of mandates)."""
    if _recent and time.monotonic() - _recent[0] < _FRESH_S:
        return copy.deepcopy(_recent[1])
    data = json.loads(_gh("GET", f"/gists/{_find_or_create_gist()}")["files"][GIST_FILE]["content"])
    if isinstance(data, list):
        data = {"mandates": data}
    data.setdefault("mandates", [])
    data.setdefault("watch", [])
    data.setdefault("review", {})
    return data


def _write_all(data: dict) -> None:
    global _recent
    body = {"files": {GIST_FILE: {"content": json.dumps(data, ensure_ascii=False)}}}
    _gh("PATCH", f"/gists/{_find_or_create_gist()}", json=body)
    _recent = (time.monotonic(), copy.deepcopy(data))


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
    data = _read_all()
    new_id = max((r["id"] for r in data["mandates"]), default=0) + 1
    data["mandates"].append(
        {"id": new_id, "text": text, "filters": filters.model_dump(mode="json")}
    )
    _write_all(data)
    return new_id


def list_mandates() -> list[Mandate]:
    return [_to_mandate(r) for r in _read_all()["mandates"]]


def delete_mandate(mandate_id: int) -> None:
    data = _read_all()
    data["mandates"] = [r for r in data["mandates"] if r["id"] != mandate_id]
    _write_all(data)


def _add_ids(mandate_id: int, key: str, ids: set[str]) -> None:
    data = _read_all()
    for r in data["mandates"]:
        if r["id"] == mandate_id:
            r[key] = sorted(set(r.get(key, [])) | ids)
    _write_all(data)


def watch_set() -> set[str]:
    """Listing keys the owner has starred (the watchlist)."""
    return set(_read_all()["watch"])


def set_watch(listing_key: str, on: bool) -> None:
    data = _read_all()
    keys = set(data["watch"])
    keys.add(listing_key) if on else keys.discard(listing_key)
    data["watch"] = sorted(keys)
    _write_all(data)


def review_map() -> dict[str, str]:
    """The owner's verdict on «Βρες μου σπίτι» picks: listing key → "ok" | "no"."""
    return dict(_read_all()["review"])


def set_review(listing_key: str, verdict: str | None) -> None:
    """Approve ("ok"), drop ("no") or clear (None) a pick; approving also stars it."""
    data = _read_all()
    if verdict is None:
        data["review"].pop(listing_key, None)
    else:
        data["review"][listing_key] = verdict
    if verdict == "ok":
        data["watch"] = sorted(set(data["watch"]) | {listing_key})
    _write_all(data)


def decide(mandate_id: int, listing_key: str, approve: bool) -> None:
    """Record the owner's review; approving also stars the listing."""
    _add_ids(mandate_id, "approved" if approve else "rejected", {listing_key})
    if approve:
        set_watch(listing_key, True)


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
            _add_ids(m.id, "sent", {lkey(d) for d, _, _ in picks})
            sent += 1
    return sent
