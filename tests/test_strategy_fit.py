"""Unit tests for investor strategy tagging — pure, no DB, no network."""

from __future__ import annotations

from scout.strategy_fit import STRATEGY_DESCRIPTIONS, strategy_tags


def _listing(**overrides) -> dict:
    """A plain listing dict (the ``_row_to_dict`` shape) with neutral defaults that trip
    NO strategy tags, overridable per test."""
    base = dict(
        net_yield=0.03,
        gross_yield=0.04,
        value_gap_pct=None,
        energy_class="B",
        year_built=2010,
        renovated_year=None,
        days_on_market=20,
        negotiation_score=0.0,
        price=200_000,
        area_m2=80.0,
        metro_distance_m=1500,
        location_precision="exact",
        rent_estimated=False,
    )
    base.update(overrides)
    return base


def test_high_yield_real_rent_is_cashflow():
    tags = strategy_tags(_listing(net_yield=0.055, rent_estimated=False))
    assert "Cashflow" in tags


def test_imputed_rent_high_yield_is_not_cashflow():
    """A strong yield built on an ESTIMATED rent is the fake-yield trap — no Cashflow tag."""
    tags = strategy_tags(_listing(net_yield=0.08, rent_estimated=True))
    assert "Cashflow" not in tags


def test_old_low_energy_flat_is_value_add():
    tags = strategy_tags(_listing(year_built=1975, energy_class="E", renovated_year=None))
    assert "Value-add" in tags


def test_poor_energy_alone_is_value_add():
    tags = strategy_tags(_listing(year_built=2012, energy_class="F"))
    assert "Value-add" in tags


def test_renovated_old_flat_is_not_value_add():
    """Renovation upside is already captured once it's been renovated."""
    tags = strategy_tags(_listing(year_built=1975, energy_class="E", renovated_year=2022))
    assert "Value-add" not in tags


def test_significant_value_gap_is_underpriced():
    assert "Underpriced" in strategy_tags(_listing(value_gap_pct=0.18))
    assert "Underpriced" not in strategy_tags(_listing(value_gap_pct=0.05))


def test_motivated_by_negotiation_score():
    assert "Motivated seller" in strategy_tags(_listing(negotiation_score=60))


def test_motivated_by_days_on_market():
    assert "Motivated seller" in strategy_tags(_listing(days_on_market=200))


def test_prime_location_needs_exact_and_close_metro():
    assert "Prime location" in strategy_tags(
        _listing(location_precision="exact", metro_distance_m=300)
    )
    # Same distance but only a municipality centroid -> not a per-listing prime tag.
    assert "Prime location" not in strategy_tags(
        _listing(location_precision="area", metro_distance_m=300)
    )


def test_multiple_tags_are_ordered_and_deduped():
    tags = strategy_tags(
        _listing(
            net_yield=0.06,
            value_gap_pct=0.20,
            negotiation_score=50,
            metro_distance_m=200,
        )
    )
    assert tags == ["Cashflow", "Underpriced", "Motivated seller", "Prime location"]


def test_empty_dict_returns_empty_list():
    assert strategy_tags({}) == []


def test_never_raises_on_garbage():
    assert strategy_tags({"net_yield": "n/a", "value_gap_pct": object()}) == []
    assert strategy_tags(None) == []  # type: ignore[arg-type]


def test_every_tag_has_a_description():
    produced = {
        "Cashflow",
        "Value-add",
        "Underpriced",
        "Motivated seller",
        "Prime location",
    }
    assert produced == set(STRATEGY_DESCRIPTIONS)
