"""Liquidity / time-on-market per area — an exit signal no portal gives.

A buy-to-let investor's real question isn't only "is it cheap?" but "if I need to exit,
how fast does this submarket move?" We can answer it from our OWN accumulating time-series:
listings we've watched go from ``active`` to ``gone`` (delisted — a proxy for sold/off-
market) tell us how long stock sits before it clears, and the share that clears tells us
absorption. Neither is on any portal — it only exists because we track daily.

Pure functions, no DB. The caller passes plain listing dicts (``search_area``, ``status``,
``first_seen``, ``last_seen``); everything here is arithmetic, so it's trivially testable.

Honesty note: ``gone`` means "removed from the portal", which is a *proxy* for sold — a
seller can also just delist. We therefore call the metric "typical days on market before
delisting", never "days to sell", and require a minimum sample before reporting it.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

# Below this many cleared listings an area's median is noise — report nothing.
_MIN_CLEARED = 8


@dataclass
class AreaLiquidity:
    area: str
    median_days_on_market: float | None  # median dwell of cleared (gone) listings
    cleared: int  # how many listings we watched go from active -> gone
    active: int  # how many are still active
    absorption_rate: float | None  # cleared / (cleared + active), 0..1


def _dwell_days(first_seen, last_seen) -> int | None:
    if first_seen is None or last_seen is None:
        return None
    return max((last_seen - first_seen).days, 0)


def liquidity_by_area(listings: list[dict]) -> dict[str, AreaLiquidity]:
    """Per-area liquidity from the tracked lifecycle of each listing.

    ``listings`` are plain dicts with ``search_area``, ``status`` ("active"/"gone"),
    ``first_seen`` and ``last_seen`` datetimes. Areas with too few cleared listings are
    omitted (their median would be meaningless)."""
    cleared: dict[str, list[int]] = {}
    active: dict[str, int] = {}
    for d in listings:
        area = d.get("search_area")
        if not area:
            continue
        if d.get("status") == "gone":
            days = _dwell_days(d.get("first_seen"), d.get("last_seen"))
            if days is not None:
                cleared.setdefault(area, []).append(days)
        elif d.get("status") == "active":
            active[area] = active.get(area, 0) + 1

    out: dict[str, AreaLiquidity] = {}
    for area in set(cleared) | set(active):
        dwells = cleared.get(area, [])
        n_cleared = len(dwells)
        n_active = active.get(area, 0)
        total = n_cleared + n_active
        out[area] = AreaLiquidity(
            area=area,
            median_days_on_market=(
                statistics.median(dwells) if n_cleared >= _MIN_CLEARED else None
            ),
            cleared=n_cleared,
            active=n_active,
            absorption_rate=(n_cleared / total if total else None),
        )
    return out
