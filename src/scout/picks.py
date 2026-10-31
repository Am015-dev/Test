"""«Βρες μου σπίτι»: the best few listings for a budget, explained like an advisor would.

The buyer states a budget, a maximum building age and whether the flat must be next to a rail
station; this ranks the matching listings by what a buy-to-let investor cares about — a page
we have read first, real photos, then rent return, price against like-for-like flats, room to
negotiate — and writes one short line per number with its basis. When too little qualifies,
``relaxations`` says which single rule to loosen and exactly how many flats that adds (same
``find`` logic, not an estimate). Pure functions over the listing dicts the UI already loads.

Ranking by goal (the «Οδηγός» question «Τι σε νοιάζει πιο πολύ;»). Every listing gets four
part scores, in points; ``rank_score`` = Σ ``GOAL_WEIGHTS[goal][part]`` × part. The sort is
always: page read first, then >2 photos, then ``rank_score`` — a goal never lifts an unread
page above a read one.

=========  ===============================================================================
part       points
=========  ===============================================================================
yield      1000 × gross yield (4,5 % → 45)
value      price vs comparables (−15 %…+25 % → −6…+10) + 3 finished before this year
           + 2 at 90+ days on market − 20 if >35 % under comparables (a warning, not a bonus)
safety     6 each: page read · >2 photos · energy class stated · ≥8 comparables
           · established area (≥50 active listings) · steady area (days-on-market
           spread: stdev ≤ mean)
growth     12 station today (from the neighbourhood name) · 12 Metro Line 4 station planned
           in the area (``metro_line4`` when present) · 6 area new-build premium ≤15 %
           (``area_insights``, needs ``area_facts``)
=========  ===============================================================================

=========  =====  =====  ======  ======
goal       yield  value  safety  growth
=========  =====  =====  ======  ======
yield      1.0    1.0    0.25    0.25
safety     0.4    0.6    1.0     0.25
growth     0.4    0.6    0.25    1.0
=========  =====  =====  ======  ======

With ``loan=True`` each pick carries the monthly instalment of a 70 % loan at 4 % over 25
years (annuity) and ``cashflow`` = rent estimate − instalment.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from .area_insights import area_name
from .finance import acquisition_costs
from .market_intel import Intel

# XE sub-areas that ARE a rail station's neighbourhood (walkable), by name. Listings carry only
# the neighbourhood (no exact address), so this is the honest proximity signal we have.
STATIONS: dict[str, str] = {
    "Αμπελόκηπ": "Μετρό Αμπελόκηποι (Γραμμή 3)",
    "Πανόρμου": "Μετρό Πανόρμου (Γραμμή 3)",
    "Περισσός": "ΗΣΑΠ Περισσός (Γραμμή 1)",
    "Νέα Ιωνία (Κέντρο)": "ΗΣΑΠ Νέα Ιωνία (Γραμμή 1)",
    "Μαρούσι (Κέντρο)": "ΗΣΑΠ Μαρούσι (Γραμμή 1)",
    "Σταθμός ΗΣΑΠ Ταύρου": "ΗΣΑΠ Ταύρος (Γραμμή 1)",
    "Ταύρος Αττικής (Κέντρο)": "ΗΣΑΠ Ταύρος (Γραμμή 1)",
    "Δάφνη Αττικής (Κέντρο)": "Μετρό Δάφνη (Γραμμή 2)",
    "Άγιος Δημήτριος Αττικής (Κέντρο)": "Μετρό Άγιος Δημήτριος (Γραμμή 2)",
}
NEW_YEARS = 10  # "new" = built or renovated within this many years
AGE_STEPS = (5, 10, 15, 20)  # the building-age limits the page offers
BUDGET_BAND = 0.12  # ± around the stated budget
TOP = 3
PAGE = 10  # the «Οδηγός» shows the ranking 10 at a time

GOALS = ("yield", "safety", "growth")
GOAL_WEIGHTS: dict[str, dict[str, float]] = {
    "yield": {"yield": 1.0, "value": 1.0, "safety": 0.25, "growth": 0.25},
    "safety": {"yield": 0.4, "value": 0.6, "safety": 1.0, "growth": 0.25},
    "growth": {"yield": 0.4, "value": 0.6, "safety": 0.25, "growth": 1.0},
}
SAFETY_PTS = 6
STATION_PTS, LINE4_PTS, LOW_PREMIUM_PTS = 12, 12, 6
ESTABLISHED = 50  # active listings in the area
MANY_COMPS = 8
LOW_PREMIUM = 0.15
# The loan the «με δάνειο» answer assumes.
LTV, RATE, YEARS = 0.70, 0.04, 25


def instalment(price: float, ltv: float = LTV, rate: float = RATE, years: int = YEARS) -> float:
    """Monthly annuity payment on a ``ltv`` × ``price`` loan."""
    principal, r, n = price * ltv, rate / 12, years * 12
    return principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)


def line4_station(area: str) -> str | None:
    """The planned Metro Line 4 station in ``area`` (``metro_line4``, written by the insights
    workstream), or None — also when that module is not there yet."""
    try:
        from . import metro_line4
    except ImportError:
        return None
    for name in ("station_for_area", "for_area", "planned_station"):
        fn = getattr(metro_line4, name, None)
        if callable(fn):
            got = fn(area)
            if got:
                return got if isinstance(got, str) else str(getattr(got, "name", got))
            return None
    table = getattr(metro_line4, "STATIONS", None) or ()
    for row in table:
        a = row.get("area") if isinstance(row, dict) else getattr(row, "area", None)
        if a and (a == area or a in area):
            name = row.get("station") if isinstance(row, dict) else getattr(row, "station", None)
            return name or a
    return None


def area_stats(listings: list[dict]) -> dict[str, tuple[int, float | None, float | None]]:
    """area → (active listings, mean days on market, stdev of days on market)."""
    by: dict[str, list[int]] = {}
    count: dict[str, int] = {}
    for d in listings:
        if not d.get("is_fresh", True):
            continue
        a = area_name(d.get("neighborhood"))
        count[a] = count.get(a, 0) + 1
        if d.get("days_on_market"):
            by.setdefault(a, []).append(d["days_on_market"])
    out = {}
    for a, n in count.items():
        doms = by.get(a, [])
        mean = statistics.mean(doms) if len(doms) >= 5 else None
        sd = statistics.stdev(doms) if len(doms) >= 5 else None
        out[a] = (n, mean, sd)
    return out


def station(d: dict) -> str | None:
    hood = d.get("neighborhood") or ""
    return next((s for key, s in STATIONS.items() if key in hood), None)


def rent_index(rent_rows: list[dict]) -> dict[str, tuple[float, int]]:
    """neighbourhood → (median asking rent €/m²/month, samples)."""
    return {
        r["neighborhood"]: (r["rent_per_m2"], r.get("samples") or 0)
        for r in rent_rows
        if r.get("neighborhood") and r.get("rent_per_m2")
    }


def area_rent(d: dict, rents: dict[str, tuple[float, int]]) -> tuple[float, int, str] | None:
    """Rent €/m² for the listing's own neighbourhood, else the median over its area."""
    hood = d.get("neighborhood") or ""
    if hood in rents:
        return rents[hood][0], rents[hood][1], hood
    area = area_name(hood)
    near = [v[0] for k, v in rents.items() if area_name(k) == area]
    if len(near) >= 2:
        return statistics.median(near), 0, area
    return None


