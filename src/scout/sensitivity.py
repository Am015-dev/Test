"""Interest-rate × vacancy sensitivity grid for a leveraged rental purchase.

Pure function only — no DB, no network, no Streamlit. It takes plain numbers in
and returns a plain ``dict`` out, so it is safe to call from the UI, the
pipeline, or a test without any side effects.

The single deal figures in ``investment.py`` / ``finance.py`` answer "what is my
return at one rate and one vacancy assumption?". This module sweeps a whole
grid of both at once — the classic two-axis stress table a buyer eyeballs to
see how far the deal is from going cash-flow negative when the mortgage repriced
or the flat sits empty longer than hoped.

Reuses ``finance.mortgage_monthly_payment`` for the amortizing-loan payment so
the maths matches the rest of the model. FAILS SOFT: given a non-positive price
or rent it returns an empty, None-safe structure (the axes echoed back with
empty matrices) rather than raising, so a listing with incomplete data renders a
blank table instead of crashing the run.
"""

from __future__ import annotations

from .finance import mortgage_monthly_payment

# Default axes: a plausible mortgage-rate band and vacancy band for the market.
_DEFAULT_RATES = [0.03, 0.04, 0.05, 0.06]
_DEFAULT_VACANCIES = [0.0, 0.05, 0.10, 0.15]


def sensitivity_grid(
    price: int,
    annual_rent: float,
    *,
    rates: list[float] | None = None,
    vacancies: list[float] | None = None,
    deposit_pct: float = 0.30,
    term_years: int = 25,
    annual_costs_pct: float = 0.12,
) -> dict:
    """Net annual yield and monthly cashflow for every (mortgage rate, vacancy) pair.

    For each ``rate`` (rows) × ``vacancy`` (columns) cell:

    * effective rent  = ``annual_rent * (1 - vacancy)``
    * running costs   = ``annual_rent * annual_costs_pct`` (share of gross rent)
    * loan            = ``price * (1 - deposit_pct)``, financed over ``term_years``
    * net yield       = (effective rent − running costs − annual mortgage interest) / price
    * monthly cashflow = (effective rent − running costs − annual mortgage payment) / 12

    Interest (the yield drag) is the first-year approximation ``loan * rate``,
    while cashflow subtracts the full amortizing payment (interest + principal),
    which is what actually leaves the buyer's account each month.

    Returns a dict shaped for a Streamlit table::

        {
            "rates": [...],              # row axis, echoed back
            "vacancies": [...],          # column axis, echoed back
            "net_yield": [[...], ...],   # net_yield[rate_i][vacancy_j], fraction
            "cashflow_monthly": [[...], ...],
        }

    On a non-positive price or rent the two matrices come back empty (the axes
    are still echoed) so callers can rely on the keys always being present.
    """
    rate_axis = _DEFAULT_RATES if rates is None else list(rates)
    vacancy_axis = _DEFAULT_VACANCIES if vacancies is None else list(vacancies)

    empty = {
        "rates": rate_axis,
        "vacancies": vacancy_axis,
        "net_yield": [],
        "cashflow_monthly": [],
    }
    if not price or price <= 0 or not annual_rent or annual_rent <= 0:
        return empty

    running_costs = annual_rent * annual_costs_pct
    loan = price * (1 - deposit_pct)

    net_yield: list[list[float]] = []
    cashflow_monthly: list[list[float]] = []
    for rate in rate_axis:
        annual_payment = mortgage_monthly_payment(loan, rate, term_years) * 12
        annual_interest = loan * rate  # first-year interest drag on yield
        yield_row: list[float] = []
        cash_row: list[float] = []
        for vac in vacancy_axis:
            effective_rent = annual_rent * (1 - vac)
            net_income = effective_rent - running_costs - annual_interest
            monthly_cf = (effective_rent - running_costs - annual_payment) / 12
            yield_row.append(round(net_income / price, 4))
            cash_row.append(round(monthly_cf, 2))
        net_yield.append(yield_row)
        cashflow_monthly.append(cash_row)

    return {
        "rates": rate_axis,
        "vacancies": vacancy_axis,
        "net_yield": net_yield,
        "cashflow_monthly": cashflow_monthly,
    }
