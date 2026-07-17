"""Tests for the Greek total cash-to-acquire model."""

from __future__ import annotations

from scout.acquisition import acquisition_costs


def test_resale_total_is_about_1_09x_price():
    r = acquisition_costs(200_000)
    # 3.09 + 1.5 + 0.5 + 1.0 + 2.48 = 8.57% of fees on top of the price.
    assert 1.08 < r["total_cash"] / r["price"] < 1.10
    assert 0.08 < r["fees_pct_of_price"] < 0.10


def test_private_sale_is_cheaper_than_agent_sale():
    with_agent = acquisition_costs(200_000)
    private = acquisition_costs(200_000, agent_fee_pct=0.0)
    assert private["agent"] == 0
    assert private["total_cash"] < with_agent["total_cash"]
    # The only difference is the agent fee (~2.48% of price).
    assert with_agent["total_cash"] - private["total_cash"] == round(200_000 * 0.0248)


def test_line_items_sum_to_total():
    r = acquisition_costs(275_000, include_legal=True)
    line_items = r["transfer_tax"] + r["notary"] + r["land_registry"] + r["legal"] + r["agent"]
    assert line_items == r["total_fees"]
    assert r["price"] + r["total_fees"] == r["total_cash"]


def test_new_build_vat_costs_more_than_resale_transfer_tax():
    resale = acquisition_costs(200_000)
    new_build = acquisition_costs(200_000, new_build=True)
    # 24% VAT dwarfs the 3.09% transfer tax.
    assert new_build["transfer_tax"] == round(200_000 * 0.24)
    assert new_build["total_cash"] > resale["total_cash"]


def test_include_legal_toggle():
    with_legal = acquisition_costs(200_000, include_legal=True)
    without_legal = acquisition_costs(200_000, include_legal=False)
    assert without_legal["legal"] == 0
    assert with_legal["legal"] == round(200_000 * 0.01)
    assert with_legal["total_cash"] > without_legal["total_cash"]


def test_degenerate_price_fails_soft():
    for bad in (0, -5000):
        r = acquisition_costs(bad)
        assert r["total_cash"] == 0
        assert r["total_fees"] == 0
        assert r["fees_pct_of_price"] == 0.0