@dataclass
class Pick:
    listing: dict
    rank_score: float
    rent: int
    rent_low: int
    rent_high: int
    gross: float
    net: float
    offer: int
    station: str | None
    checked: bool = False
    few_photos: bool = False
    status: str = ""  # first line under the title: page read or not
    lines: list[str] = field(default_factory=list)  # one short line per number, with its basis
    risks: list[str] = field(default_factory=list)
    excerpt: str | None = None  # the listing's own description, first ~300 characters
    parts: dict[str, float] = field(default_factory=dict)  # yield/value/safety/growth points
    reasons: dict[str, list[str]] = field(default_factory=dict)  # part → what earned points
    instalment: int = 0  # €/month on a 70 % / 4 % / 25-year loan
    cashflow: int = 0  # rent − instalment, €/month
    loan: bool = False  # the buyer said «με δάνειο»: show the instalment line
    goal: str = "yield"
    offer_line: str = ""

    @property
    def loan_line(self) -> str:
        """'Δόση ~1.110 €/μήνα → λείπουν 120 €' (or 'μένουν'), the «με δάνειο» answer."""
        left = (
            f"μένουν {_eur(self.cashflow)}"
            if self.cashflow >= 0
            else f"λείπουν {_eur(-self.cashflow)}"
        )
        return (
            f"Δόση ~{_eur(self.instalment)}/μήνα (δάνειο {round(LTV * 100)} %, "
            f"{gr_num(RATE * 100).replace(',0', '')} %, {YEARS} έτη) → {left}"
        )

    def sort_key(self) -> tuple:
        # A page we have read beats one we have not, whatever its yield; real photos beat
        # "≤2 photos" (often a render or a logo); then the investor ranking.
        return (self.checked, not self.few_photos, self.rank_score)


