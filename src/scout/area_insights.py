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

Investor checks (round 3; shown, NOT in the score):

* ``MIN_MONTH`` — a month of the €/m² series (median first asking €/m² of the listings first
  seen that month) counts for the 6-month trend only with 15 listings; both ends need it.
* ``MIN_LIQ`` — liquidity (share of listings that disappeared within 30/60 days of first
  sighting) needs 30 listings in the cohort AND regular weekly scrapes: scrape days are
  the days on which any listing was seen; the cohort starts after the last gap longer than
  ``GAP_MAX`` days, a disappearance only counts when the next scrape day confirms it within
  ``GAP_MAX`` days, and a listing counts only when it is old enough to have been observed for
  the whole window. Label: γρήγορη ≥ 35 % gone in 60 days, αργή < 15 %, else μέτρια.
* supply per rent listing = fresh sale listings ÷ rent listings behind the area's rent median
  (``rent_comp.samples``); unknown when the sample count was not recorded.

Pure functions; no DB, no network.
"""

from __future__ import annotations

import bisect
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from .market_intel import AGE_BANDS, MIN_COMPS, _age, _usable, age_band, kind, municipality
from .metro_line4 import OPENING, line4_station, line4_stations, line4_text
from .regulatory import area_flags
from .regulatory import flags as regulatory_flags

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
# The latitude band alone does not catch them: XE resolves the "Irakleio" search to
# Heraklion, CRETE (bare "Ηράκλειο" plus Cretan villages such as Σκαλάνι or Αρχάνες), and
# enrichment places those card-only listings on the Attica search-area centroid. From such a
# search only listings naming a quarter in brackets ("Ηράκλειο (Ηπειρώτικα)") count, and its
# rent comparables are ignored. Attica-Heraklion flats still arrive via neighbouring searches.
CRETE_SEARCHES = frozenset({"Irakleio"})

# Trend cohorts: first seen in July vs last seen in late October (of the analysis year).
EARLY_MONTH = 7
LATE_FROM = (10, 16)
LATE_TO = (10, 31)

MIN_MONTH = 15
TREND_MONTHS = 12
MIN_LIQ = 30
GAP_MAX = 14  # days between scrape days that still count as "regular" scraping
FAST_GONE, SLOW_GONE = 0.35, 0.15  # share gone within 60 days
SUPPLY_LOW, SUPPLY_HIGH = 0.75, 1.5  # supply per rent listing vs the median of ranked areas

WEIGHTS = {
    "yield": 0.35,
    "affordability": 0.20,
    "stock": 0.20,
    "negotiability": 0.15,
    "momentum": 0.10,
}
NEUTRAL = 0.5
OLD_FROM = 16  # "old stock" for the new-build premium = 16+ years (AGE_BANDS 2..4)
DEFAULT_BUDGET = 300_000  # the buyer's stated budget (find page default)

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
    # New vs old stock inside the area (fresh flats, floor >= 1): median €/m² of ≤5-year
    # stock vs 16+-year stock; each needs MIN_BAND listings, else None.
    n_new: int = 0
    ppm_new: float | None = None
    n_old: int = 0
    ppm_old: float | None = None
    new_premium: float | None = None  # ppm_new / ppm_old − 1
    # Under construction among the new builds whose own page was read (is_unfinished).
    uc_unfinished: int = 0
    uc_checked: int = 0
    stations: list[str] = field(default_factory=list)  # rail stations of its neighbourhoods
    # Fresh, not-flagged ≤5-year flats priced within budget in a station neighbourhood.
    near_station_in_budget: int = 0
    near_station_in_budget_checked: int = 0  # …of which the listing page was read
    gross_yield_new: float | None = None  # 12 × rent / ppm_new (rent is area-wide, not new-only)
    yield_rank: int | None = None  # 1 = best gross yield among ranked areas with a rent
    yield_of: int = 0
    why: str = ""
    # --- investor checks (round 3) ---
    trend_series: list[tuple[str, float, int]] = field(default_factory=list)  # (YYYY-MM, €/m², n)
    trend_pct_6m: float | None = None  # last month vs 6 months earlier, both n >= MIN_MONTH
    trend_6m_n: tuple[int, int] = (0, 0)  # (n 6 months earlier, n last month)
    dom_n: int = 0
    gone_30: float | None = None
    gone_60: float | None = None
    gone_n_30: int = 0
    gone_n_60: int = 0
    liquidity: str | None = None  # γρήγορη / μέτρια / αργή, None = unknown
    regular_since: date | None = None  # first scrape day of the current regular run
    supply_per_rent: float | None = None
    supply_rel: float | None = None  # supply_per_rent ÷ median over ranked areas
    line4: list[str] = field(default_factory=list)  # Line 4 stations under construction
    reg_flags: list[str] = field(default_factory=list)


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
    if d.get("search_area") in CRETE_SEARCHES and "(" not in (d.get("neighborhood") or ""):
        return False
    lat = d.get("lat")
    return lat is None or ATTICA_LAT[0] <= lat <= ATTICA_LAT[1]


def _eligible(d: dict) -> bool:
    return _usable(d) and _in_attica(d) and bool(_GREEK.search(area_name(d.get("neighborhood"))))


def _upper_flat(d: dict) -> bool:
    """A flat (not a house/maisonette) on floor 1 or above; unknown floor does not qualify."""
    return kind(d) == "flat" and d.get("floor") is not None and d["floor"] >= 1


def short_station(label: str) -> str:
    """'ΗΣΑΠ Περισσός (Γραμμή 1)' → 'ΗΣΑΠ Περισσός'."""
    return label.split(" (")[0]


def _median(vals: list[float]) -> float | None:
    return statistics.median(vals) if vals else None


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _num(x: float) -> str:
    """Greek thousands separator: 2950 → '2.950'."""
    return f"{x:,.0f}".replace(",", ".")


def _pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f} %".replace(".", ",")


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
        if not r.get("rent_per_m2") or r.get("area") in CRETE_SEARCHES:
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
    unfinished: tuple[int, int] = (0, 0),
    budget: int = DEFAULT_BUDGET,
) -> AreaInsight:
    from .picks import station  # picks imports this module: import late

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

    new = [d["price_per_m2"] for d, a in ages if a is not None and a <= AGE_BANDS[0][1]]
    old = [d["price_per_m2"] for d, a in ages if a is not None and a >= OLD_FROM]
    ppm_new = statistics.median(new) if len(new) >= MIN_BAND else None
    ppm_old = statistics.median(old) if len(old) >= MIN_BAND else None
    stations = sorted({short_station(s) for d in everything if (s := station(d))})
    near = [
        d
        for d, a in ages
        if a is not None and a <= AGE_BANDS[0][1] and station(d) and d["price"] <= budget
    ]

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
        dom_n=len(doms),
        rent_ppm=rent_ppm,
        rent_samples=rent_n,
        gross_yield=12 * rent_ppm / median_ppm if rent_ppm else None,
        value_band=value_band,
        value_band_discount=value_disc,
        good_stock=good,
        old_share=sum(a > RECENT_MAX_AGE for a in known) / len(known) if known else None,
        unknown_age_share=1 - len(known) / len(fresh),
        n_new=len(new),
        ppm_new=ppm_new,
        n_old=len(old),
        ppm_old=ppm_old,
        new_premium=ppm_new / ppm_old - 1 if ppm_new and ppm_old else None,
        gross_yield_new=12 * rent_ppm / ppm_new if rent_ppm and ppm_new else None,
        uc_unfinished=unfinished[0],
        uc_checked=unfinished[1],
        stations=stations,
        line4=line4_stations(name),
        reg_flags=area_flags(name),
        near_station_in_budget=len(near),
        near_station_in_budget_checked=sum(bool(d.get("page_checked")) for d in near),
    )


# ---- trend series, liquidity, supply -----------------------------------------------------


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _months_back(end: date, k: int) -> str:
    m = end.year * 12 + end.month - 1 - k
    return f"{m // 12}-{m % 12 + 1:02d}"


def price_series(everything: list[dict], end: date) -> list[tuple[str, float, int]]:
    """Median first-asking €/m² of the listings first seen in each of the last TREND_MONTHS
    months (month of ``end`` included), with n. Months without listings are left out."""
    keys = {_months_back(end, k) for k in range(TREND_MONTHS)}
    by: dict[str, list[float]] = {}
    for d in everything:
        fs = _day(d.get("first_seen"))
        if fs and _month_key(fs) in keys:
            by.setdefault(_month_key(fs), []).append(_first_ppm(d))
    return [(k, statistics.median(v), len(v)) for k, v in sorted(by.items())]


def trend_6m(
    series: list[tuple[str, float, int]], end: date
) -> tuple[float | None, tuple[int, int]]:
    """(last month ÷ the month 6 earlier − 1, (n earlier, n last)); None unless both months
    have MIN_MONTH listings."""
    got = {k: (p, n) for k, p, n in series}
    old, new = got.get(_months_back(end, 6)), got.get(_month_key(end))
    ns = (old[1] if old else 0, new[1] if new else 0)
    if old and new and min(ns) >= MIN_MONTH:
        return new[0] / old[0] - 1, ns
    return None, ns


def scrape_context(rows: list[dict]) -> tuple[list[date], date | None]:
    """(sorted scrape days, first day of the current regular run). A scrape day is any day a
    listing was first or last seen; the regular run starts after the LAST gap > GAP_MAX days
    (None when there are no dates)."""
    days = sorted({x for d in rows for k in ("first_seen", "last_seen") if (x := _day(d.get(k)))})
    if not days:
        return [], None
    start = days[0]
    for a, b in zip(days, days[1:], strict=False):
        if (b - a).days > GAP_MAX:
            start = b
    return days, start


def liquidity_stats(
    rows: list[dict], days: list[date], start: date | None
) -> dict[int, tuple[float | None, int]]:
    """{window days: (share gone within the window | None, cohort n)} for windows 30 and 60.

    Cohort = listings first seen AFTER the first day of the regular run (earlier ones carry
    an unknown real age) and at least ``window`` days before the last scrape day; a gone
    listing counts only when the next scrape day after its ``last_seen`` is within GAP_MAX
    days (otherwise we do not know when it went). Share is None below MIN_LIQ."""
    out: dict[int, tuple[float | None, int]] = {30: (None, 0), 60: (None, 0)}
    if not days or start is None:
        return out
    end = days[-1]
    for w in out:
        n = gone = 0
        for d in rows:
            fs, ls = _day(d.get("first_seen")), _day(d.get("last_seen"))
            if not fs or not ls or fs <= start or (end - fs).days < w:
                continue
            is_gone = d.get("status") == "gone"
            if is_gone:
                i = bisect.bisect_right(days, ls)
                if i >= len(days) or (days[i] - ls).days > GAP_MAX:
                    continue
            n += 1
            gone += is_gone and (ls - fs).days <= w
        out[w] = (gone / n if n >= MIN_LIQ else None, n)
    return out


def liquidity_label(gone_60: float | None, gone_30: float | None = None) -> str | None:
    g = gone_60 if gone_60 is not None else gone_30
    if g is None:
        return None
    return "γρήγορη" if g >= FAST_GONE else "αργή" if g < SLOW_GONE else "μέτρια"


LIQUIDITY_THRESHOLDS = (
    f"γρήγορη: τουλάχιστον {_pct(FAST_GONE)} των αγγελιών φεύγουν σε 60 μέρες · "
    f"αργή: κάτω από {_pct(SLOW_GONE)} · αλλιώς μέτρια"
)


def n_words(a: int, b: int | None = None) -> str:
    """Sample sizes in words for a phone: «178 αγγελίες» / «62 και 243 αγγελίες»."""
    return f"{a} αγγελίες" if b is None else f"{a} και {b} αγγελίες"


def liquidity_text(x: AreaInsight) -> str:
    """«γρήγορη — 41 % έφυγαν σε 60 μέρες (210 αγγελίες), 22 % σε 30 (260 αγγελίες)» or the reason it is
    unknown. The thresholds are printed by the caller next to it (``LIQUIDITY_THRESHOLDS``)."""
    if x.liquidity is None:
        since = f", πρώτη τακτική {x.regular_since:%d/%m}" if x.regular_since else ""
        return f"άγνωστη — χρειάζεται ιστορικό σαρώσεων{since}"
    parts = []
    if x.gone_60 is not None:
        parts.append(f"{_pct(x.gone_60)} έφυγαν σε 60 μέρες ({n_words(x.gone_n_60)})")
    if x.gone_30 is not None:
        parts.append(f"{_pct(x.gone_30)} σε 30 ({n_words(x.gone_n_30)})")
    return f"{x.liquidity} — " + ", ".join(parts)


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
        n = f"{x.rent_samples} δείγματα" if x.rent_samples else "δείγματα: —"
        cands.append(
            (
                WEIGHTS["yield"] * c["yield"],
                f"Μικτή απόδοση {_pct(x.gross_yield, 1)}: ενοίκιο (εκτίμηση) "
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
                f"(από {_num(x.trend_early_ppm)} σε {_num(x.trend_late_ppm)} €/τ.μ., "
                f"{n_words(x.trend_early_n, x.trend_late_n)}).",
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
            f"({n_words(x.trend_early_n, x.trend_late_n)})."
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
            f"Τάση τιμών μη διαθέσιμη ({n_words(x.trend_early_n, x.trend_late_n)}, "
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
    budget: int = DEFAULT_BUDGET,
    lifecycle: list[dict] | None = None,
) -> tuple[list[AreaInsight], float | None]:
    """Metrics per area with at least MIN_FRESH fresh usable listings, plus the reference
    (median fresh €/m² over all eligible input). ``areas`` filters by ``search_area``.
    Flats only, floor 1 or above (``_upper_flat``).

    ``lifecycle`` = listings of EVERY status (active and gone) with ``status``,
    ``first_seen``, ``last_seen``; liquidity needs it (default: ``listings``, which the UI
    loads active-only, so liquidity is then unknown)."""
    year = year or date.today().year
    life_all = listings if lifecycle is None else lifecycle
    days, regular_start = scrape_context(life_all)
    seen = [x for d in listings if (x := _day(d.get("last_seen")))]
    end = max(seen) if seen else date.today()
    life_by_area: dict[str, list[dict]] = {}
    for d in life_all:
        if (
            _upper_flat(d)
            and (areas is None or d.get("search_area") in areas)
            and _eligible({**d, "is_unfinished": False})
        ):
            life_by_area.setdefault(area_name(d.get("neighborhood")), []).append(d)
    scope = [
        d for d in listings if _upper_flat(d) and (areas is None or d.get("search_area") in areas)
    ]
    pool = [d for d in scope if _eligible(d)]
    # Under construction among new builds whose own page was read. Flagged listings are not
    # "usable", so they are counted here from the same scope, not from the pool.
    unf: dict[str, list[int]] = {}
    for d in scope:
        if not (d.get("is_fresh", True) and d.get("page_checked")):
            continue
        if not _eligible({**d, "is_unfinished": False}):
            continue
        a = _age(d, year)
        if d.get("is_unfinished") or (a is not None and a <= AGE_BANDS[0][1]):
            c = unf.setdefault(area_name(d.get("neighborhood")), [0, 0])
            c[0] += bool(d.get("is_unfinished"))
            c[1] += 1
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
            x = _insight(
                name, fresh, rows, rents.get(name), year, tuple(unf.get(name, (0, 0))), budget
            )
            x.trend_series = price_series(rows, end)
            x.trend_pct_6m, x.trend_6m_n = trend_6m(x.trend_series, end)
            stats = liquidity_stats(life_by_area.get(name, []), days, regular_start)
            (x.gone_30, x.gone_n_30), (x.gone_60, x.gone_n_60) = stats[30], stats[60]
            x.liquidity = liquidity_label(x.gone_60, x.gone_30)
            x.regular_since = regular_start
            if x.rent_samples:
                x.supply_per_rent = x.n_fresh / x.rent_samples
            out.append(x)
    ratios = [x.supply_per_rent for x in out if x.supply_per_rent]
    if ratios:
        mid = statistics.median(ratios)
        for x in out:
            x.supply_rel = x.supply_per_rent / mid if x.supply_per_rent else None
    return out, ref


def rank_areas(
    listings: list[dict],
    rent_rows: list[dict] | None = None,
    *,
    areas: tuple[str, ...] | list[str] | None = None,
    year: int | None = None,
    budget: int = DEFAULT_BUDGET,
    lifecycle: list[dict] | None = None,
) -> list[AreaInsight]:
    """Areas ranked for a buy-to-let private buyer, best first (see module docstring)."""
    insights, ref = area_insights(
        listings, rent_rows, areas=areas, year=year, budget=budget, lifecycle=lifecycle
    )
    by_yield = sorted(
        (x for x in insights if x.gross_yield is not None), key=lambda x: -x.gross_yield
    )
    for i, x in enumerate(by_yield, 1):
        x.yield_rank, x.yield_of = i, len(by_yield)
    for x in insights:
        x.components = _components(x, ref)
        x.score = round(100 * sum(WEIGHTS[k] * v for k, v in x.components.items()), 1)
        x.reasons = _reasons(x, ref)
        x.risks = _risks(x)
        x.why = why(x)
    return sorted(insights, key=lambda x: (-x.score, x.area))


# ---- the explained "why" and the decision sentences --------------------------------------


def _rent(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def why(x: AreaInsight) -> str:
    """One line of numbers, filled from the fields — no adjectives. Parts whose data is
    missing are left out (never guessed)."""
    parts = []
    if x.gross_yield is not None:
        n = f" από {x.rent_samples} αγγελίες ενοικίασης" if x.rent_samples else ""
        of = "περιοχή" if x.yield_of == 1 else "περιοχές"
        rank = f" ({x.yield_rank}η από {x.yield_of} {of} με ενοίκιο)" if x.yield_rank else ""
        parts.append(
            f"Μικτή απόδοση {_pct(x.gross_yield, 1)}{rank} με ενοίκιο (εκτίμηση) "
            f"{_rent(x.rent_ppm)} €/τ.μ.{n}"
        )
    if x.new_premium is not None:
        word = "ακριβότερα" if x.new_premium >= 0 else "φθηνότερα"
        parts.append(
            f"νεόδμητα {_pct(abs(x.new_premium))} {word} από τα παλιά ({n_words(x.n_new, x.n_old)})"
        )
    if x.stations:
        parts.append(", ".join(x.stations[:2]))
    return (
        "· ".join(parts) if parts else f"{x.n_fresh} αγγελίες, διάμεση {_num(x.median_ppm)} €/τ.μ."
    )


def decision(ranked: list[AreaInsight], budget: int = DEFAULT_BUDGET) -> list[str]:
    """The buyer's answer in up to three short sentences, each computed from ``ranked`` with
    its numbers inline: best yield, deepest market without falling prices, and most new flats
    within budget in a neighbourhood with a rail station."""
    out = []
    solid = [x for x in ranked if x.n_fresh >= SMALL_SAMPLE]
    small = " Μικρό δείγμα." if ranked and not solid else ""
    solid = solid or ranked  # nothing reaches SMALL_SAMPLE: still answer, and say so
    ys = [x for x in solid if x.gross_yield is not None]
    if ys:
        x = max(ys, key=lambda a: a.gross_yield)
        new_y = (
            f" ({_pct(x.gross_yield_new, 1)} στα νεόδμητα)" if x.gross_yield_new is not None else ""
        )
        out.append(
            f"Για απόδοση: {x.area}, μικτή απόδοση {_pct(x.gross_yield, 1)} στα παλιά{new_y}, "
            f"ενοίκιο (εκτίμηση) {_rent(x.rent_ppm)} €/τ.μ. από ζητούμενα ενοίκια της περιοχής, "
            f"{x.n_fresh} αγγελίες πώλησης.{small}"
        )
    ok = [x for x in solid if x.trend_pct is None or x.trend_pct > FALLING_TREND]
    if ok:
        known = [a for a in ok if a.gone_60 is not None or a.gone_30 is not None]
        if known:
            x = max(known, key=lambda a: (a.gone_60 if a.gone_60 is not None else a.gone_30))
            out.append(
                f"Για ρευστότητα: {x.area}, {liquidity_text(x)}, " f"{x.n_fresh} αγγελίες.{small}"
            )
        else:
            x = max(ok, key=lambda a: a.n_fresh)
            dom = f", διάμεσα {x.median_dom:.0f} μέρες στην αγορά" if x.median_dom else ""
            out.append(
                f"Για ρευστότητα: {x.area}, {x.n_fresh} αγγελίες, "
                f"{_pct(x.cut_share)} με μείωση τιμής{dom}.{small}"
            )
    grow = [(t, x) for x in solid if (t := exit_trend(x)) is not None]
    if grow:
        t, x = max(grow, key=lambda p: p[0][0])
        l4 = (
            f" — Γραμμή 4 υπό κατασκευή ({', '.join(x.line4)}, ορίζοντας {OPENING})"
            if x.line4
            else ""
        )
        out.append(f"Για ανατίμηση: {x.area}{l4}, {_signed(t[0])} €/τ.μ. {t[1]} ({t[2]}).{small}")
    else:
        out.append(
            "Για ανατίμηση: δεν υπάρχει αρκετό ιστορικό τιμών "
            f"(χρειάζονται τουλάχιστον {MIN_MONTH} αγγελίες ανά μήνα ή {MIN_TREND} στις δύο ομάδες)."
        )
    near = max(ranked, key=lambda a: a.near_station_in_budget, default=None)
    b = f"{_num(budget)} €"
    if near is not None and near.near_station_in_budget:
        st = ", ".join(near.stations[:2])
        out.append(
            f"Για νεόδμητο κοντά σε σταθμό έως {b}: {near.area} ({st}), "
            f"{near.near_station_in_budget} αγγελίες, "
            f"{near.near_station_in_budget_checked} με ελεγμένη περιγραφή."
        )
    else:
        out.append(f"Νεόδμητο έως {b} σε γειτονιά με σταθμό: δεν βρέθηκε αγγελία.")
    return out


# ---- the six checks of a buy-to-let investor ---------------------------------------------

GOOD, MID, WARN, UNKNOWN = "καλό", "μέτριο", "προσοχή", "άγνωστο"
GOOD_YIELD = 0.05  # gross; below LOW_YIELD (4 %) is a warning
TOO_CHEAP = -0.35  # market_intel: > 35 % under the comps median is a warning, never a bonus
CHEAP, DEAR = -0.05, 0.05
EXIT_UP, EXIT_DOWN = 0.02, -0.02


def exit_trend(x: AreaInsight) -> tuple[float, str, str] | None:
    """(change, "σε 6 μήνες" | "από τον Ιούλιο", "62 και 243 αγγελίες") — the 6-month change when both
    months have enough listings, else the July→late-October change; None when neither."""
    if x.trend_pct_6m is not None:
        return x.trend_pct_6m, "σε 6 μήνες", n_words(*x.trend_6m_n)
    if x.trend_pct is not None:
        return x.trend_pct, "από τον Ιούλιο", n_words(x.trend_early_n, x.trend_late_n)
    return None


def _signed(x: float, digits: int = 1) -> str:
    s = _pct(abs(x), digits)
    return f"+{s}" if x > 0 else f"−{s}" if x < 0 else s


def investor_checks(d: dict, intel, insight: AreaInsight | None) -> list[tuple[str, str, str]]:
    """Six labelled checks for one listing: (label, value with number and basis, verdict).

    verdict ∈ {καλό, μέτριο, προσοχή, άγνωστο}. ``intel`` = ``market_intel.Intel`` (or None),
    ``insight`` = the listing's area (or None). Nothing is guessed: a check without its data
    says «άγνωστο» and why."""
    out = []

    # 1. price vs comparables
    comps = intel.comps(d) if intel is not None else None
    if comps is None:
        out.append(("Τιμή έναντι παρόμοιων", f"λιγότερα από {MIN_COMPS} παρόμοια", UNKNOWN))
    else:
        pct = comps["pct"]
        v = WARN if pct <= TOO_CHEAP or pct >= DEAR else GOOD if pct <= CHEAP else MID
        note = " — υπερβολικά φθηνό, έλεγξε γιατί" if pct <= TOO_CHEAP else ""
        out.append(
            (
                "Τιμή έναντι παρόμοιων",
                f"{_num(d['price_per_m2'])} €/τ.μ. έναντι διάμεσης {_num(comps['ppm'])} "
                f"€/τ.μ. ({_signed(pct)}), Παρόμοια ({comps['n']}): {comps['label']}{note}",
                v,
            )
        )

    # 2. yield
    gy, rent_m = d.get("gross_yield"), d.get("est_monthly_rent")
    if gy and rent_m and d.get("price"):
        basis = "εκτίμηση από ζητούμενα ενοίκια περιοχής" if d.get("rent_estimated") else "αγγελία"
        v = GOOD if gy >= GOOD_YIELD else WARN if gy < LOW_YIELD else MID
        out.append(
            (
                "Μικτή απόδοση",
                f"{_pct(gy, 1)} = 12 × {_num(rent_m)} €/μήνα ({basis}) ÷ "
                f"{_num(d['price'])} €, πριν από έξοδα και φόρους",
                v,
            )
        )
    else:
        out.append(("Μικτή απόδοση", "άγνωστη — δεν υπάρχει εκτίμηση ενοικίου", UNKNOWN))

    # 3. liquidity of the area
    if insight is None:
        out.append(("Ρευστότητα περιοχής", "δεν αξιολογείται η περιοχή (λίγες αγγελίες)", UNKNOWN))
    else:
        v = {"γρήγορη": GOOD, "μέτρια": MID, "αργή": WARN}.get(insight.liquidity or "", UNKNOWN)
        out.append(
            (
                f"Ρευστότητα περιοχής ({insight.area})",
                liquidity_text(insight)
                + (f" · {LIQUIDITY_THRESHOLDS}" if insight.liquidity else ""),
                v,
            )
        )

    # 4. rental demand
    if insight is None or insight.supply_per_rent is None:
        out.append(
            (
                "Ζήτηση ενοικίου",
                "άγνωστη — δεν έχει καταγραφεί ο αριθμός αγγελιών ενοικίασης",
                UNKNOWN,
            )
        )
    else:
        rel = insight.supply_rel
        v = (
            UNKNOWN
            if rel is None
            else GOOD if rel <= SUPPLY_LOW else WARN if rel >= SUPPLY_HIGH else MID
        )
        out.append(
            (
                "Ζήτηση ενοικίου",
                f"{_rent_ratio(insight.supply_per_rent)} αγγελίες πώλησης ανά αγγελία "
                f"ενοικίασης ({insight.n_fresh} πώλησης / {insight.rent_samples} ενοικίασης)· "
                f"καλό έως {SUPPLY_LOW} και προσοχή από {SUPPLY_HIGH} φορές τη διάμεση των περιοχών",
                v,
            )
        )

    # 5. legal / regulatory
    reg = regulatory_flags(d)
    if reg:
        short_let = any(r.startswith("Βραχυχρόνια") for r in reg)
        frozen = any("δεν εκδίδεται" in r for r in reg)
        v = WARN if frozen else MID if short_let else GOOD
        out.append(("Νομικά / κανονιστικά", "· ".join(reg), v))
    elif d.get("neighborhood"):
        out.append(
            (
                "Νομικά / κανονιστικά",
                "κανένας περιορισμός βραχυχρόνιας μίσθωσης στα δεδομένα μας "
                "(δεν αντικαθιστά νομικό έλεγχο)",
                GOOD,
            )
        )
    else:
        out.append(("Νομικά / κανονιστικά", "άγνωστη περιοχή", UNKNOWN))

    # 6. exit: €/m² trend of the area (+ Line 4 when its sub-area is named after a station)
    t = exit_trend(insight) if insight is not None else None
    st_name = line4_station(d)
    l4 = (
        f" · Μετρό Γραμμή 4 υπό κατασκευή: {st_name} (ορίζοντας {OPENING})"
        if st_name
        else (f" · {line4_text(insight.line4)}" if insight is not None and insight.line4 else "")
    )
    if t is None:
        series = "δεν υπάρχει αρκετό ιστορικό" + (
            f" ({n_words(insight.trend_early_n, insight.trend_late_n)})"
            if insight is not None
            else ""
        )
        out.append(("Έξοδος (τάση €/τ.μ.)", series + l4, UNKNOWN))
    else:
        v = GOOD if t[0] >= EXIT_UP else WARN if t[0] <= EXIT_DOWN else MID
        out.append(
            (
                "Έξοδος (τάση €/τ.μ.)",
                f"{_signed(t[0])} {t[1]} στη διάμεση ζητούμενη €/τ.μ. της περιοχής ({t[2]})"
                f"{l4}",
                v,
            )
        )
    return out


def _rent_ratio(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")
