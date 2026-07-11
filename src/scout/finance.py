"""Real-return finance model for a rental property purchase.

Pure functions only — no DB, no network, no Streamlit. Everything here takes
plain numbers in and returns plain numbers (or ``None``) out, so it is safe to
call from the UI, the pipeline, or a test without any side effects.

All functions FAIL SOFT: given missing or non-positive required inputs they
return ``None`` rather than raising, so a listing with incomplete data simply
shows blank finance fields instead of crashing the run.

Greek-market cost model (spec):
1. One-off acquisition costs on top of the purchase price (transfer tax,
   notary, lawyer, buyer's agent — the last waived for private-seller deals).
2. Annual operating costs (management, maintenance, ENFIA, insurance) netted
   against effective (vacancy-adjusted) rent to get NOI.
3. Net yield = NOI / total cash price (price + acquisition costs).
4. Optional mortgage leverage: standard amortizing loan, debt service
   subtracted from NOI to get cash-on-cash return on the cash actually put in
   (deposit + acquisition costs).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostAssumptions:
    """Editable Greek-market cost defaults. The UI lets the user override any
    of these per-listing; values here are sane starting approximations only."""

    vacancy_rate: float = 0.05  # share of the year unrented
    mgmt_pct_of_rent: float = 0.0  # letting-agent / management fee (0 = self-managed)
    maintenance_pct_of_rent: float = 0.08  # repairs & upkeep reserve
    enfia_eur_per_m2_year: float = 4.0  # ENFIA annual property tax, ~€2-13/m2/yr by zone
    insurance_pct_of_value_year: float = 0.001  # building insurance
    transfer_tax_pct: float = 0.0309  # property transfer tax on purchase
    notary_pct: float = 0.012  # notary fees
    legal_pct: float = 0.006  # lawyer fees
    agent_pct: float = 0.02  # buyer-side agent fee (waived for private-seller deals)


# Module-level default so callers can omit `a` in every call below.
_DEFAULT = CostAssumptions()


def acquisition_costs(
    price: int, is_private_seller: bool, a: CostAssumptions = _DEFAULT
) -> float | None:
    """One-off buying costs on top of `price`: transfer tax + notary + legal
    (+ buyer's agent, unless the seller is private and there is no agent fee)."""
    if price is None or price <= 0:
        return None
    pct = a.transfer_tax_pct + a.notary_pct + a.legal_pct
    if not is_private_seller:
        pct += a.agent_pct
    return price * pct


def annual_operating_costs(
    annual_rent: float | None,
    price: int,
    area_m2: float | None,
    a: CostAssumptions = _DEFAULT,
) -> float | None:
    """Management + maintenance (both % of rent) + ENFIA (€/m2/yr * area, skipped
    when area is unknown) + insurance (% of price)."""
    if price is None or price <= 0:
        return None
    rent = annual_rent or 0.0
    costs = rent * (a.mgmt_pct_of_rent + a.maintenance_pct_of_rent)
    if area_m2 is not None and area_m2 > 0:
        costs += a.enfia_eur_per_m2_year * area_m2
    costs += a.insurance_pct_of_value_year * price
    return costs


def net_operating_income(
    annual_rent: float | None,
    price: int,
    area_m2: float | None,
    a: CostAssumptions = _DEFAULT,
) -> float | None:
    """Effective (vacancy-adjusted) rent minus annual operating costs."""
    if annual_rent is None or annual_rent <= 0:
        return None
    op_costs = annual_operating_costs(annual_rent, price, area_m2, a)
    if op_costs is None:
        return None
    effective_rent = annual_rent * (1 - a.vacancy_rate)
    return effective_rent - op_costs


def net_yield(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    is_private_seller: bool,
    a: CostAssumptions = _DEFAULT,
) -> float | None:
    """NOI / (price + acquisition costs), as a fraction (e.g. 0.041 = 4.1%)."""
    noi = net_operating_income(annual_rent, price, area_m2, a)
    if noi is None:
        return None
    acq = acquisition_costs(price, is_private_seller, a)
    if acq is None:
        return None
    total_cost = price + acq
    if total_cost <= 0:
        return None
    return noi / total_cost


def mortgage_monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """Standard amortizing-loan monthly payment:

        M = P * r(1+r)^n / ((1+r)^n - 1)

    where r is the monthly rate and n the number of monthly payments.
    """
    if principal is None or principal <= 0:
        return 0.0
    if years is None or years <= 0:
        return 0.0
    months = years * 12
    if annual_rate is None or annual_rate == 0:
        return principal / months
    r = annual_rate / 12
    factor = (1 + r) ** months
    return principal * r * factor / (factor - 1)


def leverage_summary(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    is_private_seller: bool,
    deposit_pct: float,
    annual_rate: float,
    years: int,
    a: CostAssumptions = _DEFAULT,
) -> dict | None:
    """Mortgage-leveraged return summary. `deposit_pct` is the fraction of the
    purchase price put down in cash (e.g. 0.25); the rest is financed."""
    if price is None or price <= 0 or annual_rent is None:
        return None

    noi = net_operating_income(annual_rent, price, area_m2, a)
    acq = acquisition_costs(price, is_private_seller, a)
    if noi is None or acq is None:
        return None

    deposit = price * deposit_pct
    loan = price - deposit
    monthly_payment = mortgage_monthly_payment(loan, annual_rate, years)
    annual_debt_service = monthly_payment * 12
    cash_invested = deposit + acq
    annual_cashflow_after_debt = noi - annual_debt_service
    cash_on_cash = annual_cashflow_after_debt / cash_invested if cash_invested > 0 else None

    return {
        "loan": loan,
        "monthly_payment": monthly_payment,
        "annual_debt_service": annual_debt_service,
        "cash_invested": cash_invested,
        "noi": noi,
        "annual_cashflow_after_debt": annual_cashflow_after_debt,
        "cash_on_cash": cash_on_cash,
    }
