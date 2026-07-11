"""Unit tests for the pure finance model — no DB, no network."""

from __future__ import annotations

import pytest

from scout.finance import (
    CostAssumptions,
    acquisition_costs,
    annual_operating_costs,
    leverage_summary,
    mortgage_monthly_payment,
    net_operating_income,
    net_yield,
)

DEFAULTS = CostAssumptions()


def test_mortgage_payment_matches_known_amortization():
    # Textbook case: 100,000 @ 4% APR over 25 years ~= 527.84/mo.
    payment = mortgage_monthly_payment(100_000, 0.04, 25)
    assert payment == pytest.approx(527.84, abs=0.05)


def test_mortgage_payment_zero_rate_is_straight_division():
    # No interest -> principal split evenly across the term.
    payment = mortgage_monthly_payment(120_000, 0.0, 20)
    assert payment == pytest.approx(120_000 / (20 * 12))


def test_mortgage_payment_non_positive_years_is_zero():
    assert mortgage_monthly_payment(100_000, 0.04, 0) == 0.0
    assert mortgage_monthly_payment(100_000, 0.04, -5) == 0.0


def test_mortgage_payment_non_positive_principal_is_zero():
    assert mortgage_monthly_payment(0, 0.04, 25) == 0.0
    assert mortgage_monthly_payment(-100, 0.04, 25) == 0.0


def test_private_seller_waives_agent_fee():
    price = 150_000
    private = acquisition_costs(price, True)
    agented = acquisition_costs(price, False)
    assert private is not None and agented is not None
    assert private < agented
    # Difference should be exactly the agent fee.
    assert agented - private == pytest.approx(price * DEFAULTS.agent_pct)
    # Hand-computed: (0.0309 + 0.012 + 0.006) * 150000 = 7335.0
    assert private == pytest.approx(7335.0)
    # + agent fee (0.02 * 150000 = 3000) = 10335.0
    assert agented == pytest.approx(10335.0)


def test_annual_operating_costs_skips_enfia_without_area():
    price = 150_000
    annual_rent = 700 * 12
    with_area = annual_operating_costs(annual_rent, price, 60)
    without_area = annual_operating_costs(annual_rent, price, None)
    assert with_area is not None and without_area is not None
    # ENFIA term = 4.0 * 60 = 240, so with_area should be exactly that much higher.
    assert with_area - without_area == pytest.approx(240.0)


def test_net_operating_income_hand_computed():
    price = 150_000
    annual_rent = 700 * 12  # 8400
    # mgmt(0%) + maintenance(8%) of rent = 672
    # ENFIA = 4.0 * 60 = 240
    # insurance = 0.001 * 150000 = 150
    # total op costs = 1062
    # effective rent = 8400 * 0.95 = 7980
    # NOI = 7980 - 1062 = 6918
    noi = net_operating_income(annual_rent, price, 60)
    assert noi == pytest.approx(6918.0)


def test_net_yield_sanity_case():
    price = 150_000
    annual_rent = 700 * 12
    ny = net_yield(price, annual_rent, 60, is_private_seller=True)
    assert ny is not None
    # NOI 6918 / (150000 + 7335 acquisition costs) = 6918 / 157335
    assert ny == pytest.approx(6918.0 / 157_335.0)
    assert 0.03 < ny < 0.06  # sane single-digit-percent yield


def test_leverage_summary_full_case():
    price = 150_000
    annual_rent = 700 * 12
    result = leverage_summary(
        price,
        annual_rent,
        60,
        is_private_seller=True,
        deposit_pct=0.25,
        annual_rate=0.04,
        years=25,
    )
    assert result is not None

    deposit = price * 0.25
    acq = acquisition_costs(price, True)
    assert result["loan"] == pytest.approx(price - deposit)
    assert result["cash_invested"] == pytest.approx(deposit + acq)
    assert result["noi"] == pytest.approx(6918.0)
    assert result["annual_debt_service"] == pytest.approx(result["monthly_payment"] * 12)
    assert result["annual_cashflow_after_debt"] == pytest.approx(
        result["noi"] - result["annual_debt_service"]
    )
    # This particular case is slightly cashflow-negative after debt service,
    # so cash-on-cash should come out negative.
    assert result["cash_on_cash"] < 0
    assert result["cash_on_cash"] == pytest.approx(
        result["annual_cashflow_after_debt"] / result["cash_invested"]
    )


def test_leverage_summary_fails_soft_on_bad_inputs():
    assert leverage_summary(0, 8400, 60, True, 0.25, 0.04, 25) is None
    assert leverage_summary(150_000, None, 60, True, 0.25, 0.04, 25) is None


def test_fail_soft_on_missing_or_non_positive_inputs():
    assert acquisition_costs(0, True) is None
    assert acquisition_costs(-100, True) is None
    assert annual_operating_costs(8400, 0, 60) is None
    assert net_operating_income(None, 150_000, 60) is None
    assert net_operating_income(0, 150_000, 60) is None
    assert net_yield(0, 8400, 60, True) is None
    assert net_yield(150_000, None, 60, True) is None
    # annual_rent and area_m2 may be None without raising.
    assert annual_operating_costs(None, 150_000, None) is not None
