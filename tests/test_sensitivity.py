"""Tests for the interest-rate × vacancy sensitivity grid."""

from __future__ import annotations

from scout.sensitivity import sensitivity_grid


def test_grid_dimensions_and_axes_echoed():
    g = sensitivity_grid(200_000, 12_000)
    assert g["rates"] == [0.03, 0.04, 0.05, 0.06]
    assert g["vacancies"] == [0.0, 0.05, 0.10, 0.15]
    # One row per rate, one column per vacancy, for both matrices.
    assert len(g["net_yield"]) == 4
    assert all(len(row) == 4 for row in g["net_yield"])
    assert len(g["cashflow_monthly"]) == 4
    assert all(len(row) == 4 for row in g["cashflow_monthly"])


def test_higher_rate_lowers_cashflow():
    g = sensitivity_grid(200_000, 12_000)
    # Fix vacancy (first column), walk down the rate rows: cashflow must fall.
    col = [row[0] for row in g["cashflow_monthly"]]
    assert col == sorted(col, reverse=True)
    assert col[0] > col[-1]


def test_higher_vacancy_lowers_net_yield():
    g = sensitivity_grid(200_000, 12_000)
    # Fix rate (first row), walk across the vacancy columns: net yield must fall.
    row = g["net_yield"][0]
    assert row == sorted(row, reverse=True)
    assert row[0] > row[-1]


def test_custom_axes_respected():
    g = sensitivity_grid(200_000, 12_000, rates=[0.02, 0.07], vacancies=[0.0, 0.20, 0.40])
    assert g["rates"] == [0.02, 0.07]
    assert g["vacancies"] == [0.0, 0.20, 0.40]
    assert len(g["net_yield"]) == 2
    assert all(len(r) == 3 for r in g["net_yield"])


def test_degenerate_inputs_return_empty_but_safe():
    for bad in (
        sensitivity_grid(0, 12_000),
        sensitivity_grid(-1, 12_000),
        sensitivity_grid(200_000, 0),
        sensitivity_grid(200_000, -5),
    ):
        # Axes still present so the caller's keys never KeyError.
        assert bad["rates"] and bad["vacancies"]
        assert bad["net_yield"] == []
        assert bad["cashflow_monthly"] == []


def test_all_cash_has_no_mortgage_payment():
    # deposit_pct=1.0 → loan is zero → no payment, no interest drag.
    g = sensitivity_grid(200_000, 12_000, deposit_pct=1.0)
    # Net yield is then identical across every rate (rate only bites via the loan).
    first_col = [row[0] for row in g["net_yield"]]
    assert len(set(first_col)) == 1
    # Cashflow is just effective rent minus running costs, /12, also rate-invariant.
    cash_col = [row[0] for row in g["cashflow_monthly"]]
    assert len(set(cash_col)) == 1
    # And it is positive: 12k rent, 0% vacancy, 12% costs → (12000 - 1440)/12 = 880.
    assert cash_col[0] == 880.0
