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
    if score >= 60:
        points += 2
    elif score >= 40:
        points += 1
    if (net_yield or 0) >= 0.045:
        points += 1
    # value_gap_pct is now populated ONLY when it clears the model's own ±band (see
    # valuation.apply_valuations), so any gap present here is beyond-noise, not puffery.
    if (value_gap_pct or 0) >= 0.10:
        points += 1
    if negotiation_score >= 45:
        points += 1
    reasons = []
    if score >= 60:
        reasons.append("strong overall fit")
    if (net_yield or 0) >= 0.045:
        reasons.append(f"{(net_yield or 0) * 100:.1f}% net yield")
    if (value_gap_pct or 0) >= 0.10:
        reasons.append(f"{(value_gap_pct or 0) * 100:.0f}% under model value (beyond ±band)")
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


def renovation_roi(
    energy_class: str | None,
    area_m2: float | None,
    annual_rent: float | None,
    rent_uplift_pct: float = 0.12,
) -> dict | None:
    """For an EPBD-liability flat (E/F/G), the rough return on funding the retrofit: the
    indicative capex vs. the annual rent uplift a modern, efficient flat commands. Pairs with
    epbd.epbd_flag. Returns None when there's no liability or no rent to uplift."""
    from .epbd import epbd_flag

    flag = epbd_flag(energy_class, area_m2)
    if not flag.at_risk or not flag.est_capex or not annual_rent or annual_rent <= 0:
        return None
    annual_uplift = annual_rent * rent_uplift_pct
    payback = flag.est_capex / annual_uplift if annual_uplift else None
    return {
        "capex": flag.est_capex,
        "annual_rent_uplift": int(round(annual_uplift)),
        "roi_pct": round(annual_uplift / flag.est_capex, 3),
        "payback_years": round(payback, 1) if payback else None,
    }


# Greek rental-income tax brackets (individuals): 15% to €12k, 35% to €35k, 45% above.
_TAX_BRACKETS = ((12_000, 0.15), (35_000, 0.35), (float("inf"), 0.45))


def greek_rental_tax(annual_rent: float | None) -> dict | None:
    """Progressive Greek tax on gross annual rental income, with the effective rate — the
    line item investors most often forget when they eyeball 'yield'."""
    if not annual_rent or annual_rent <= 0:
        return None
    tax, lo = 0.0, 0.0
    for hi, rate in _TAX_BRACKETS:
        if annual_rent <= lo:
            break
        band = min(annual_rent, hi) - lo
        tax += band * rate
        lo = hi
    return {"annual_tax": int(round(tax)), "effective_rate": round(tax / annual_rent, 3)}


def exit_value(
    price: int,
    area_median_ppm2_trend_pct: float | None,
    hold_years: int = 5,
) -> dict | None:
    """A simple exit projection: compound the area's €/m² trend over the hold period. Honest
    about being a projection off a thin trend — a range, not a promise. None without a trend."""
    if area_median_ppm2_trend_pct is None:
        return None
    factor = (1 + area_median_ppm2_trend_pct) ** hold_years
    projected = int(round(price * factor))
    return {
        "hold_years": hold_years,
        "annual_trend_pct": round(area_median_ppm2_trend_pct, 4),
        "projected_value": projected,
        "total_gain_pct": round(factor - 1, 3),
    }
