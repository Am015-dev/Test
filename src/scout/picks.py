"""«Βρες μου σπίτι»: the best few listings for a budget, explained like an advisor would.

The buyer states a budget, a maximum building age and whether the flat must be next to a rail
station; this ranks the matching listings by what a buy-to-let investor cares about — a page
we have read first, real photos, then rent return, price against like-for-like flats, room to
negotiate — and writes one short line per number with its basis. When too little qualifies,
``relaxations`` says which single rule to loosen and exactly how many flats that adds (same
``find`` logic, not an estimate). Pure functions over the listing dicts the UI already loads.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
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


def _build(d: dict, intel: Intel, rents: dict, year: int) -> Pick | None:
    """Everything about one listing that does not depend on the buyer's filters."""
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
    rank = (
        gross * 1000  # rent return leads
        + max(min(gap, 0.25), -0.15) * 40
        + (3 if built and built <= year - 1 else 0)  # finished, not "delivery this year"
        + (2 if dom >= 90 else 0)
        - (20 if too_cheap else 0)
    )
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
    lines.append(
        (f"{dom} μέρες στην αγορά → ξεκίνα" if dom else "Προσφορά: ξεκίνα")
        + f" από ~{_eur(offer)}"
        + (" (ιδιώτης πωλητής)" if d.get("is_private_seller") else "")
    )
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
    )


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
    year: int | None = None,
    top: int = TOP,
    memo: dict[int, Pick | None] | None = None,
) -> list[Pick]:
    """The ``top`` listings for ``budget`` (± BUDGET_BAND): read pages first, then real
    photos, then best rent return. ``max_age=None`` = any building age. ``memo`` caches the
    per-listing work between calls that only differ in the filters (see ``relaxations``)."""
    year = year or date.today().year
    rents = rent_index(rent_rows)
    memo = {} if memo is None else memo
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
        if id(d) not in memo:
            memo[id(d)] = _build(d, intel, rents, year)
        if memo[id(d)] is not None:
            out.append(memo[id(d)])
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
    year: int | None = None,
    limit: int = 4,
) -> list[Relax]:
    """Up to ``limit`` single-rule relaxations that add flats, each with its exact count."""
    memo: dict[int, Pick | None] = {}
    now = {"budget": budget, "max_age": max_age, "near_rail": near_rail}
    now["checked_only"] = checked_only

    def ids(**kw) -> dict[int, bool]:
        args = {**now, **kw}
        got = find(listings, intel, rent_rows, top=10**9, year=year, memo=memo, **args)
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
    if checked_only:
        options.append(("Μόνο ελεγμένες: όχι", {"checked_only": False}))
    out = []
    for label, changes in options:
        more = {k: v for k, v in ids(**changes).items() if k not in base}
        if more:
            out.append(Relax(label, changes, len(more), sum(more.values())))
    return out[:limit]
