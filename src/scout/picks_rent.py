"""«Να νοικιάσω»: the rentals that fit a monthly budget, best value first, with four checks.

Input: rental dicts from ``queries.load_rent_listings()`` (contract C1: the sale keys, with
``price`` = monthly rent, plus ``rent_per_m2``, ``furnished``, ``available_from``,
``days_on_market`` / ``dom_basis`` / ``relisted_on``, ``is_fresh``, ``page_checked``).

Ranking: the rent-value score (``RentPick.score``, below) first; the tie-break is value — the
rental's €/τ.μ. against the median €/τ.μ. of the OTHER active rentals in the same neighbourhood (at least ``MIN_COMPS``), else in the same area
(``area_insights.area_name``) — then freshness (fewer days on market first). A rent more than
``TOO_CHEAP`` under its comparables is a warning (often a room, a typo or a bait ad) and
sorts after the ones that compare normally; rentals without comparables come last.

Band: monthly rent ≤ budget × (1 + ``BUDGET_BAND``); no lower bound. ``relaxations`` loosens
one rule at a time and counts exactly what it adds (same ``find``, not an estimate).

Near matches (C7, ``find(..., near=True)``): after the strict matches, rentals that fail
exactly ONE answer. Steps (``picks.near_steps``): rent band 10 % → 20 % → 30 % over the
budget; building age one step up (10 → 20); station rule off; chosen areas → all areas;
bedrooms off; last, any building age. Each step keeps its best ``picks.NEAR_MIN`` by value;
all near matches are then sorted by ``score`` (smaller loosening first on a tie), after every
strict one — and only when the strict matches are fewer than ``picks.NEAR_MIN``. Each carries
``relaxed`` («ποσό +18 %», «κτίριο 1998», «χωρίς όρο σταθμού», «Μαρούσι», «3 υπν.»).
Then «ευρύτερα» (``tier=2``): every remaining rental within rent × 1,30 (two or more answers
failed, or one past a step's cap), by ``score``, no cap; ``relaxed`` names what it fails. «Επιπλωμένο» is not loosened
(C7 does not list it).

Rent-value score («Βαθμολογία», 0–100, ``RentPick.score``): value 0–70 from ``vs_area_pct``
(20 % under the comparables = 70, equal = 35, 20 % over = 0; no comparables = 35; more than
``TOO_CHEAP`` under = 0, a warning not a bonus) + freshness 0–30 (up to 14 days on the market
= 30, falling to 0 at ``STALE_DAYS``; unknown = 15; re-posted = 10). ``score_basis`` says it.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from . import picks
from .area_insights import area_name

BUDGET_BAND = 0.10
MIN_COMPS = 5
TOO_CHEAP = 0.35
AGE_STEPS = picks.AGE_STEPS
NEW_YEARS = picks.NEW_YEARS
TOP = 10


def gr_num(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def days(n: int) -> str:
    return f"{n} {'μέρα' if n == 1 else 'μέρες'}"


def ppm(d: dict) -> float | None:
    """Monthly rent per m²: the stored ``rent_per_m2``, else price ÷ m²."""
    if d.get("rent_per_m2"):
        return float(d["rent_per_m2"])
    if d.get("price") and d.get("area_m2"):
        return d["price"] / d["area_m2"]
    return None


def usable(d: dict) -> bool:
    return bool(d.get("is_fresh", True) and d.get("price") and d.get("area_m2")) and not d.get(
        "is_suspect"
    )


def station_text(d: dict) -> str:
    """The station line: ``picks.station_text`` when it exists, else the neighbourhood rule."""
    fn = getattr(picks, "station_text", None)
    if callable(fn):
        return fn(d) or ""
    s = picks.station(d)
    return f"{s} (από το όνομα της γειτονιάς)" if s else ""


def rail_ok(d: dict) -> bool:
    fn = getattr(picks, "near_rail", None)
    return bool(fn(d)) if callable(fn) else bool(picks.station(d))


def comps_index(rentals: list[dict]) -> tuple[dict, dict]:
    """(neighbourhood → [(id, €/τ.μ.)], area → [(id, €/τ.μ.)]) over the active rentals."""
    hood: dict[str, list[tuple[int, float]]] = {}
    area: dict[str, list[tuple[int, float]]] = {}
    for d in rentals:
        x = ppm(d) if usable(d) else None
        if x is None:
            continue
        h = d.get("neighborhood") or ""
        hood.setdefault(h, []).append((id(d), x))
        area.setdefault(area_name(h), []).append((id(d), x))
    return hood, area


def comps(d: dict, index: tuple[dict, dict]) -> tuple[float, int, str] | None:
    """(median €/τ.μ., n, where) of the other rentals — neighbourhood first, then area."""
    hood = d.get("neighborhood") or ""
    area = area_name(hood)
    for where, rows in ((hood, index[0].get(hood, [])), (area, index[1].get(area, []))):
        others = [x for i, x in rows if i != id(d)]
        if len(others) >= MIN_COMPS:
            return statistics.median(others), len(others), where
    return None


@dataclass
class RentPick:
    listing: dict
    rent_per_m2: float
    vs_area_pct: float | None  # (own − comps median) ÷ comps median; negative = cheaper
    dom: int | None
    checks: list[tuple[str, str]] = field(default_factory=list)  # (label, text): the four
    reasons: list[str] = field(default_factory=list)  # why it ranks where it does
    risks: list[str] = field(default_factory=list)
    comps_n: int = 0
    comps_ppm: float | None = None
    comps_where: str = ""
    station: str = ""
    over_budget: int = 0  # € above the stated budget (inside the band), 0 when within
    score: int = 0  # rent-value score 0–100 (module docstring)
    score_basis: str = ""  # «τιμή έναντι παρόμοιων 52/70 + φρεσκάδα 30/30»
    relaxed: str = ""  # what it is outside of, in the user's words; "" = strict
    tier: int = 0  # 0 strict · 1 near (one answer) · 2 «ευρύτερα» (two or more)

    @property
    def too_cheap(self) -> bool:
        return self.vs_area_pct is not None and self.vs_area_pct < -TOO_CHEAP

    def sort_key(self) -> tuple:
        no_comps = self.vs_area_pct is None
        return (self.too_cheap, no_comps, self.vs_area_pct or 0.0, self.dom or 10**6)

    @property
    def comps_line(self) -> str:
        """«Παρόμοια ενοίκια (12): 8 % κάτω» or why it cannot be compared."""
        if self.vs_area_pct is None:
            return f"Παρόμοια ενοίκια: λιγότερα από {MIN_COMPS} (δεν συγκρίνεται)"
        pct = round(abs(self.vs_area_pct) * 100)
        if pct < 2:
            return f"Παρόμοια ενοίκια ({self.comps_n}): όσο τα παρόμοια"
        side = "κάτω" if self.vs_area_pct < 0 else "πάνω"
        return f"Παρόμοια ενοίκια ({self.comps_n}): {pct} % {side}"


def _day(v) -> str | None:
    return f"{v:%d/%m/%Y}" if isinstance(v, (date, datetime)) else None


DOM_BASIS = {"listed": "από την ημερομηνία αγγελίας", "seen": "από τότε που τη βλέπουμε"}


def freshness(d: dict) -> str:
    dom = d.get("days_on_market")
    if dom is None:
        return "Μέρες στην αγορά: άγνωστο"
    basis = DOM_BASIS.get(d.get("dom_basis") or "")
    out = f"{days(dom)} στην αγορά" + (f" ({basis})" if basis else "")
    if d.get("relisted_on"):
        out += f" · ξαναδημοσιεύτηκε {_day(d['relisted_on'])}"
    return out


STALE_DAYS = 60


def fresh_verdict(d: dict) -> str:
    """The short freshness check: re-posted, new, long on the market, or the days."""
    dom = d.get("days_on_market")
    if d.get("relisted_on"):
        return f"ξαναδημοσιεύτηκε {_day(d['relisted_on'])} — ίδιο σπίτι, νέα αγγελία"
    if dom is None:
        return "άγνωστο"
    if dom <= 14:
        return f"νέα αγγελία ({days(dom)})"
    if dom >= STALE_DAYS:
        return f"{days(dom)} στην αγορά — ρώτα γιατί δεν έχει νοικιαστεί"
    return f"{days(dom)} στην αγορά"


def _checks(d: dict, p: RentPick) -> list[tuple[str, str]]:
    if p.vs_area_pct is None:
        price = f"λιγότερα από {MIN_COMPS} παρόμοια ενοίκια (δεν συγκρίνεται)"
    else:
        price = (
            f"{gr_num(p.rent_per_m2)} έναντι {gr_num(p.comps_ppm)} €/τ.μ., διάμεσο "
            f"{p.comps_n} αγγελιών ({p.comps_where})"
        )
    seller = d.get("is_private_seller")
    who = (
        "Ιδιώτης"
        if seller
        else ("Μεσιτικό γραφείο — ρώτα την αμοιβή του μεσίτη" if seller is False else "άγνωστο")
    )
    energy = d.get("energy_class")
    return [
        ("Τιμή έναντι παρόμοιων", price),
        ("Φρεσκάδα", fresh_verdict(d)),
        ("Ιδιώτης ή μεσιτικό", who),
        (
            "Ενεργειακή κλάση",
            f"{energy}" if energy else "δεν δηλώνεται — ζήτα το πιστοποιητικό (ΠΕΑ)",
        ),
    ]


VALUE_PTS, FRESH_PTS = 70, 30
VALUE_SPAN = 0.20  # this far under the comparables = full value points, this far over = none
NEW_DAYS = 14


def value_score(vs_area_pct: float | None, d: dict) -> tuple[int, str]:
    """(rent-value score 0–100, its basis in words) — module docstring."""
    if vs_area_pct is None:
        value = VALUE_PTS / 2
    elif vs_area_pct < -TOO_CHEAP:
        value = 0.0
    else:
        x = (VALUE_SPAN - vs_area_pct) / (2 * VALUE_SPAN)
        value = VALUE_PTS * min(max(x, 0.0), 1.0)
    dom = d.get("days_on_market")
    if d.get("relisted_on"):
        fresh = 10.0
    elif dom is None:
        fresh = FRESH_PTS / 2
    else:
        x = (STALE_DAYS - dom) / (STALE_DAYS - NEW_DAYS)
        fresh = FRESH_PTS * min(max(x, 0.0), 1.0)
    basis = (
        f"τιμή έναντι παρόμοιων {round(value)}/{VALUE_PTS}"
        + (" (χωρίς παρόμοια)" if vs_area_pct is None else "")
        + f" + φρεσκάδα {round(fresh)}/{FRESH_PTS}"
    )
    return round(value + fresh), basis


def _build(d: dict, index: tuple[dict, dict], budget: int) -> RentPick:
    own = ppm(d) or 0.0
    cmp = comps(d, index)
    vs = (own - cmp[0]) / cmp[0] if cmp else None
    p = RentPick(
        listing=d,
        rent_per_m2=own,
        vs_area_pct=vs,
        dom=d.get("days_on_market"),
        comps_n=cmp[1] if cmp else 0,
        comps_ppm=cmp[0] if cmp else None,
        comps_where=cmp[2] if cmp else "",
        station=station_text(d),
        over_budget=max(0, int(d["price"] - budget)),
    )
    p.checks = _checks(d, p)
    p.score, p.score_basis = value_score(vs, d)
    if vs is not None and vs < 0 and not p.too_cheap:
        p.reasons.append(f"{round(-vs * 100)} % κάτω από τα παρόμοια ενοίκια ({p.comps_n})")
    if p.dom is not None and p.dom <= 14:
        p.reasons.append(f"νέα αγγελία ({days(p.dom)})")
    if p.station:
        p.reasons.append(p.station)
    if p.too_cheap:
        p.risks.append(
            "Πολύ κάτω από τα παρόμοια — έλεγξε ότι είναι ολόκληρο σπίτι και ότι η αγγελία υπάρχει."
        )
    if p.over_budget:
        p.risks.append(f"{eur(p.over_budget)} πάνω από το ποσό σου.")
    if cmp and cmp[1] < 8:
        p.risks.append(f"Παρόμοια ενοίκια ({cmp[1]}): μικρό δείγμα για σύγκριση.")
    p.risks = p.risks[:3]
    return p


def pick(d: dict, index: tuple[dict, dict]) -> RentPick:
    """One rental on its own (favourites): the same card facts, no budget."""
    return _build(d, index, int(d["price"]))


def _age_ok(d: dict, max_age: int | None, year: int) -> bool:
    if max_age is None:
        return True
    built = d.get("renovated_year") or d.get("year_built")
    return bool(built and year - max_age <= built <= year)


PRICE_STEPS = (0.20, 0.30)  # the rent band over the budget, after BUDGET_BAND


def _misses(
    d: dict,
    budget_month: int,
    year: int,
    bedrooms: int | None,
    near_rail: bool,
    areas: list[str] | None,
    max_age: int | None,
) -> list[tuple[str, int, str]]:
    """The answers this rental fails, as (answer, step, label) — see ``picks._misses``."""
    out: list[tuple[str, int, str]] = []
    price = d["price"]
    if price > budget_month * (1 + BUDGET_BAND):
        step = next(
            (i + 1 for i, b in enumerate(PRICE_STEPS) if price <= budget_month * (1 + b)), 0
        )
        out.append(("price", step, f"ποσό +{math.ceil((price / budget_month - 1) * 100)} %"))
    if not _age_ok(d, max_age, year):
        wider = [a for a in picks.AGE_LOOSEN if a is None or (max_age is not None and a > max_age)]
        step = next((i + 1 for i, a in enumerate(wider) if _age_ok(d, a, year)), 0)
        built = d.get("renovated_year") or d.get("year_built")
        out.append(("age", step, f"κτίριο {built}" if built else "κτίριο χωρίς έτος"))
    if near_rail and not rail_ok(d):
        out.append(("rail", 1, "χωρίς όρο σταθμού"))
    if areas and (area := area_name(d.get("neighborhood"))) not in areas:
        out.append(("areas", 1, area))
    if not picks._bedrooms_ok(d, bedrooms):
        n = d.get("bedrooms")
        out.append(("bedrooms", 1, f"{n} υπν." if n is not None else "υπν. άγνωστα"))
    return out


def find(
    rentals: list[dict],
    budget_month: int,
    bedrooms: int | None = None,
    near_rail: bool = False,
    areas: list[str] | None = None,
    max_age: int | None = None,
    furnished: bool = False,
    top: int = TOP,
    *,
    year: int | None = None,
    near: bool = False,
    _index: tuple[dict, dict] | None = None,
) -> list[RentPick]:
    """Rentals with rent ≤ ``budget_month`` × 1,10 that pass the answers, best value first
    (module docstring). ``bedrooms`` 1/2 exact, 3 = 3+, None any; ``furnished=True`` keeps only
    rentals that say «Επιπλωμένο»; ``max_age=None`` any building age. ``near=True`` appends
    the near matches after the strict ones."""
    year = year or date.today().year
    index = _index or comps_index(rentals)
    strict: list[RentPick] = []
    loose: dict[tuple[str, int], list[RentPick]] = {}
    wide: list[RentPick] = []
    for d in rentals:
        if not usable(d):
            continue
        if furnished and d.get("furnished") is not True:
            continue
        miss = _misses(d, budget_month, year, bedrooms, near_rail, areas, max_age)
        if not miss:
            strict.append(_build(d, index, budget_month))
        elif not near or not all(step for _, step, _ in miss):
            continue  # past rent × 1,30, or not asked for
        elif len(miss) > 1:
            label = ", ".join(x[2] for x in miss)
            wide.append(replace(_build(d, index, budget_month), relaxed=label, tier=2))
        else:
            answer, step, label = miss[0]
            p = replace(_build(d, index, budget_month), relaxed=label, tier=1)
            loose.setdefault((answer, step), []).append(p)
    strict.sort(key=lambda p: (-p.score, p.sort_key()))  # the score, then value/freshness
    out = strict
    if near and len(out) < picks.NEAR_MIN:  # only to fill a thin list
        # Each step's best NEAR_MIN by value, then all near matches by score, the smaller
        # loosening first on a tie.
        ranked = []
        for i, step in enumerate(picks.near_steps(max_age, near_rail, areas, bedrooms)):
            group = sorted(loose.get(step, []), key=lambda p: (-p.score, p.sort_key()))
            ranked += [(-p.score, i, p) for p in group[: picks.NEAR_MIN]]
            wide += [replace(p, tier=2) for p in group[picks.NEAR_MIN :]]  # past the cap
        ranked.sort(key=lambda x: x[:2])
        out += [p for *_, p in ranked]
        out += sorted(wide, key=lambda p: (-p.score, p.sort_key()))  # «ευρύτερα», no cap
    return out[:top]


@dataclass
class Relax:
    """One answer loosened and exactly how many rentals it adds (counted with ``find``)."""

    label: str
    changes: dict  # find() keyword → new value; "budget_month" is the budget itself
    added: int

    @property
    def text(self) -> str:
        return f"{self.label} (+{self.added})"


def relaxations(
    rentals: list[dict],
    budget_month: int,
    bedrooms: int | None = None,
    near_rail: bool = False,
    areas: list[str] | None = None,
    max_age: int | None = None,
    furnished: bool = False,
    *,
    year: int | None = None,
    limit: int = 4,
) -> list[Relax]:
    """Up to ``limit`` single-answer relaxations that add rentals, each with its exact count."""
    now = dict(budget_month=budget_month, bedrooms=bedrooms, near_rail=near_rail)
    now |= dict(areas=areas, max_age=max_age, furnished=furnished)
    index = comps_index(rentals)

    def ids(**kw) -> set[int]:
        got = find(rentals, **{**now, **kw}, top=10**9, year=year, _index=index)
        return {id(p.listing) for p in got}

    base = ids()
    options: list[tuple[str, dict]] = [
        ("Ποσό +10 %", {"budget_month": int(round(budget_month * 1.1 / 50) * 50)})
    ]
    if max_age is not None:
        wider = next((a for a in AGE_STEPS if a > max_age), None)
        options.append(
            (f"Έως {wider} ετών" if wider else "Οποιαδήποτε ηλικία κτιρίου", {"max_age": wider})
        )
    if near_rail:
        options.append(("Χωρίς όρο σταθμού", {"near_rail": False}))
    if areas:
        options.append(("Σε όλες τις περιοχές", {"areas": None}))
    if bedrooms is not None:
        options.append(("Χωρίς όρο υπνοδωματίων", {"bedrooms": None}))
    if furnished:
        options.append(("Και χωρίς έπιπλα", {"furnished": False}))
    out = []
    for label, changes in options:
        if more := ids(**changes) - base:
            out.append(Relax(label, changes, len(more)))
    return out[:limit]
