"""Unit tests for the five-year total-return projection — no DB, no network."""

from __future__ import annotations

from scout.projection import five_year_projection

# A healthy, cash-flowing base case: 200k flat, ~10k/yr rent, 75 m2.
PRICE = 200_000
RENT = 10_800
AREA = 75.0


def test_loan_balance_strictly_decreases_each_year():
    proj = five_year_projection(PRICE, RENT, AREA)
    balances = [y["loan_balance"] for y in proj["years"]]
    assert balances == sorted(balances, reverse=True)
    for earlier, later in zip(balances, balances[1:], strict=False):
        assert later < earlier


def test_equity_grows_each_year():
    proj = five_year_projection(PRICE, RENT, AREA)
    equity = [y["equity"] for y in proj["years"]]
    for earlier, later in zip(equity, equity[1:], strict=False):
        assert later > earlier


def test_total_return_positive_for_healthy_case():
    proj = five_year_projection(PRICE, RENT, AREA)
    assert proj["total"]["total_return_pct"] > 0
    # Four pillars all point the right way.
    assert proj["total"]["cumulative_cash_flow"] != 0
    assert proj["total"]["property_appreciation"] > 0
    assert proj["total"]["debt_paydown"] > 0
    assert proj["total"]["equity"] > proj["deposit"]


def test_higher_appreciation_gives_higher_total_return():
    low = five_year_projection(PRICE, RENT, AREA, appreciation_pct=0.01)
    high = five_year_projection(PRICE, RENT, AREA, appreciation_pct=0.05)
    assert high["total"]["total_return_pct"] > low["total"]["total_return_pct"]


def test_shape_has_five_years_and_total():
    proj = five_year_projection(PRICE, RENT, AREA)
    assert [y["year"] for y in proj["years"]] == [1, 2, 3, 4, 5]
    assert proj["assumptions"]["appreciation_pct"] == 0.02


def test_none_safe_on_missing_rent_and_bad_price():
    assert five_year_projection(PRICE, None, AREA) is None
    assert five_year_projection(0, RENT, AREA) is None
    assert five_year_projection(-1, RENT, AREA) is None
    assert five_year_projection(PRICE, 0, AREA) is None
