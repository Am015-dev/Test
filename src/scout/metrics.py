"""Standard investor metrics investors expect BY NAME — cap rate, GRM, DSCR, break-even
occupancy — computed on the same Greek cost model as ``finance.net_yield`` so they're
consistent with the rest of the tool.

Deliberately Athens-calibrated, not US-copied. The popular US rules of thumb (the "1%
rule", "50% rule") assume US-level yields and costs and are meaningless here: Athens gross
yields run ~4–6%, so a "1% monthly rent" (12%/yr) rule fails on essentially every real
flat — importing it would just paint everything red. We surface the metrics a Greek buyer
actually underwrites on, with thresholds sane for this market, and say so.
"""

from __future__ import annotations

from .finance import (
    CostAssumptions,
    annual_operating_costs,
    mortgage_monthly_payment,
    net_operating_income,
)

_DEFAULT = CostAssumptions()

# Athens-calibrated "good / ok" thresholds (not US rules of thumb).
CAP_RATE_GOOD = 0.045
CAP_RATE_OK = 0.035
GRM_GOOD = 22.0  # ~4.5% gross; lower is better
GRM_OK = 28.0
DSCR_GOOD = 1.20
DSCR_OK = 1.00
BEO_GOOD = 0.80  # break-even occupancy; lower is safer
BEO_OK = 0.90


def cap_rate(
    price: int, annual_rent: float | None, area_m2: float | None, a: CostAssumptions = _DEFAULT
) -> float | None:
    """NOI ÷ price — the unlevered income return investors quote as the 'cap rate'."""
    if not price or price <= 0:
        return None
    noi = net_operating_income(annual_rent, price, area_m2, a)
    if noi is None:
        return None
    return noi / price


def gross_rent_multiplier(price: int, annual_rent: float | None) -> float | None:
    """Price ÷ annual gross rent. Lower = cheaper relative to the rent it throws off."""
    if not price or price <= 0 or not annual_rent or annual_rent <= 0:
        return None
    return price / annual_rent


def annual_debt_service(
    price: int, *, deposit_pct: float = 0.30, rate: float = 0.045, term_years: int = 25
) -> float:
    """Yearly mortgage payment for a standard purchase (30% down, 25 yr, ~4.5%)."""
    loan = price * max(1 - deposit_pct, 0.0)
    return mortgage_monthly_payment(loan, rate, term_years) * 12


def dscr(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    *,
    deposit_pct: float = 0.30,
    rate: float = 0.045,
    term_years: int = 25,
    a: CostAssumptions = _DEFAULT,
) -> float | None:
    """Debt-service coverage ratio: NOI ÷ annual mortgage payment. ≥1 means the rent covers
    the loan; lenders and cautious investors want a cushion (≥1.2)."""
    noi = net_operating_income(annual_rent, price, area_m2, a)
    if noi is None:
        return None
    ds = annual_debt_service(price, deposit_pct=deposit_pct, rate=rate, term_years=term_years)
    if ds <= 0:
        return None
    return noi / ds


def break_even_occupancy(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    *,
    financed: bool = True,
    deposit_pct: float = 0.30,
    rate: float = 0.045,
    term_years: int = 25,
    a: CostAssumptions = _DEFAULT,
) -> float | None:
    """Minimum occupancy (0–1+) at which rent covers operating costs (+ mortgage, if
    financed). Below it the property loses money; lower is safer."""
    if not annual_rent or annual_rent <= 0 or not price or price <= 0:
        return None
    op = annual_operating_costs(annual_rent, price, area_m2, a) or 0.0
    ds = (
        annual_debt_service(price, deposit_pct=deposit_pct, rate=rate, term_years=term_years)
        if financed
        else 0.0
    )
    return (op + ds) / annual_rent


def investor_metrics(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    *,
    is_private_seller: bool = False,
    a: CostAssumptions = _DEFAULT,
) -> dict:
    """All the recognized metrics in one dict, each with a value and an Athens-calibrated
    verdict in {"good","ok","weak",None}. Missing rent → values are None (no fabrication)."""

    def verdict(v, good, ok, lower_is_better=False):
        if v is None:
            return None
        if lower_is_better:
            return "good" if v <= good else ("ok" if v <= ok else "weak")
        return "good" if v >= good else ("ok" if v >= ok else "weak")

    cr = cap_rate(price, annual_rent, area_m2, a)
    grm = gross_rent_multiplier(price, annual_rent)
    ds = dscr(price, annual_rent, area_m2, a=a)
    beo = break_even_occupancy(price, annual_rent, area_m2, a=a)
    return {
        "cap_rate": cr,
        "grm": grm,
        "dscr": ds,
        "break_even_occupancy": beo,
        "verdicts": {
            "cap_rate": verdict(cr, CAP_RATE_GOOD, CAP_RATE_OK),
            "grm": verdict(grm, GRM_GOOD, GRM_OK, lower_is_better=True),
            "dscr": verdict(ds, DSCR_GOOD, DSCR_OK),
            "break_even_occupancy": verdict(beo, BEO_GOOD, BEO_OK, lower_is_better=True),
        },
    }
