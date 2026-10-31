"""«Βρες μου σπίτι»: the best few listings for a budget, explained like an advisor would.

The buyer states a budget and whether the flat must be new and next to a rail station; this
ranks the matching listings by what a buy-to-let investor cares about — rent return, price
against like-for-like flats, room to negotiate — and writes the case for each in plain Greek
with the numbers behind it. Pure functions over the listing dicts the UI already loads.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

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
    why: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


def _r(x: float, step: int) -> int:
    return int(round(x / step) * step)


def _eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def gr_pct(x: float) -> str:
    return f"{x:.1%}".replace(".", ",")


def gr_num(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def find(
    listings: list[dict],
    intel: Intel,
    rent_rows: list[dict],
    budget: int,
    *,
    new_only: bool = True,
    near_rail: bool = True,
    areas: list[str] | None = None,
    year: int | None = None,
    top: int = TOP,
) -> list[Pick]:
    """The ``top`` listings for ``budget`` (± BUDGET_BAND), best rent return first."""
    year = year or date.today().year
    rents = rent_index(rent_rows)
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
        if new_only and not (built and year - NEW_YEARS <= built <= year):
            continue
        st_name = station(d)
        if near_rail and not st_name:
            continue
        if areas and area_name(d.get("neighborhood")) not in areas:
            continue
        rent_basis = area_rent(d, rents)
        if rent_basis is None:
            continue
        per_m2, samples, where = rent_basis
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
        rank = (
            gross * 1000  # rent return leads
            + max(min(gap, 0.25), -0.15) * 40
            + (3 if built and built <= year - 1 else 0)  # finished, not "delivery this year"
            + (2 if dom >= 90 else 0)
            - (20 if too_cheap else 0)
        )
        why = [
            f"Απόδοση: ενοίκιο ~{_eur(_r(rent, 10))}/μήνα ({gr_num(per_m2)} €/τ.μ. ζητούμενο στην "
            f"περιοχή «{where}»"
            + (", +10% επειδή είναι νεόδμητο" if new_premium > 1 else "")
            + f") → μικτή {gr_pct(gross)}, καθαρή ~{gr_pct(net)} μετά από φόρο, κενό, "
            "συντήρηση, ΕΝΦΙΑ και έξοδα αγοράς.",
        ]
        if cmp:
            pos = (
                "φθηνότερο από τα 3 στα 4"
                if d["price_per_m2"] < cmp["p25"]
                else (
                    "στο συνηθισμένο εύρος"
                    if d["price_per_m2"] <= cmp["p75"]
                    else "ακριβότερο από τα 3 στα 4"
                )
            )
            why.append(
                f"Τιμή: {_eur(d['price_per_m2'])}/τ.μ., {abs(cmp['pct']):.0%} "
                f"{'κάτω' if cmp['pct'] < 0 else 'πάνω'} από {cmp['n']} παρόμοια "
                f"({cmp['label']}, διάμεσος {_eur(cmp['ppm'])}/τ.μ.) — {pos}."
            )
        if st_name:
            why.append(
                f"Σταθμός: η γειτονιά «{d.get('neighborhood')}» είναι η περιοχή του σταθμού {st_name}."
            )
        why.append(
            f"Κτίριο {built}, "
            + (f"{d['floor']:g}ος όροφος, " if d.get("floor") is not None else "")
            + f"{d['area_m2']:g} τ.μ."
            + (f", {d['bedrooms']} υπνοδωμάτια." if d.get("bedrooms") else ".")
        )
        why.append(
            f"Προσφορά: ξεκίνα από ~{_eur(offer)}"
            + (f" — {dom} μέρες στην αγορά χωρίς πώληση" if dom >= 90 else "")
            + (", ιδιώτης πωλητής" if d.get("is_private_seller") else "")
            + "."
        )
        risks = []
        if built == year:
            risks.append("Έτος κατασκευής φέτος: βεβαιώσου ότι έχει παραδοθεί και έχει άδεια.")
        if too_cheap:
            risks.append("Ασυνήθιστα φθηνό για τα παρόμοια — έλεγξε τ.μ., κατάσταση, νομικά.")
        if not samples:
            risks.append(
                "Το ενοίκιο είναι διάμεσος ζητούμενων ενοικίων της περιοχής, όχι συμβόλαιο."
            )
        if d.get("floor") == 1:
            risks.append("1ος όροφος: λίγο χαμηλότερο ενοίκιο από τους ψηλότερους.")
        if cmp and cmp["n"] < 8:
            risks.append(f"Μικρό δείγμα σύγκρισης ({cmp['n']} παρόμοια).")
        if not d.get("energy_class"):
            risks.append("Η ενεργειακή κλάση δεν δηλώνεται — ζήτα το πιστοποιητικό.")
        out.append(
            Pick(
                listing=d,
                rank_score=rank,
                rent=_r(rent, 10),
                rent_low=_r(rent * 0.9, 10),
                rent_high=_r(rent * 1.1, 10),
                gross=gross,
                net=net,
                offer=offer,
                station=st_name,
                why=why,
                risks=risks[:3],
            )
        )
    out.sort(key=lambda p: -p.rank_score)
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
