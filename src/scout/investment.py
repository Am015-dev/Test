"""Investment decision calculators — the numbers an investor underwrites on.

Pure functions on top of ``finance.py``: no DB, no network, no Streamlit. Each fails soft
(returns ``None`` on missing/degenerate inputs) so a listing with incomplete data shows a
blank field rather than a bogus figure. These turn the raw signals into the concrete
questions a buyer actually asks — "what's my downside?", "what if I offer less?",
"how long to get my money back?", "is this an A or a C deal?".
"""

from __future__ import annotations

from dataclasses import dataclass

from .finance import CostAssumptions, acquisition_costs, net_yield

_DEFAULT = CostAssumptions()


def net_yield_sensitivity(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    is_private_seller: bool,
) -> dict | None:
    """Net yield under pessimistic / base / optimistic assumptions — the honest RANGE, not a
    single point. Pessimistic = higher vacancy + maintenance; optimistic = the reverse."""
    if not annual_rent or annual_rent <= 0 or not price or price <= 0:
        return None
    scenarios = {
        "pessimistic": CostAssumptions(vacancy_rate=0.12, maintenance_pct_of_rent=0.12),
        "base": _DEFAULT,
        "optimistic": CostAssumptions(vacancy_rate=0.02, maintenance_pct_of_rent=0.05),
    }
    out = {}
    for name, a in scenarios.items():
        y = net_yield(price, annual_rent, area_m2, is_private_seller, a)
        if y is None:
            return None
        out[name] = round(y, 4)
    return out


def yield_on_offer(
    offer: int | None,
    annual_rent: float | None,
    area_m2: float | None,
    is_private_seller: bool,
) -> float | None:
    """Net yield computed at the RECOMMENDED OFFER, not the asking price — the return the
    investor actually gets if the deal closes at the suggested number."""
    if not offer or offer <= 0:
        return None
    return net_yield(offer, annual_rent, area_m2, is_private_seller)


def break_even_rent(
    price: int,
    area_m2: float | None,
    is_private_seller: bool,
    a: CostAssumptions = _DEFAULT,
) -> int | None:
    """The monthly rent at which net operating income just covers holding costs (NOI = 0) —
    the downside floor. Below this the property bleeds cash before financing."""
    if not price or price <= 0 or not area_m2 or area_m2 <= 0:
        return None
    # NOI = rent*(1-vac)*(1 - mgmt - maint) - enfia*area - insurance*price = 0
    fixed = a.enfia_eur_per_m2_year * area_m2 + a.insurance_pct_of_value_year * price
    rent_factor = (1 - a.vacancy_rate) * (1 - a.mgmt_pct_of_rent - a.maintenance_pct_of_rent)
    if rent_factor <= 0:
        return None
    annual_break_even = fixed / rent_factor
    return int(round(annual_break_even / 12))


def payback_years(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    is_private_seller: bool,
    a: CostAssumptions = _DEFAULT,
) -> float | None:
    """Unlevered years to recoup the all-in cash outlay (price + acquisition costs) from net
    income — the simple "how long to get my money back" figure."""
    if not annual_rent or annual_rent <= 0:
        return None
    y = net_yield(price, annual_rent, area_m2, is_private_seller, a)
    acq = acquisition_costs(price, is_private_seller, a)
    if not y or y <= 0 or acq is None:
        return None
    noi = y * (price + acq)
    if noi <= 0:
        return None
    return round((price + acq) / noi, 1)


def rent_vs_buy_monthly(
    price: int,
    own_monthly_rent_saved: float | None,
    area_m2: float | None,
    is_private_seller: bool,
    a: CostAssumptions = _DEFAULT,
) -> dict | None:
    """For an owner-occupier: monthly cost of OWNING (holding costs, unlevered) vs the rent
    they'd otherwise pay. Positive ``advantage`` means owning is cheaper per month."""
    if not price or price <= 0 or not own_monthly_rent_saved or own_monthly_rent_saved <= 0:
        return None
    from .finance import annual_operating_costs

    op = annual_operating_costs(own_monthly_rent_saved * 12, price, area_m2, a)
    if op is None:
        return None
    own_monthly = op / 12
    return {
        "own_monthly_cost": round(own_monthly),
        "rent_monthly": round(own_monthly_rent_saved),
        "advantage": round(own_monthly_rent_saved - own_monthly),
    }


@dataclass
class DealGrade:
    grade: str  # A / B / C / D
    rationale: str


def deal_grade(
    *,
    score: float,
    data_complete: bool,
    net_yield: float | None,
    value_gap_pct: float | None,
    negotiation_score: float,
) -> DealGrade:
    """A simple A-D letter grade fusing quality (score), evidence (data completeness), return
    (net yield), value (gap vs model) and motivation. Deliberately conservative: an
    incomplete-data listing is capped at B, because we can't fully stand behind it."""
    points = 0
    if score >= 55:
        points += 2
    elif score >= 35:
        points += 1
    if (net_yield or 0) >= 0.04:
        points += 1
    if (value_gap_pct or 0) >= 0.10:
        points += 1
    if negotiation_score >= 45:
        points += 1
    reasons = []
    if score >= 55:
        reasons.append("strong overall fit")
    if (net_yield or 0) >= 0.04:
        reasons.append(f"{(net_yield or 0) * 100:.1f}% net yield")
    if (value_gap_pct or 0) >= 0.10:
        reasons.append(f"{(value_gap_pct or 0) * 100:.0f}% under model value")
    if negotiation_score >= 45:
        reasons.append("motivated seller")

    if points >= 4:
        grade = "A"
    elif points >= 3:
        grade = "B"
    elif points >= 1:
        grade = "C"
    else:
        grade = "D"
    # Evidence cap: never award an A/B to a listing we can't fully verify.
    if not data_complete and grade in ("A", "B"):
        grade = "B" if grade == "A" else "C"
        reasons.append("capped — incomplete data")
    return DealGrade(grade=grade, rationale=", ".join(reasons) or "limited signals")
