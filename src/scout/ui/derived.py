"""Values derived from the app's cached listings, computed once per data version (C13).

``app.get_listings`` returns ONE list per data version (cache_resource keyed by the data file's
path, mtime and row count), shared by every session. Everything here is keyed by that list's
identity: the store keeps a reference to the list, so the id cannot be reused while its entry
lives; only the newest list is kept (a new data version frees the old one). Values are shared
across sessions: READ-ONLY.
Nothing here changes a result; it only stops recomputing the same thing on every rerun.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date
from typing import Any

from scout import area_insights

_STORE: dict[int, tuple[list[dict], dict]] = {}
_KEEP = 1  # the current data version only: an old list must not stay alive
_LOCK = threading.Lock()


def memo(listings: list[dict], name: Any, fn: Callable[[], Any]) -> Any:
    """``fn()`` once per (``listings`` object, ``name``); later calls get the same value."""
    with _LOCK:
        entry = _STORE.get(id(listings))
        if entry is None or entry[0] is not listings:
            entry = (listings, {})
            _STORE.pop(id(listings), None)
            _STORE[id(listings)] = entry
            while len(_STORE) > _KEEP:
                _STORE.pop(next(iter(_STORE)))
        values = entry[1]
    if name not in values:  # computed outside the lock; a race only computes it twice
        values[name] = fn()
    return values[name]


def guide_context(listings: list[dict], rents: list[dict], year: int | None = None):
    """The guide's per-data inputs: (area_facts, find_memo). ``area_facts`` is
    ``{x.area: x for x in area_insights.rank_areas(listings, rents, year=year)}``; ``find_memo``
    is the ``memo`` ``picks.find`` fills with its per-listing work (it depends only on the data,
    the rents, the year and area_facts — never on the answers). Recomputed when the rents
    differ from the ones it was built with."""
    year = year or date.today().year

    def make():
        facts = {x.area: x for x in area_insights.rank_areas(listings, rents, year=year)}
        return rents, facts, {}

    got = memo(listings, ("guide", year), make)
    if got[0] != rents:  # the rent rows refreshed (their cache is shorter): start over
        with _LOCK:
            _STORE[id(listings)][1].pop(("guide", year), None)
        got = memo(listings, ("guide", year), make)
    return got[1], got[2]
