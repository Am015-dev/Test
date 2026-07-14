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


# Single-point rate/vacancy assumption for the one-axis what-if sweeps below.
# (The grid above sweeps rate × vacancy; these hold both fixed and sweep one
# other lever, so the buyer sees "what if rent is 10% softer / the price is 10%
# higher than asking?" in isolation.)
_DEFAULT_STEPS = (-0.10, -0.05, 0.0, 0.05, 0.10)
_DEFAULT_RATE = 0.04
_DEFAULT_VACANCY = 0.05


def rent_sensitivity(
    price: int,
    annual_rent: float,
    *,
    steps: tuple[float, ...] = _DEFAULT_STEPS,
    rate: float = _DEFAULT_RATE,
    vacancy: float = _DEFAULT_VACANCY,
    deposit_pct: float = 0.30,
    term_years: int = 25,
    annual_costs_pct: float = 0.12,
) -> dict:
    """Net annual yield and monthly cashflow as the achievable rent flexes.

    For each fractional ``step`` (e.g. ``-0.10`` = 10% below the assumed rent)
    the sweep uses ``rent = annual_rent * (1 + step)`` and, mirroring
    ``sensitivity_grid`` so the numbers stay consistent:

    * effective rent   = ``rent * (1 - vacancy)``
    * running costs    = ``rent * annual_costs_pct`` (share of gross rent, so
      costs scale with rent just as they do in the grid)
    * loan             = ``price * (1 - deposit_pct)``, financed over ``term_years``
    * net yield        = (effective rent − running costs − annual interest) / price
    * monthly cashflow = (effective rent − running costs − annual payment) / 12

    Interest (the yield drag) is the first-year approximation ``loan * rate``;
    cashflow subtracts the full amortizing payment via
    ``finance.mortgage_monthly_payment``, exactly as the grid does.

    Returns::

        {
            "steps": [...],              # echoed back
            "rents": [...],              # resulting annual rent per step
            "net_yield": [...],          # fraction, per step
            "cashflow_monthly": [...],   # € per month, per step
        }

    On a non-positive price or rent the three result lists come back empty (the
    steps are still echoed) so callers can rely on the keys always being present.
    """
    step_axis = list(steps)
    empty = {
        "steps": step_axis,
        "rents": [],
        "net_yield": [],
        "cashflow_monthly": [],
    }
    if not price or price <= 0 or not annual_rent or annual_rent <= 0:
        return empty

    loan = price * (1 - deposit_pct)
    annual_payment = mortgage_monthly_payment(loan, rate, term_years) * 12
    annual_interest = loan * rate  # first-year interest drag on yield

    rents: list[float] = []
    net_yield: list[float] = []
    cashflow_monthly: list[float] = []
    for step in step_axis:
        rent = annual_rent * (1 + step)
        running_costs = rent * annual_costs_pct
        effective_rent = rent * (1 - vacancy)
        net_income = effective_rent - running_costs - annual_interest
        monthly_cf = (effective_rent - running_costs - annual_payment) / 12
        rents.append(round(rent, 2))
        net_yield.append(round(net_income / price, 4))
        cashflow_monthly.append(round(monthly_cf, 2))

    return {
        "steps": step_axis,
        "rents": rents,
        "net_yield": net_yield,
        "cashflow_monthly": cashflow_monthly,
    }


def price_sensitivity(
    price: int,
    annual_rent: float,
    *,
    steps: tuple[float, ...] = _DEFAULT_STEPS,
    rate: float = _DEFAULT_RATE,
    vacancy: float = _DEFAULT_VACANCY,
    deposit_pct: float = 0.30,
    term_years: int = 25,
    annual_costs_pct: float = 0.12,
) -> dict:
    """Cap-rate-style net yield and cash-on-cash as the purchase price flexes.

    For each fractional ``step`` (e.g. ``0.10`` = paying 10% over the assumed
    price) the sweep uses ``buy_price = price * (1 + step)``. Rent is held fixed
    (this axis is about what you pay, not what you earn), so, consistent with the
    grid's cost model:

    * effective rent   = ``annual_rent * (1 - vacancy)``
    * running costs    = ``annual_rent * annual_costs_pct``
    * NOI              = effective rent − running costs (unlevered)
    * net yield        = NOI / ``buy_price``  (the cap-rate view)
    * loan             = ``buy_price * (1 - deposit_pct)``, over ``term_years``
    * cash-on-cash     = (NOI − annual payment) / deposit, where the deposit
      ``buy_price * deposit_pct`` is the cash actually put in

    Debt service uses the full amortizing payment via
    ``finance.mortgage_monthly_payment``, matching the grid.

    Returns::

        {
            "steps": [...],          # echoed back
            "prices": [...],         # resulting buy price per step
            "net_yield": [...],      # cap-rate fraction, per step
            "cash_on_cash": [...],   # fraction, per step
        }

    On a non-positive price or rent the three result lists come back empty (the
    steps are still echoed). A degenerate per-step price (``<= 0``) yields
    ``None`` for that cell rather than dividing by zero, keeping every list the
    same length as ``steps``.
    """
    step_axis = list(steps)
    empty = {
        "steps": step_axis,
        "prices": [],
        "net_yield": [],
        "cash_on_cash": [],
    }
    if not price or price <= 0 or not annual_rent or annual_rent <= 0:
        return empty

    running_costs = annual_rent * annual_costs_pct
    effective_rent = annual_rent * (1 - vacancy)
    noi = effective_rent - running_costs  # unlevered, cap-rate numerator

    prices: list[float] = []
    net_yield: list[float | None] = []
    cash_on_cash: list[float | None] = []
    for step in step_axis:
        buy_price = price * (1 + step)
        prices.append(round(buy_price, 2))
        if buy_price <= 0:
            net_yield.append(None)
            cash_on_cash.append(None)
            continue
        loan = buy_price * (1 - deposit_pct)
        deposit = buy_price * deposit_pct
        annual_payment = mortgage_monthly_payment(loan, rate, term_years) * 12
        net_yield.append(round(noi / buy_price, 4))
        if deposit > 0:
            cash_on_cash.append(round((noi - annual_payment) / deposit, 4))
        else:
            cash_on_cash.append(None)

    return {
        "steps": step_axis,
        "prices": prices,
        "net_yield": net_yield,
        "cash_on_cash": cash_on_cash,
    }
