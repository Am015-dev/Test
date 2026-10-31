"""Where in NE Athens should a private buyer buy a flat to rent out — and why.

Per-municipality market read from the listing dicts the UI already loads (see
``ui/queries.py: load_listings``) plus the scraped rental comparables (``rent_comp``
rows), then a transparent buy-to-let ranking with short factual Greek reasons.

Everything here is ASKING prices (sale and rent) — not transaction prices. The text says so.

Thresholds (module constants, so they are visible and testable):

* ``MIN_FRESH`` — a municipality is assessed only with at least 20 fresh, usable listings
  (fresh = re-seen in the latest scrape window; usable = has €/m², not excluded / suspect /
  unfinished, and geographically in Attica). Fewer and a median moves with one listing.
* ``MIN_BAND`` — an age-band median needs ``market_intel.MIN_COMPS`` (5) listings.
* ``MIN_TREND`` — each trend cohort (first seen in July / seen in late October) needs 10
  listings, else the trend is ``None`` ("n/a").
* ``SMALL_SAMPLE`` — under 50 fresh listings is flagged as a risk.

Score (0–100) = 100 × Σ weight × component, each component on a FIXED scale clamped to 0..1
(not min-max across areas, so a score means the same thing every week):

=================  ======  ===============================================================
component          weight  scale (0 → 1)
=================  ======  ===============================================================
gross yield         0.35   3% → 7%
affordability       0.20   20% above → 20% below the NE-Athens median €/m²
good stock          0.20   0 → 30 fresh, non-ground, ≤30-year flats under their band median
negotiability       0.15   0% → 40% of fresh listings with a price cut
momentum            0.10   asking €/m² −5% → +5% July → late October
=================  ======  ===============================================================

A missing signal (no rent, trend n/a) scores a neutral 0.5 and is named as a risk.

Pure functions; no DB, no network.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from .market_intel import AGE_BANDS, MIN_COMPS, _age, _usable, age_band, municipality

# The buyer's NE-Athens search areas (``search_area`` values; mirrors WEEKLY_AREAS in
# .github/workflows/daily.yml).
NE_ATHENS_AREAS = (
    "Cholargos", "Papagou", "Agia Paraskevi", "Chalandri", "Vrilissia", "Marousi",
    "Zografou", "Psychiko", "Filothei", "Irakleio", "Nea Filadelfeia", "Pefki", "Galatsi",
    "Ampelokipoi", "Metamorfosi",
)  # fmt: skip

MIN_FRESH = 20
MIN_BAND = MIN_COMPS
MIN_TREND = 10
SMALL_SAMPLE = 50
RECENT_MAX_AGE = 30  # "newer stock" = built/renovated within 30 years (AGE_BANDS 0..2)
RECENT_BANDS = tuple(i for i, (_, hi, _) in enumerate(AGE_BANDS) if hi <= RECENT_MAX_AGE)
OLD_STOCK_SHARE = 0.6
FALLING_TREND = -0.03
RISING_TREND = 0.01
FEW_RENT_SAMPLES = 10
LOW_YIELD = 0.04
# Attica latitude band: the "Irakleio" search also returns Heraklion (Crete) listings.
ATTICA_LAT = (37.6, 38.4)

# Trend cohorts: first seen in July vs last seen in late October (of the analysis year).
EARLY_MONTH = 7
LATE_FROM = (10, 16)
LATE_TO = (10, 31)

WEIGHTS = {
    "yield": 0.35,
    "affordability": 0.20,
    "stock": 0.20,
    "negotiability": 0.15,
    "momentum": 0.10,
}
NEUTRAL = 0.5

_ATHENS = {"Αθήνα", "Athina", "Athens"}
_GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")


@dataclass
class AreaInsight:
    area: str
    n_fresh: int
    median_ppm: float
    median_ppm_recent: float | None
    n_recent: int
    trend_early_ppm: float | None
    trend_early_n: int
    trend_late_ppm: float | None
    trend_late_n: int
    trend_pct: float | None  # None = n/a (a cohort under MIN_TREND)
    cut_share: float
    median_cut_pct: float | None
    median_dom: float | None
    rent_ppm: float | None  # asking rent €/m²/month
    rent_samples: int | None  # None = count not recorded in rent_comp
    gross_yield: float | None
    value_band: str | None  # ≤30y age band cheapest vs new builds (≤5y)
    value_band_discount: float | None  # 1 − band median / new-build median
    good_stock: int
    old_share: float | None  # share of fresh listings with known age that are >30 years
    unknown_age_share: float
    score: float = 0.0
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


# ---- helpers -----------------------------------------------------------------------------


def area_name(neighborhood: str | None) -> str:
    """Municipality, except central Athens, where the quarter in brackets is the area
    ('Αθήνα (Αμπελόκηποι)' → 'Αμπελόκηποι')."""
    m = municipality({"neighborhood": neighborhood})
    if m in _ATHENS and neighborhood and "(" in neighborhood:
        return neighborhood.split("(", 1)[1].rstrip(") ").strip() or m
    return m


def _day(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def _in_attica(d: dict) -> bool:
    lat = d.get("lat")
    return lat is None or ATTICA_LAT[0] <= lat <= ATTICA_LAT[1]


def _eligible(d: dict) -> bool:
    return _usable(d) and _in_attica(d) and bool(_GREEK.search(area_name(d.get("neighborhood"))))


def _median(vals: list[float]) -> float | None:
    return statistics.median(vals) if vals else None


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _num(x: float) -> str:
    """Greek thousands separator: 2950 → '2.950'."""
    return f"{x:,.0f}".replace(",", ".")


def _pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%".replace(".", ",")


def _first_ppm(d: dict) -> float:
    """€/m² when first seen: the first asking price if we have it, else the current one."""
    if d.get("first_price") and d.get("area_m2"):
        return d["first_price"] / d["area_m2"]
    return d["price_per_m2"]


# ---- rent --------------------------------------------------------------------------------


def rent_by_area(rent_rows: list[dict]) -> dict[str, tuple[float, int | None]]:
    """Map area name → (asking rent €/m²/month, samples or None when not recorded).

    ``rent_rows`` are ``rent_comp`` rows ``{area, neighborhood, rent_per_m2, samples}``. A
    search area's area-wide row (neighbourhood None) is used for the municipality that owns
    most of its neighbourhood rows; a municipality owning no search area falls back to the
    median of its own neighbourhood rows.
    """
    hoods: dict[str, list[dict]] = {}
    overall: dict[str, dict] = {}
    for r in rent_rows:
        if not r.get("rent_per_m2"):
            continue
        if r.get("neighborhood"):
            hoods.setdefault(r["area"], []).append(r)
        else:
            overall[r["area"]] = r
    out: dict[str, tuple[float, int | None]] = {}
    by_name: dict[str, list[dict]] = {}
    for search_area, rows in hoods.items():
        for r in rows:
            by_name.setdefault(area_name(r["neighborhood"]), []).append(r)
        owner = Counter(area_name(r["neighborhood"]) for r in rows).most_common(1)[0][0]
        o = overall.get(search_area)
        if o and (owner not in out or (o.get("samples") or 0) > (out[owner][1] or 0)):
            out[owner] = (float(o["rent_per_m2"]), o.get("samples") or None)
    for name, rows in by_name.items():
        if name not in out:
            samples = sum(r.get("samples") or 0 for r in rows)
            out[name] = (statistics.median(r["rent_per_m2"] for r in rows), samples or None)
    return out


# ---- per-area metrics --------------------------------------------------------------------


def _band_medians(rows: list[dict], year: int) -> dict[int, float]:
    by_band: dict[int, list[float]] = {}
    for d in rows:
        b = age_band(_age(d, year))
        if b is not None:
            by_band.setdefault(b, []).append(d["price_per_m2"])
    return {b: statistics.median(v) for b, v in by_band.items() if len(v) >= MIN_BAND}


def _insight(
    name: str,
    fresh: list[dict],
    everything: list[dict],
    rent: tuple[float, int | None] | None,
    year: int,
) -> AreaInsight:
    ppms = [d["price_per_m2"] for d in fresh]
    median_ppm = statistics.median(ppms)
    ages = [(d, _age(d, year)) for d in fresh]
    recent = [d for d, a in ages if a is not None and a <= RECENT_MAX_AGE]
    known = [a for _, a in ages if a is not None]

    early = [
        _first_ppm(d)
        for d in everything
        if (fs := _day(d.get("first_seen"))) and fs.year == year and fs.month == EARLY_MONTH
    ]
    lo, hi = date(year, *LATE_FROM), date(year, *LATE_TO)
    late = [
        d["price_per_m2"] for d in everything if (ls := _day(d.get("last_seen"))) and lo <= ls <= hi
    ]
    trend = None
    if len(early) >= MIN_TREND and len(late) >= MIN_TREND:
        trend = statistics.median(late) / statistics.median(early) - 1

    cuts = [
        1 - d["price"] / d["first_price"]
        for d in fresh
        if d.get("price_dropped") and d.get("first_price") and d.get("price")
    ]
    doms = [d["days_on_market"] for d in fresh if d.get("days_on_market") is not None]

    bands = _band_medians(fresh, year)
    value_band = value_disc = None
    if 0 in bands:
        cands = [(bands[b] / bands[0], b) for b in RECENT_BANDS if b != 0 and b in bands]
        if cands:
            ratio, b = min(cands)
            value_band, value_disc = AGE_BANDS[b][2], 1 - ratio

    good = 0
    for d, a in ages:
        b = age_band(a)
        if (
            b in RECENT_BANDS
            and b in bands
            and d.get("floor") is not None
            and d["floor"] >= 1
            and d["price_per_m2"] < bands[b]
        ):
            good += 1

    rent_ppm, rent_n = rent if rent else (None, None)
    return AreaInsight(
        area=name,
        n_fresh=len(fresh),
        median_ppm=median_ppm,
        median_ppm_recent=_median([d["price_per_m2"] for d in recent]),
        n_recent=len(recent),
        trend_early_ppm=_median(early),
        trend_early_n=len(early),
        trend_late_ppm=_median(late),
        trend_late_n=len(late),
        trend_pct=trend,
        cut_share=len(cuts) / len(fresh),
        median_cut_pct=_median(cuts),
        median_dom=_median(doms),
        rent_ppm=rent_ppm,
        rent_samples=rent_n,
        gross_yield=12 * rent_ppm / median_ppm if rent_ppm else None,
        value_band=value_band,
        value_band_discount=value_disc,
        good_stock=good,
        old_share=sum(a > RECENT_MAX_AGE for a in known) / len(known) if known else None,
        unknown_age_share=1 - len(known) / len(fresh),
    )


# ---- score + text ------------------------------------------------------------------------


def _components(x: AreaInsight, ref_ppm: float) -> dict[str, float]:
    return {
        "yield": NEUTRAL if x.gross_yield is None else _clamp((x.gross_yield - 0.03) / 0.04),
        "affordability": _clamp(0.5 + (1 - x.median_ppm / ref_ppm) * 2.5),
        "stock": _clamp(x.good_stock / 30),
        "negotiability": _clamp(x.cut_share / 0.40),
        "momentum": NEUTRAL if x.trend_pct is None else _clamp(0.5 + x.trend_pct * 10),
    }


def _reasons(x: AreaInsight, ref_ppm: float) -> list[str]:
    """Candidate sentences keyed by component, strongest contribution first, 2–4 kept."""
    cands: list[tuple[float, str]] = []
    c = x.components
    if x.gross_yield is not None:
        n = f"{x.rent_samples} δείγματα" if x.rent_samples else "δείγματα μη καταγεγραμμένα"
        cands.append(
            (
                WEIGHTS["yield"] * c["yield"],
                f"Μικτή απόδοση {_pct(x.gross_yield, 1)}: ζητούμενο ενοίκιο "
                f"{f'{x.rent_ppm:.1f}'.replace('.', ',')} €/τ.μ./μήνα ({n}) έναντι "
                f"{_num(x.median_ppm)} €/τ.μ. ζητούμενης τιμής πώλησης.",
            )
        )
    gap = 1 - x.median_ppm / ref_ppm
    if gap > 0:
        cands.append(
            (
                WEIGHTS["affordability"] * c["affordability"],
                f"Διάμεση ζητούμενη τιμή {_num(x.median_ppm)} €/τ.μ., {_pct(gap)} κάτω από "
                f"τη διάμεση της ΒΑ Αθήνας ({_num(ref_ppm)} €/τ.μ.).",
            )
        )
    if x.good_stock:
        cands.append(
            (
                WEIGHTS["stock"] * c["stock"],
                f"{x.good_stock} διαθέσιμα διαμερίσματα έως 30 ετών, όχι ισόγεια, κάτω από "
                "τη διάμεση τιμή της ηλικιακής τους κατηγορίας.",
            )
        )
    if x.cut_share > 0 and x.median_cut_pct is not None:
        # Days on market is not quoted: it counts from when WE first saw the listing, so a
        # tracking gap makes it a lower bound (kept on the dataclass, not in the prose).
        cands.append(
            (
                WEIGHTS["negotiability"] * c["negotiability"],
                f"Το {_pct(x.cut_share)} των αγγελιών έχει μειώσει τιμή (διάμεση μείωση "
                f"{_pct(x.median_cut_pct, 1)}).",
            )
        )
    if x.trend_pct is not None and x.trend_pct >= RISING_TREND:
        cands.append(
            (
                WEIGHTS["momentum"] * c["momentum"],
                f"Ζητούμενη τιμή {_pct(x.trend_pct, 1)} πάνω από τον Ιούλιο "
                f"({_num(x.trend_early_ppm)} → {_num(x.trend_late_ppm)} €/τ.μ., "
                f"n={x.trend_early_n}/{x.trend_late_n}).",
            )
        )
    if x.value_band and x.value_band_discount and x.value_band_discount > 0:
        cands.append(
            (
                0.05,  # informative, not scored: ranks below the scored reasons
                f"Σε κτίρια {x.value_band} η τιμή είναι {_pct(x.value_band_discount)} "
                "χαμηλότερη από τα νεόδμητα (έως 5 ετών).",
            )
        )
    cands.sort(key=lambda t: -t[0])
    out = [s for _, s in cands[:4]]
    if len(out) < 2:
        out.append(
            f"{x.n_fresh} τρέχουσες αγγελίες, διάμεση ζητούμενη τιμή "
            f"{_num(x.median_ppm)} €/τ.μ."
        )
    return out


def _risks(x: AreaInsight) -> list[str]:
    risks = []
    if x.n_fresh < SMALL_SAMPLE:
        risks.append(f"Μικρό δείγμα: μόνο {x.n_fresh} τρέχουσες αγγελίες.")
    if x.trend_pct is not None and x.trend_pct <= FALLING_TREND:
        risks.append(
            f"Πτωτικές ζητούμενες τιμές: {_pct(x.trend_pct, 1)} από τον Ιούλιο "
            f"(n={x.trend_early_n}/{x.trend_late_n})."
        )
    if x.gross_yield is None:
        risks.append("Δεν υπάρχουν στοιχεία ενοικίων· η απόδοση δεν υπολογίστηκε.")
    elif x.gross_yield < LOW_YIELD:
        risks.append(f"Χαμηλή μικτή απόδοση ({_pct(x.gross_yield, 1)}) πριν από έξοδα και φόρους.")
    if x.old_share is not None and x.old_share >= OLD_STOCK_SHARE:
        risks.append(
            f"Παλαιό απόθεμα: το {_pct(x.old_share)} των αγγελιών με γνωστό έτος είναι "
            "κτίρια άνω των 30 ετών."
        )
    if x.trend_pct is None:
        risks.append(
            f"Τάση τιμών μη διαθέσιμη (n={x.trend_early_n}/{x.trend_late_n}, "
            f"απαιτούνται {MIN_TREND})."
        )
    if x.gross_yield is not None and x.rent_samples and x.rent_samples < FEW_RENT_SAMPLES:
        risks.append(f"Το ενοίκιο βασίζεται σε μόνο {x.rent_samples} αγγελίες ενοικίασης.")
    if x.gross_yield is not None and not x.rent_samples:
        risks.append("Ο αριθμός δειγμάτων του ενοικίου δεν έχει καταγραφεί.")
    if not risks:
        risks.append("Οι τιμές είναι ζητούμενες, όχι τιμές συναλλαγής.")
    return risks[:2]


# ---- public ------------------------------------------------------------------------------


def area_insights(
    listings: list[dict],
    rent_rows: list[dict] | None = None,
    *,
    areas: tuple[str, ...] | list[str] | None = None,
    year: int | None = None,
) -> tuple[list[AreaInsight], float | None]:
    """Metrics per area with at least MIN_FRESH fresh usable listings, plus the reference
    (median fresh €/m² over all eligible input). ``areas`` filters by ``search_area``."""
    year = year or date.today().year
    pool = [
        d for d in listings if _eligible(d) and (areas is None or d.get("search_area") in areas)
    ]
    fresh_all = [d for d in pool if d.get("is_fresh", True)]
    if not fresh_all:
        return [], None
    ref = statistics.median(d["price_per_m2"] for d in fresh_all)
    grouped: dict[str, list[dict]] = {}
    for d in pool:
        grouped.setdefault(area_name(d.get("neighborhood")), []).append(d)
    rents = rent_by_area(rent_rows or [])
    out = []
    for name, rows in sorted(grouped.items()):
        fresh = [d for d in rows if d.get("is_fresh", True)]
        if len(fresh) >= MIN_FRESH:
            out.append(_insight(name, fresh, rows, rents.get(name), year))
    return out, ref


def rank_areas(
    listings: list[dict],
    rent_rows: list[dict] | None = None,
    *,
    areas: tuple[str, ...] | list[str] | None = None,
    year: int | None = None,
) -> list[AreaInsight]:
    """Areas ranked for a buy-to-let private buyer, best first (see module docstring)."""
    insights, ref = area_insights(listings, rent_rows, areas=areas, year=year)
    for x in insights:
        x.components = _components(x, ref)
        x.score = round(100 * sum(WEIGHTS[k] * v for k, v in x.components.items()), 1)
        x.reasons = _reasons(x, ref)
        x.risks = _risks(x)
    return sorted(insights, key=lambda x: (-x.score, x.area))
