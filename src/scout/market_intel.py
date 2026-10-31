"""Market intelligence over everything collected — the analysis a generic agent cannot do
from one page of listings.

* Like-for-like comparables: the same municipality, building-age band and size band (and
  floor band when there are enough), so a 2010 flat is priced against 2010-ish flats, not
  against the area median that mixes 1965 blocks with new builds.
* Same-flat twins: one flat listed by several agents (same municipality, m², floor, build
  year, price within 10%) — every asking price and the cheapest link.
* Age premium per municipality: median €/m² per age band, i.e. what a newer building costs
  here and where the value sits.

Pure functions over the listing dicts the UI already loads; no DB, no network.
"""

from __future__ import annotations

import statistics
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

AGE_BANDS = ((0, 5, "έως 5 ετών"), (6, 15, "6–15 ετών"), (16, 30, "16–30 ετών"),
             (31, 45, "31–45 ετών"), (46, 999, "46+ ετών"))  # fmt: skip
SIZE_BANDS = ((0, 45), (45, 65), (65, 90), (90, 120), (120, 10_000))
MIN_COMPS = 5
TWIN_PRICE_GAP = 0.10


HOUSE_WORDS = ("μονοκατοικ", "μεζονετ", "βιλα", "κτιριο", "πολυκατοικ")


def kind(d: dict) -> str:
    """'house' for detached houses / maisonettes (priced differently per m²), else 'flat'."""
    return _kind_of_title(d.get("title") or "")


@lru_cache(maxsize=65_536)  # titles repeat across reruns and pages: normalise each one once
def _kind_of_title(title: str) -> str:
    title = unicodedata.normalize("NFD", title.casefold())
    title = "".join(c for c in title if not unicodedata.combining(c))
    return "house" if title.startswith(HOUSE_WORDS) else "flat"


def comp_area(d: dict) -> str:
    """The area comparables are drawn from: the municipality, or the quarter for central Athens
    ('Αθήνα (Αμπελόκηποι)' → 'Αμπελόκηποι') — Athens is too varied to compare as one."""
    m = municipality(d)
    hood = d.get("neighborhood") or ""
    if m in ("Αθήνα", "Athina") and "(" in hood:
        return hood.split("(", 1)[1].rstrip(") ").strip() or m
    return m


def municipality(d: dict) -> str:
    """'Αργυρούπολη (Κέντρο)' → 'Αργυρούπολη'."""
    return (d.get("neighborhood") or "").split(" (")[0].strip()


def _age(d: dict, year: int) -> int | None:
    built = d.get("renovated_year") or d.get("year_built")
    if not built:
        return None
    age = year - int(built)
    return age if 0 <= age < 200 else (0 if age < 0 else None)


def age_band(age: int | None) -> int | None:
    if age is None:
        return None
    return next(i for i, (lo, hi, _) in enumerate(AGE_BANDS) if lo <= age <= hi)


def _size_band(m2: float | None) -> int | None:
    if not m2:
        return None
    return next((i for i, (lo, hi) in enumerate(SIZE_BANDS) if lo <= m2 < hi), None)


def _floor_band(floor: float | None) -> int | None:
    if floor is None:
        return None
    return 0 if floor < 1 else 1 if floor < 3 else 2


FLOOR_LABEL = ("ισόγειο/υπόγειο", "1ος–2ος", "3ος+")
SPOKEN_FLOOR = ("στο ισόγειο ή υπόγειο", "στον 1ο ή 2ο όροφο", "από τον 3ο όροφο και πάνω")


def _usable(d: dict) -> bool:
    return bool(
        d.get("price_per_m2")
        and municipality(d)
        and not d.get("excluded")
        and not d.get("is_suspect")
        and not d.get("is_unfinished")
    )


