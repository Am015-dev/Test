"""«Βρες μου σπίτι»: the best few listings for a budget, explained like an advisor would.

The buyer states a budget, a maximum building age and whether the flat must be next to a rail
station; this ranks the matching listings by what a buy-to-let investor cares about — a page
we have read first, real photos, then rent return, price against like-for-like flats, room to
negotiate — and writes one short line per number with its basis. When too little qualifies,
``relaxations`` says which single rule to loosen and exactly how many flats that adds (same
``find`` logic, not an estimate). Pure functions over the listing dicts the UI already loads.

Ranking by goal (the «Οδηγός» question «Τι σε νοιάζει πιο πολύ;»). Every listing gets four
part scores, in points; ``rank_score`` = Σ ``GOAL_WEIGHTS[goal][part]`` × part. The sort is
always: page read first, then real photos (>2, not render/plan/site/stock), then the buyer
score (``buyer_score``, the card's «Βαθμολογία»), then ``rank_score`` as the tie-break — the
goal never lifts an unread page above a read one, nor a lower score above a higher one.

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
           for the listing (``metro_line4.line4_station`` when present) · 6 area
           new-build premium ≤15 %
           (``area_insights``, needs ``area_facts``)
=========  ===============================================================================

=========  =====  =====  ======  ======
goal       yield  value  safety  growth
=========  =====  =====  ======  ======
yield      1.0    1.0    0.25    0.25
safety     0.4    0.6    1.0     0.25
growth     0.4    0.6    0.25    1.0
=========  =====  =====  ======  ======

Never a thin list (C7). ``find(..., near=True)`` returns the strict matches first and then
**near matches**: listings that fail exactly ONE of the buyer's answers. The loosening steps,
smallest first: price band 12 % → 20 % → 30 % over the budget; building age one step up
(10 → 20); station rule off; chosen areas → all areas; bedrooms off; and last, any building
age. Every step keeps its best ``NEAR_MIN`` (3 × ``PAGE``); all near matches are then ranked
together by the usual sort (page read, photos, ``rank_score``), the smaller loosening first
on a tie, and sort after every strict match. Near matches are added only when the strict
matches are fewer than ``NEAR_MIN``. Each carries ``relaxed``, the loosened answer in
the user's words («ποσό +18 %», «κτίριο 1998», «χωρίς όρο σταθμού», «Μαρούσι», «3 υπν.»).
Then a third tier, «ευρύτερα» (``tier=2``): every remaining flat within budget × 1,30 — the
ones that fail two or more answers and the one-answer ones past a step's cap — by the usual
sort, with no cap; ``relaxed`` names everything it fails («ποσό +22 %, κτίριο 1985, χωρίς όρο
σταθμού»). Every flat in the band appears exactly once, in one tier.

The buyer score (``buyer_score``) on every pick is the 0–100 score of ``nl_search.advise``,
the same number the map colour and the search advice use.

With ``loan=True`` each pick carries the monthly instalment of a 70 % loan at 4 % over 25
years (annuity) and ``cashflow`` = rent estimate − instalment.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from . import stations
from .area_insights import area_name
from .finance import acquisition_costs
from .market_intel import Intel
from .nl_search import advise

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
NEAR_MIN = 3 * PAGE  # near matches are added until at least this many candidates exist
PRICE_STEPS = (0.20, 0.30)  # the price band over the budget, after BUDGET_BAND
AGE_LOOSEN = (10, 20, None)  # building-age limits a near match may step up to

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


def line4_stations(area: str) -> list[str]:
    """Planned Metro Line 4 stations in ``area`` (``metro_line4.line4_stations``, written by
    the insights workstream); empty when that module is not there yet."""
    try:
        from . import metro_line4
    except ImportError:
        return []
    return list(metro_line4.line4_stations(area) or [])


def line4_station(d: dict) -> str | None:
    """The planned Line 4 station for one listing (``metro_line4.line4_station``), or None."""
    try:
        from . import metro_line4
    except ImportError:
        return None
    return metro_line4.line4_station(d)


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


NAME_BASED = "(από το όνομα της γειτονιάς)"
NEAR_RAIL_M = 800  # walking distance that counts as «κοντά σε μετρό»


def _exact_station(d: dict) -> tuple[str, int] | None:
    """(Greek station label, metres) when the listing's own point was measured, else None.
    Approximate points (area centroids) carry no usable distance."""
    if d.get("location_precision") != "exact" or d.get("metro_distance_m") is None:
        return None
    name = stations.label(d.get("nearest_metro"))
    return (name, int(d["metro_distance_m"])) if name else None


def station_text(d: dict) -> str:
    """The station line a user reads. Exact point: «Μετρό Άγιος Δημήτριος · 450 μ.». Otherwise
    the station the neighbourhood name carries, with no distance: «ΗΣΑΠ Περισσός (από το όνομα
    της γειτονιάς)». Empty when neither is known."""
    if hit := _exact_station(d):
        return f"{hit[0]} · {hit[1]:,} μ.".replace(",", ".")
    if name := station(d):
        return f"{name.split(' (Γραμμή')[0]} {NAME_BASED}"
    return ""


def near_rail(d: dict) -> bool:
    """Within 800 m of a station when the point is exact; otherwise when the neighbourhood name
    carries a station."""
    if hit := _exact_station(d):
        return hit[1] <= NEAR_RAIL_M
    return station(d) is not None


_near_rail = near_rail  # ``find`` has a parameter of the same name


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
    bad_photos: bool = False  # photo check: render / plan / site / stock, not the flat
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
    buyer_score: int = 0  # 0–100, ``nl_search.advise`` (the score on every card)
    relaxed: str = ""  # what it is outside of, in the user's words; "" = strict
    tier: int = 0  # 0 strict · 1 near (one answer) · 2 «ευρύτερα» (two or more answers)

    @property
    def loan_line(self) -> str:
        """'Δόση ~1.110 €/μήνα → λείπουν 120 €' (or 'μένουν'), the «με δάνειο» answer."""
        left = (
            f"Το ενοίκιο την καλύπτει και περισσεύουν {_eur(self.cashflow)} τον μήνα."
            if self.cashflow >= 0
            else f"Το ενοίκιο δεν φτάνει: λείπουν {_eur(-self.cashflow)} τον μήνα."
        )
        return (
            f"Δόση ~{_eur(self.instalment)}/μήνα (δάνειο {round(LTV * 100)} %, επιτόκιο "
            f"{gr_num(RATE * 100).replace(',0', '')} %, {YEARS} χρόνια). {left}"
        )

    def sort_key(self) -> tuple:
        # The trust ladder first: a page we have read beats one we have not; real photos beat
        # "≤2 photos" (often a render or a logo) and render/plan/site/stock. Then the buyer
        # score (one truth with the card's «Βαθμολογία»); the goal's points break ties.
        return (
            self.checked,
            not self.bad_photos,
            not self.few_photos,
            self.buyer_score,
            self.rank_score,
        )


def _r(x: float, step: int) -> int:
    return int(round(x / step) * step)


def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def gr_pct(x: float) -> str:
    """0.047 → '4,7 %'."""
    return f"{x * 100:.1f} %".replace(".", ",")


def gr_num(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


CHECKED = "Ελέγχθηκε η περιγραφή{when}: δεν λέει ότι χτίζεται ακόμα"
UNCHECKED = "Δεν έχει ελεγχθεί ακόμα"
FEW_PHOTOS = "Έως 2 φωτογραφίες, συχνά μόνο σχέδιο ή λογότυπο"
EXCERPT_CHARS = 300
PHOTO_KINDS = {
    "photo": "αληθινές",
    "render": "σχέδια, όχι αληθινές",
    "plan": "σχέδια, όχι αληθινές",
    "site": "εργοτάξιο",
    "stock": "ίδιες με άλλες αγγελίες του μεσίτη",
}
BAD_PHOTO_KINDS = frozenset({"render", "plan", "site", "stock"})


def photo_line(d: dict) -> str:
    """'Φωτογραφίες: πραγματικές' etc. from the photo check; «δεν ελέγχθηκαν» when none."""
    return f"Φωτογραφίες: {PHOTO_KINDS.get(d.get('photo_kind') or '', 'δεν τις έχουμε δει ακόμα')}"


def status_line(d: dict) -> str:
    if not d.get("page_checked"):
        text = UNCHECKED
    else:
        when = d.get("page_checked_at")
        text = CHECKED.format(
            when=f" ({when:%d/%m/%Y})" if isinstance(when, (date, datetime)) else ""
        )
    return f"{text} · {photo_line(d)}"


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
    bscore = advise(d, cmp["pct"] if cmp else None)["score"]
    dom = d.get("days_on_market") or 0
    offer_cut = 0.03 + (0.03 if dom >= 90 else 0) + (0.02 if d.get("is_private_seller") else 0)
    offer = _r(d["price"] * (1 - offer_cut), 1000)
    too_cheap = gap > 0.35
    checked = bool(d.get("page_checked"))
    few = bool(d.get("few_photos"))
    st_name = station_text(d) if _near_rail(d) else None
    value = (
        max(min(gap, 0.25), -0.15) * 40
        + (3 if built and built <= year - 1 else 0)  # finished, not "delivery this year"
        + (2 if dom >= 90 else 0)
        - (20 if too_cheap else 0)
    )
    area = area_name(d.get("neighborhood"))
    n_area, dom_mean, dom_sd = (stats or {}).get(area, (0, None, None))
    safe = [
        ("ελέγξαμε την αγγελία", checked),
        ("πάνω από 2 φωτογραφίες", (d.get("photo_count") or 0) > 2),
        ("γράφει ενεργειακή κλάση", bool(d.get("energy_class"))),
        (f"{cmp['n'] if cmp else 0} παρόμοια", bool(cmp and cmp["n"] >= MANY_COMPS)),
        (f"{n_area} αγγελίες στην περιοχή", n_area >= ESTABLISHED),
        ("στην περιοχή πουλάνε σε σταθερό χρόνο", bool(dom_mean and dom_sd <= dom_mean)),
    ]
    fact = (area_facts or {}).get(area)
    prem = getattr(fact, "new_premium", None)
    l4 = line4_station(d)
    grow = [
        (st_name or "", bool(st_name), STATION_PTS),
        (f"Γραμμή 4: {l4}" if l4 else "", bool(l4), LINE4_PTS),
        (
            f"εδώ το νεόδμητο ζητά μόνο {round(prem * 100)} % παραπάνω" if prem is not None else "",
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
        f"Ενοίκιο (εκτίμηση) ~{_eur(_r(rent, 10))}/μήνα: τα διπλανά ζητούν {gr_num(per_m2)} "
        f"€/τ.μ. × {d['area_m2']:g} τ.μ."
        + (", και 10 % παραπάνω γιατί είναι νεόδμητο" if new_premium > 1 else ""),
        f"Μικτή απόδοση {gr_pct(gross)}. Καθαρή απόδοση ~{gr_pct(net)}, αφού βγάλεις έναν "
        "μήνα χωρίς ενοικιαστή, φόρο, συντήρηση και ΕΝΦΙΑ",
    ]
    ppm = d.get("price_per_m2") or d["price"] / d["area_m2"]
    if cmp:
        pct = round(abs(cmp["pct"]) * 100)
        rel = (
            f"όσο ζητούν και τα {cmp['n']} παρόμοια σπίτια της γειτονιάς"
            if pct < 2
            else f"{pct} % {'κάτω' if cmp['pct'] < 0 else 'πάνω'} από όσο ζητούν τα {cmp['n']} "
            "παρόμοια σπίτια της γειτονιάς"
        )
        lines.append(f"Τιμή {_eur(ppm)}/τ.μ., {rel}")
    else:
        lines.append(
            f"Τιμή {_eur(ppm)}/τ.μ. Βρήκαμε λιγότερα από 5 παρόμοια, άρα δεν τη συγκρίνουμε"
        )
    if st_name:
        lines.append(f"Σταθμός {st_name}")
    lines.append(
        " · ".join(
            x
            for x in (
                f"Κτίριο {d.get('year_built') or '—'}"
                + (f", ανακαίνιση {d['renovated_year']}" if d.get("renovated_year") else ""),
                (
                    (f"{d['floor']:g}ος όροφος" if d["floor"] else "Ισόγειο")
                    if d.get("floor") is not None
                    else ""
                ),
                f"{d['area_m2']:g} τ.μ.",
                (
                    (f"{d['bedrooms']} υπνοδωμάτι{'ο' if d['bedrooms'] == 1 else 'α'}")
                    if d.get("bedrooms")
                    else ""
                ),
            )
            if x
        )
    )
    offer_line = (
        (f"{dom} {'μέρα' if dom == 1 else 'μέρες'} στην αγορά. " if dom else "")
        + f"Προσφορά: ξεκίνα από ~{_eur(offer)}"
        + (" (πουλά ιδιώτης)" if d.get("is_private_seller") else "")
    )
    lines.append(offer_line)
    risks = []
    if few:
        risks.append(FEW_PHOTOS)
    if built == year:
        risks.append(
            f"Γράφει έτος κατασκευής {year}, δηλαδή φέτος. Βεβαιώσου ότι έχει παραδοθεί και έχει άδεια."
        )
    if too_cheap:
        risks.append(
            "Πολύ φθηνότερο από τα άλλα σπίτια της γειτονιάς. Έλεγξε τα τ.μ., την κατάσταση "
            "και τα νομικά."
        )
    if where != d.get("neighborhood"):
        risks.append(
            f"Το ενοίκιο βγαίνει από όλη την περιοχή «{where}», γιατί η γειτονιά έχει λίγες "
            "αγγελίες ενοικίασης."
        )
    if cmp and cmp["n"] < 8:
        risks.append(f"Παρόμοια ({cmp['n']}): λίγα για σίγουρη σύγκριση.")
    if not d.get("energy_class"):
        risks.append("Δεν γράφει ενεργειακή κλάση. Ζήτα το πιστοποιητικό.")
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
        bad_photos=(d.get("photo_kind") or "") in BAD_PHOTO_KINDS,
        status=status_line(d),
        lines=lines,
        risks=risks[:3],
        excerpt=excerpt(d.get("description")),
        parts=parts,
        reasons=reasons,
        instalment=_r(inst, 10),
        cashflow=_r(rent - inst, 10),
        offer_line=offer_line,
        buyer_score=bscore,
    )


def buyer_score(d: dict, intel: Intel) -> int:
    """The buyer score 0–100 for one listing: ``nl_search.advise`` with the listing's
    comparables from ``intel`` — one definition for cards, map and search advice."""
    cmp = intel.comps(d)
    return advise(d, cmp["pct"] if cmp else None)["score"]


def score(parts: dict[str, float], goal: str) -> float:
    w = GOAL_WEIGHTS.get(goal, GOAL_WEIGHTS["yield"])
    return sum(w[k] * parts.get(k, 0.0) for k in w)


def _bedrooms_ok(d: dict, bedrooms: int | None) -> bool:
    """``bedrooms`` 1 or 2 = exactly that; 3 = three or more; None = any."""
    if bedrooms is None:
        return True
    n = d.get("bedrooms")
    return n is not None and (n >= 3 if bedrooms >= 3 else n == bedrooms)


def _age_ok(d: dict, max_age: int | None, year: int) -> bool:
    built = d.get("renovated_year") or d.get("year_built")
    return max_age is None or bool(built and year - max_age <= built <= year)


def _misses(
    d: dict,
    budget: int,
    year: int,
    max_age: int | None,
    near_rail: bool,
    areas: list[str] | None,
    bedrooms: int | None,
) -> list[tuple[str, int, str]]:
    """The buyer's answers this listing fails, each as (answer, step, label): ``step`` is the
    loosening it needs (1 = the first step of that answer), ``label`` the user's words.
    A step of 0 means no allowed loosening admits it."""
    out: list[tuple[str, int, str]] = []
    price = d["price"]
    if price > budget * (1 + BUDGET_BAND):
        step = next((i + 1 for i, b in enumerate(PRICE_STEPS) if price <= budget * (1 + b)), 0)
        out.append(("price", step, f"ποσό +{math.ceil((price / budget - 1) * 100)} %"))
    if not _age_ok(d, max_age, year):
        wider = [a for a in AGE_LOOSEN if a is None or (max_age is not None and a > max_age)]
        step = next((i + 1 for i, a in enumerate(wider) if _age_ok(d, a, year)), 0)
        built = d.get("renovated_year") or d.get("year_built")
        out.append(("age", step, f"κτίριο {built}" if built else "κτίριο χωρίς έτος"))
    if near_rail and not _near_rail(d):
        out.append(("rail", 1, "χωρίς όρο σταθμού"))
    if areas and (area := area_name(d.get("neighborhood"))) not in areas:
        out.append(("areas", 1, area))
    if not _bedrooms_ok(d, bedrooms):
        n = d.get("bedrooms")
        out.append(("bedrooms", 1, f"{n} υπν." if n is not None else "υπν. άγνωστα"))
    return out


def near_steps(max_age: int | None, near_rail: bool, areas, bedrooms) -> list[tuple[str, int]]:
    """The loosening steps, smallest first, only for answers the buyer gave: price, age by
    named limits (10 → 20), station, areas, bedrooms, and LAST age «any»."""
    steps = [("price", i + 1) for i in range(len(PRICE_STEPS))]
    wider = [a for a in AGE_LOOSEN if a is None or a > max_age] if max_age is not None else []
    steps += [("age", i + 1) for i, a in enumerate(wider) if a is not None]
    if near_rail:
        steps.append(("rail", 1))
    if areas:
        steps.append(("areas", 1))
    if bedrooms is not None:
        steps.append(("bedrooms", 1))
    if wider:
        steps.append(("age", len(wider)))  # any building age
    return steps


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
    near: bool = False,
) -> list[Pick]:
    """The ``top`` listings for ``budget`` (± BUDGET_BAND): read pages first, then real
    photos, then ``rank_score`` for ``goal`` (module docstring). ``max_age=None`` = any
    building age; ``areas`` = area names (``area_insights.area_name``); ``bedrooms`` see
    ``_bedrooms_ok``; ``area_facts`` = area → ``AreaInsight`` for the growth part. ``memo``
    caches the per-listing work between calls that only differ in the filters.
    ``near=True`` appends the near matches after the strict ones (module docstring)."""
    year = year or date.today().year
    rents = rent_index(rent_rows)
    memo = {} if memo is None else memo
    if "_stats" not in memo:
        memo["_stats"] = area_stats(listings)
    stats = memo["_stats"]
    lo = budget * (1 - BUDGET_BAND)
    strict: list[Pick] = []
    loose: dict[tuple[str, int], list[Pick]] = {}
    wide: list[Pick] = []
    for d in listings:
        if not d.get("is_fresh", True) or d.get("excluded") or d.get("is_suspect"):
            continue
        if d.get("is_unfinished") or not d.get("price") or not d.get("area_m2"):
            continue
        if d["price"] < lo or (d.get("floor") is not None and d["floor"] < 1):
            continue
        if checked_only and not d.get("page_checked"):
            continue
        miss = _misses(d, budget, year, max_age, near_rail, areas, bedrooms)
        if miss and not (near and all(step for _, step, _ in miss)):
            continue  # past the widest price step (budget × 1,30), or not asked for
        if id(d) not in memo:
            memo[id(d)] = _build(d, intel, rents, year, stats, area_facts)
        if (p := memo[id(d)]) is None:
            continue
        p = replace(p, rank_score=score(p.parts, goal), loan=loan, goal=goal)
        if len(miss) > 1:
            label = ", ".join(x[2] for x in miss)
            wide.append(replace(p, relaxed=label, tier=2))
        elif miss:
            answer, step, label = miss[0]
            loose.setdefault((answer, step), []).append(replace(p, relaxed=label, tier=1))
        else:
            strict.append(p)
    # One flat per building/listing group: skip near-identical units of the same block.
    seen: set[tuple] = set()

    def unique(group: list[Pick], cap: int | None = None) -> list[Pick]:
        group.sort(key=Pick.sort_key, reverse=True)
        kept: list[Pick] = []
        for p in group:
            if cap is not None and len(kept) >= cap:
                wide.append(replace(p, tier=2))  # past the step's cap: «ευρύτερα»
                continue
            d = p.listing
            key = (d.get("neighborhood"), d.get("year_built"), round(d["price"], -4))
            if key not in seen:
                seen.add(key)
                kept.append(p)
        return kept

    out = unique(strict)
    if near and len(out) < NEAR_MIN:  # near matches fill a thin list, never trail a long one
        # Every step contributes its best NEAR_MIN; then one ranking over all near matches,
        # the smaller loosening first on a tie.
        ranked = []
        for i, step in enumerate(near_steps(max_age, near_rail, areas, bedrooms)):
            ranked += [(p.sort_key(), -i, p) for p in unique(loose.get(step, []), NEAR_MIN)]
        ranked.sort(key=lambda x: x[:2], reverse=True)
        out += [p for *_, p in ranked]
        out += unique(wide)  # «ευρύτερα»: every remaining flat in the band, no cap
    return out[:top]


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
            f", {self.added_checked} με ελεγμένη περιγραφή)"
            if "checked_only" not in self.changes
            else ")"
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
        options.append(("Χωρίς όρο ελεγμένης περιγραφής", {"checked_only": False}))
    out = []
    for label, changes in options:
        more = {k: v for k, v in ids(**changes).items() if k not in base}
        if more:
            out.append(Relax(label, changes, len(more), sum(more.values())))
    return out[:limit]
