"""Five-year total-return projection for a leveraged rental flat.

Pure functions on top of ``finance.py``: no DB, no network, no Streamlit. Fails soft
(returns ``None`` on missing/degenerate inputs) so a listing with incomplete data shows a
blank projection rather than a bogus figure.

Where ``finance.leverage_summary`` answers "what does year one look like?", this walks the
hold period forward and adds up the FOUR PILLARS of a levered property return:

1. Cumulative net cash flow — NOI minus debt service, banked each year.
2. Property appreciation — the value compounded at a MODEST assumed rate.
3. Mortgage debt paydown — principal retired by the amortization schedule.
4. Equity growth — pillars 2 + 3, i.e. value minus remaining loan balance.

The appreciation rate is an ASSUMPTION, not a forecast: the default of 2%/yr is deliberately
conservative (roughly long-run inflation) and is echoed back in the returned ``assumptions``
block so the caller can label it as such.
"""

from __future__ import annotations

from .finance import (
    CostAssumptions,
    acquisition_costs,
    mortgage_monthly_payment,
    net_operating_income,
)

_DEFAULT = CostAssumptions()


def _amortization_balances(
    loan: float, annual_rate: float, term_years: int, through_years: int
) -> list[float]:
    """Remaining loan balance at the END of each year 1..``through_years``, walking the
    standard amortization schedule month by month. Zero-rate loans amortize linearly."""
    payment = mortgage_monthly_payment(loan, annual_rate, term_years)
    r = (annual_rate or 0.0) / 12
    balance = loan
    balances: list[float] = []
    for _ in range(through_years):
        for _ in range(12):
            interest = balance * r
            balance = balance + interest - payment
        balances.append(max(balance, 0.0))
    return balances


def five_year_projection(
    price: int,
    annual_rent: float | None,
    area_m2: float | None,
    *,
    appreciation_pct: float = 0.02,
    deposit_pct: float = 0.30,
    rate: float = 0.045,
    term_years: int = 25,
    is_private_seller: bool = False,
    a: CostAssumptions = _DEFAULT,
    hold_years: int = 5,
) -> dict | None:
    """Year-by-year total return on the cash invested over a ``hold_years`` (default 5) hold.

    Compounds property value at the MODEST assumed ``appreciation_pct`` (default 2%/yr — an
    assumption, not a forecast), amortizes the loan for the true remaining balance, and banks
    NOI-minus-debt-service each year. Returns ``None`` on missing rent or non-positive price."""
    if price is None or price <= 0 or not annual_rent or annual_rent <= 0:
        return None

    noi = net_operating_income(annual_rent, price, area_m2, a)
    acq = acquisition_costs(price, is_private_seller, a)
    if noi is None or acq is None:
        return None

    deposit = price * deposit_pct
    loan = price - deposit
    initial_cash = deposit + acq
    if initial_cash <= 0:
        return None

    annual_payment = mortgage_monthly_payment(loan, rate, term_years) * 12
    annual_cash_flow = noi - annual_payment
    balances = _amortization_balances(loan, rate, term_years, hold_years)

    years: list[dict] = []
    for i in range(hold_years):
        year = i + 1
        value = price * (1 + appreciation_pct) ** year
        balance = balances[i]
        equity = value - balance
        cumulative_cash_flow = annual_cash_flow * year
        # Return on cash: equity gained (vs the deposit already in the deal) + cash banked.
        equity_gain = equity - deposit
        total_return = (equity_gain + cumulative_cash_flow) / initial_cash
        years.append(
            {
                "year": year,
                "cumulative_cash_flow": round(cumulative_cash_flow, 2),
                "property_value": round(value, 2),
                "loan_balance": round(balance, 2),
                "equity": round(equity, 2),
                "total_return_pct": round(total_return, 4),
            }
        )

    final = years[-1]
    end_value = price * (1 + appreciation_pct) ** hold_years
    end_balance = balances[-1]
    total = {
        "hold_years": hold_years,
        # The four pillars, at the end of the hold.
        "cumulative_cash_flow": final["cumulative_cash_flow"],
        "property_appreciation": round(end_value - price, 2),
        "debt_paydown": round(loan - end_balance, 2),
        "equity": final["equity"],
        "equity_gain": round(final["equity"] - deposit, 2),
        "total_return_pct": final["total_return_pct"],
    }

    return {
        "assumptions": {
            "appreciation_pct": appreciation_pct,  # MODEST assumption, not a forecast
            "deposit_pct": deposit_pct,
            "rate": rate,
            "term_years": term_years,
        },
        "deposit": round(deposit, 2),
        "loan": round(loan, 2),
        "acquisition_costs": round(acq, 2),
        "initial_cash": round(initial_cash, 2),
        "annual_noi": round(noi, 2),
        "annual_mortgage_payment": round(annual_payment, 2),
        "annual_cash_flow": round(annual_cash_flow, 2),
        "years": years,
        "total": total,
    }