@dataclass
class Intel:
    year: int
    by_key: dict[tuple, list[dict]] = field(default_factory=dict)
    twins_by_key: dict[tuple, list[dict]] = field(default_factory=dict)

    # ---- comparables ---------------------------------------------------------------------

    def comps(self, d: dict) -> dict | None:
        """Like-for-like €/m² for ``d``: median, quartiles, n, where ``d`` sits, and a label
        naming exactly what it was compared with. None when fewer than MIN_COMPS exist."""
        m, a = (comp_area(d), kind(d)), age_band(_age(d, self.year))
        s, f = _size_band(d.get("area_m2")), _floor_band(d.get("floor"))
        if not m[0] or a is None or s is None or not d.get("price_per_m2"):
            return None
        twins = {id(t) for t in self.twins(d)}
        levels = [(m, a, s, f)] if f is not None else []  # tightest first, then relax
        for key in [*levels, (m, a, s, None), (m, a, None, None)]:
            rows = [
                x
                for x in self._pool(key)
                if x is not d and id(x) not in twins and x.get("id") != d.get("id")
            ]
            pool = [x["price_per_m2"] for x in rows]
            if len(pool) >= MIN_COMPS:
                q = statistics.quantiles(pool, n=4)
                med = statistics.median(pool)
                return {
                    "ppm": med,
                    "p25": q[0],
                    "p75": q[2],
                    "n": len(pool),
                    "pct": d["price_per_m2"] / med - 1,
                    "label": self._label(*key),
                    "rows": sorted(rows, key=lambda x: x["price_per_m2"]),
                }
        return None

    def _pool(self, key: tuple) -> list[dict]:
        m, a, s, f = key
        if f is not None:
            return self.by_key.get((m, a, s, f), [])
        if s is not None:
            return [x for ff in (None, 0, 1, 2) for x in self.by_key.get((m, a, s, ff), [])]
        return [
            x
            for ss in (None, *range(len(SIZE_BANDS)))
            for ff in (None, 0, 1, 2)
            for x in self.by_key.get((m, a, ss, ff), [])
        ]

    @staticmethod
    def _label(m: tuple, a: int, s: int | None, f: int | None) -> str:
        parts = ["μονοκατοικίες ή μεζονέτες" if m[1] == "house" else "διαμερίσματα"]
        if s is not None:
            lo, hi = SIZE_BANDS[s]
            parts[0] += (
                f" έως {hi} τ.μ."
                if lo == 0
                else f" πάνω από {lo} τ.μ." if hi > 999 else f" {lo}–{hi} τ.μ."
            )
        if f is not None:
            parts.append(SPOKEN_FLOOR[f])
        age = AGE_BANDS[a][2].replace("46+ ετών", "πάνω από 45 ετών")
        parts += [f"σε κτίρια {age}", f"στην περιοχή {m[0]}"]
        return ", ".join(parts)

    # ---- same flat, several listings -----------------------------------------------------

    def twins(self, d: dict) -> list[dict]:
        """Other listings of (very probably) the same flat, cheapest first."""
        key = _twin_key(d)
        if key is None:
            return []
        return sorted(
            (
                x
                for x in self.twins_by_key.get(key, [])
                if x is not d
                and x.get("id") != d.get("id")
                and abs(x["price"] / d["price"] - 1) <= TWIN_PRICE_GAP
            ),
            key=lambda x: x["price"],
        )

    # ---- age premium ---------------------------------------------------------------------

    def age_table(self, m: str) -> list[dict]:
        """Median flat €/m² per age band in municipality ``m`` (bands with ≥ MIN_COMPS)."""
        out = []
        for a, (_, _, label) in enumerate(AGE_BANDS):
            vals = [x["price_per_m2"] for x in self._pool(((m, "flat"), a, None, None))]
            if len(vals) >= MIN_COMPS:
                out.append({"band": label, "ppm": statistics.median(vals), "n": len(vals)})
        return out


def _twin_key(d: dict) -> tuple | None:
    if not (d.get("price") and d.get("area_m2") and d.get("year_built")) or d.get("floor") is None:
        return None
    return (municipality(d), round(d["area_m2"]), d["floor"], d["year_built"])


# One shared Intel per listings list the app caches (``share``), so every page and rerun reads
# the same index instead of rebuilding it. Keyed by the list's identity; the entry holds the
# list itself, so the id cannot be reused while it is here. Read-only for callers.
_SHARED: dict[int, tuple[list[dict], Intel]] = {}
_SHARED_MAX = 1  # the current data version only: an old list must not stay alive
_LOCK = threading.Lock()


def share(listings: list[dict]) -> Intel:
    """Build the Intel of ``listings`` once and hand the same object to every later
    ``build(listings)`` with that very list (until the year turns). For the app's cached lists
    only: the list must not change afterwards."""
    with _LOCK:
        hit = _SHARED.get(id(listings))
        if hit and hit[0] is listings and hit[1].year == date.today().year:
            return hit[1]
        intel = _build(listings, None)
        _SHARED.pop(id(listings), None)
        _SHARED[id(listings)] = (listings, intel)
        while len(_SHARED) > _SHARED_MAX:
            _SHARED.pop(next(iter(_SHARED)))
        return intel


def build(listings: list[dict], year: int | None = None) -> Intel:
    """Index every usable listing (fresh or not — older asking prices are still evidence).
    A list registered with ``share`` gets its shared Intel back (same result, built once)."""
    if year is None:
        hit = _SHARED.get(id(listings))
        if hit and hit[0] is listings and hit[1].year == date.today().year:
            return hit[1]
    return _build(listings, year)


def _build(listings: list[dict], year: int | None) -> Intel:
    intel = Intel(year=year or date.today().year)
    for d in listings:
        if not _usable(d):
            continue
        key = (
            (comp_area(d), kind(d)),
            age_band(_age(d, intel.year)),
            _size_band(d.get("area_m2")),
            _floor_band(d.get("floor")),
        )
        if key[1] is not None:
            intel.by_key.setdefault(key, []).append(d)
        if d.get("is_fresh", True) and (tk := _twin_key(d)):
            intel.twins_by_key.setdefault(tk, []).append(d)
    return intel