def _r(x: float, step: int) -> int:
    return int(round(x / step) * step)


def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def gr_pct(x: float) -> str:
    """0.047 → '4,7 %'."""
    return f"{x * 100:.1f} %".replace(".", ",")


def gr_num(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


CHECKED = "Ελέγχθηκε η περιγραφή{when} — δεν αναφέρει κατασκευή σε εξέλιξη"
UNCHECKED = "Δεν έχει ελεγχθεί ακόμα η σελίδα της αγγελίας"
FEW_PHOTOS = "≤2 φωτογραφίες — συχνά μόνο render ή λογότυπο"
EXCERPT_CHARS = 300


def status_line(d: dict) -> str:
    if not d.get("page_checked"):
        return UNCHECKED
    when = d.get("page_checked_at")
    return CHECKED.format(when=f" ({when:%d/%m/%Y})" if isinstance(when, (date, datetime)) else "")


def excerpt(text: str | None, limit: int = EXCERPT_CHARS) -> str | None:
    """The first ``limit`` characters of the listing's description, cut at a word."""
    text = " ".join((text or "").split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:—-") + "…"


def _build(
    d: dict,
    intel: Intel,
    rents: dict,
    year: int,
    stats: dict | None = None,
    area_facts: dict | None = None,
) -> Pick | None:
    """Everything about one listing that does not depend on the buyer's filters or goal."""
    rent_basis = area_rent(d, rents)
    if rent_basis is None:
        return None
    per_m2, _samples, where = rent_basis
    built = d.get("renovated_year") or d.get("year_built")
    new_premium = 1.1 if built and year - built <= 5 else 1.0  # new stock rents higher
    rent = per_m2 * d["area_m2"] * new_premium
    gross = 12 * rent / d["price"]
    costs = acquisition_costs(d["price"], bool(d.get("is_private_seller"))) or 0
    # Net (Greek practice: the tenant pays κοινόχρηστα): 1 month empty a year, 15% rental
    # tax, 5% upkeep, ENFIA ~3 €/m² a year; on price + purchase costs.
    net_income = rent * 11 * (1 - 0.15 - 0.05) - 3 * d["area_m2"]
    net = net_income / (d["price"] + costs)
    cmp = intel.comps(d)
    gap = -cmp["pct"] if cmp else 0.0
    dom = d.get("days_on_market") or 0
    offer_cut = 0.03 + (0.03 if dom >= 90 else 0) + (0.02 if d.get("is_private_seller") else 0)
    offer = _r(d["price"] * (1 - offer_cut), 1000)
    too_cheap = gap > 0.35
    checked = bool(d.get("page_checked"))
    few = bool(d.get("few_photos"))
    st_name = station(d)
    value = (
        max(min(gap, 0.25), -0.15) * 40
        + (3 if built and built <= year - 1 else 0)  # finished, not "delivery this year"
        + (2 if dom >= 90 else 0)
        - (20 if too_cheap else 0)
    )
    area = area_name(d.get("neighborhood"))
    n_area, dom_mean, dom_sd = (stats or {}).get(area, (0, None, None))
    safe = [
        ("ελέγχθηκε η σελίδα", checked),
        ("πάνω από 2 φωτογραφίες", (d.get("photo_count") or 0) > 2),
        ("δηλώνει ενεργειακή κλάση", bool(d.get("energy_class"))),
        (f"{cmp['n'] if cmp else 0} παρόμοια", bool(cmp and cmp["n"] >= MANY_COMPS)),
        (f"{n_area} αγγελίες στην περιοχή", n_area >= ESTABLISHED),
        ("σταθερός χρόνος πώλησης στην περιοχή", bool(dom_mean and dom_sd <= dom_mean)),
    ]
    fact = (area_facts or {}).get(area)
    prem = getattr(fact, "new_premium", None)
    l4 = line4_station(area)
    grow = [
        (st_name or "", bool(st_name), STATION_PTS),
        (f"Γραμμή 4: {l4}" if l4 else "", bool(l4), LINE4_PTS),
        (
            f"νεόδμητα +{round(prem * 100)} % στην περιοχή" if prem is not None else "",
            prem is not None and prem <= LOW_PREMIUM,
            LOW_PREMIUM_PTS,
        ),
    ]
    parts = {
        "yield": gross * 1000,  # rent return
        "value": value,
        "safety": SAFETY_PTS * sum(ok for _, ok in safe),
        "growth": sum(pts for _, ok, pts in grow if ok),
    }
    reasons = {
        "safety": [t for t, ok in safe if ok],
        "growth": [t for t, ok, _ in grow if ok],
    }
    rank = score(parts, "yield")
    inst = instalment(d["price"])
    lines = [
        f"Ενοίκιο (εκτίμηση) ~{_eur(_r(rent, 10))}/μήνα ({gr_num(per_m2)} €/τ.μ. × "
        f"{d['area_m2']:g} τ.μ." + (", +10 % νεόδμητο" if new_premium > 1 else "") + ")",
        f"Μικτή απόδοση {gr_pct(gross)} · Καθαρή ~{gr_pct(net)}",
    ]
    ppm = d.get("price_per_m2") or d["price"] / d["area_m2"]
    if cmp:
        pct = round(abs(cmp["pct"]) * 100)
        rel = (
            f"όσο τα {cmp['n']} παρόμοια"
            if pct < 2
            else f"{pct} % {'κάτω' if cmp['pct'] < 0 else 'πάνω'} από {cmp['n']} παρόμοια"
        )
        lines.append(f"Τιμή {_eur(ppm)}/τ.μ. — {rel}")
    else:
        lines.append(f"Τιμή {_eur(ppm)}/τ.μ. — λιγότερα από 5 παρόμοια για σύγκριση")
    if st_name:
        lines.append(f"Σταθμός {st_name} — από το όνομα της γειτονιάς")
    lines.append(
        " · ".join(
            x
            for x in (
                f"Κτίριο {d.get('year_built') or '—'}"
                + (f", ανακαίνιση {d['renovated_year']}" if d.get("renovated_year") else ""),
                f"{d['floor']:g}ος όροφος" if d.get("floor") is not None else "",
                f"{d['area_m2']:g} τ.μ.",
                f"{d['bedrooms']} υπνοδωμάτια" if d.get("bedrooms") else "",
            )
            if x
        )
    )
    offer_line = (
        (f"{dom} μέρες στην αγορά → ξεκίνα" if dom else "Προσφορά: ξεκίνα")
        + f" από ~{_eur(offer)}"
        + (" (ιδιώτης πωλητής)" if d.get("is_private_seller") else "")
    )
    lines.append(offer_line)
    risks = []
    if few:
        risks.append(FEW_PHOTOS)
    if built == year:
        risks.append("Έτος κατασκευής φέτος: βεβαιώσου ότι έχει παραδοθεί και έχει άδεια.")
    if too_cheap:
        risks.append("Ασυνήθιστα φθηνό για τα παρόμοια — έλεγξε τ.μ., κατάσταση, νομικά.")
    if where != d.get("neighborhood"):
        risks.append(f"Ενοίκιο από την ευρύτερη περιοχή «{where}» — λίγα στοιχεία για τη γειτονιά.")
    if cmp and cmp["n"] < 8:
        risks.append(f"Μόνο {cmp['n']} παρόμοια για σύγκριση — μικρό δείγμα.")
    if not d.get("energy_class"):
        risks.append("Η ενεργειακή κλάση δεν δηλώνεται — ζήτα το πιστοποιητικό.")
    return Pick(
        listing=d,
        rank_score=rank,
        rent=_r(rent, 10),
        rent_low=_r(rent * 0.9, 10),
        rent_high=_r(rent * 1.1, 10),
        gross=gross,
        net=net,
        offer=offer,
        station=st_name,
        checked=checked,
        few_photos=few,
        status=status_line(d),
        lines=lines,
        risks=risks[:3],
        excerpt=excerpt(d.get("description")),
        parts=parts,
        reasons=reasons,
        instalment=_r(inst, 10),
        cashflow=_r(rent - inst, 10),
        offer_line=offer_line,
    )


def score(parts: dict[str, float], goal: str) -> float:
    w = GOAL_WEIGHTS.get(goal, GOAL_WEIGHTS["yield"])
    return sum(w[k] * parts.get(k, 0.0) for k in w)


def _bedrooms_ok(d: dict, bedrooms: int | None) -> bool:
    """``bedrooms`` 1 or 2 = exactly that; 3 = three or more; None = any."""
    if bedrooms is None:
        return True
    n = d.get("bedrooms")
    return n is not None and (n >= 3 if bedrooms >= 3 else n == bedrooms)


def find(
    listings: list[dict],
    intel: Intel,
    rent_rows: list[dict],
    budget: int,
    *,
    max_age: int | None = NEW_YEARS,
    near_rail: bool = True,
    checked_only: bool = False,
    areas: list[str] | None = None,
    bedrooms: int | None = None,
    goal: str = "yield",
    loan: bool = False,
    area_facts: dict | None = None,
    year: int | None = None,
    top: int = TOP,
    memo: dict | None = None,
) -> list[Pick]:
    """The ``top`` listings for ``budget`` (± BUDGET_BAND): read pages first, then real
    photos, then ``rank_score`` for ``goal`` (module docstring). ``max_age=None`` = any
    building age; ``areas`` = area names (``area_insights.area_name``); ``bedrooms`` see
    ``_bedrooms_ok``; ``area_facts`` = area → ``AreaInsight`` for the growth part. ``memo``
    caches the per-listing work between calls that only differ in the filters."""
    year = year or date.today().year
    rents = rent_index(rent_rows)
    memo = {} if memo is None else memo
    if "_stats" not in memo:
        memo["_stats"] = area_stats(listings)
    stats = memo["_stats"]
    lo, hi = budget * (1 - BUDGET_BAND), budget * (1 + BUDGET_BAND)
    out: list[Pick] = []
    for d in listings:
        if not d.get("is_fresh", True) or d.get("excluded") or d.get("is_suspect"):
            continue
        if d.get("is_unfinished") or not d.get("price") or not d.get("area_m2"):
            continue
        if not lo <= d["price"] <= hi or (d.get("floor") is not None and d["floor"] < 1):
            continue
        built = d.get("renovated_year") or d.get("year_built")
        if max_age is not None and not (built and year - max_age <= built <= year):
            continue
        if near_rail and not station(d):
            continue
        if checked_only and not d.get("page_checked"):
            continue
        if areas and area_name(d.get("neighborhood")) not in areas:
            continue
        if not _bedrooms_ok(d, bedrooms):
            continue
        if id(d) not in memo:
            memo[id(d)] = _build(d, intel, rents, year, stats, area_facts)
        if (p := memo[id(d)]) is not None:
            out.append(replace(p, rank_score=score(p.parts, goal), loan=loan, goal=goal))
    out.sort(key=Pick.sort_key, reverse=True)
    # One flat per building/listing group: skip near-identical units of the same block.
    seen: set[tuple] = set()
    unique = []
    for p in out:
        d = p.listing
        key = (d.get("neighborhood"), d.get("year_built"), round(d["price"], -4))
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique[:top]


@dataclass
class Relax:
    """One rule loosened, and exactly what it adds (counted with ``find``)."""

    label: str
    changes: dict  # find() keyword → new value; "budget" is the budget itself
    added: int
    added_checked: int

    @property
    def text(self) -> str:
        return f"{self.label} (+{self.added}" + (
            f", {self.added_checked} ελεγμένες)" if "checked_only" not in self.changes else ")"
        )


def relaxations(
    listings: list[dict],
    intel: Intel,
    rent_rows: list[dict],
    budget: int,
    *,
    max_age: int | None = NEW_YEARS,
    near_rail: bool = True,
    checked_only: bool = False,
    areas: list[str] | None = None,
    bedrooms: int | None = None,
    goal: str = "yield",
    area_facts: dict | None = None,
    year: int | None = None,
    limit: int = 4,
) -> list[Relax]:
    """Up to ``limit`` single-rule relaxations that add flats, each with its exact count."""
    memo: dict = {}
    now = {"budget": budget, "max_age": max_age, "near_rail": near_rail}
    now |= {"checked_only": checked_only, "areas": areas, "bedrooms": bedrooms}
    extra = {"goal": goal, "area_facts": area_facts}

    def ids(**kw) -> dict[int, bool]:
        args = {**now, **kw}
        got = find(listings, intel, rent_rows, top=10**9, year=year, memo=memo, **extra, **args)
        return {id(p.listing): p.checked for p in got}

    base = ids()
    options: list[tuple[str, dict]] = []
    if max_age is not None:
        wider = next((a for a in AGE_STEPS if a > max_age), None)
        label = f"Έως {wider} ετών" if wider else "Οποιαδήποτε ηλικία κτιρίου"
        options.append((label, {"max_age": wider}))
    options.append(("Προϋπολογισμός +10 %", {"budget": _r(budget * 1.1, 10_000)}))
    if near_rail:
        options.append(("Χωρίς όρο σταθμού", {"near_rail": False}))
    if areas:
        options.append(("Σε όλες τις περιοχές", {"areas": None}))
    if bedrooms is not None:
        options.append(("Χωρίς όρο υπνοδωματίων", {"bedrooms": None}))
    if checked_only:
        options.append(("Μόνο ελεγμένες: όχι", {"checked_only": False}))
    out = []
    for label, changes in options:
        more = {k: v for k, v in ids(**changes).items() if k not in base}
        if more:
            out.append(Relax(label, changes, len(more), sum(more.values())))
    return out[:limit]
