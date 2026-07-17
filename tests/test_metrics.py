"""Standard investor metrics (cap rate, GRM, DSCR, break-even occupancy)."""

import math

from scout.metrics import (
    break_even_occupancy,
    cap_rate,
    dscr,
    gross_rent_multiplier,
    investor_metrics,
)


def test_cap_rate_is_noi_over_price_and_below_gross():
    cr = cap_rate(200_000, 12_000, 80.0)
    assert cr is not None
    # NOI is net of costs/vacancy, so cap rate < gross yield (12000/200000 = 6%).
    assert 0 < cr < 0.06


def test_grm_is_price_over_annual_rent():
    assert gross_rent_multiplier(200_000, 10_000) == 20.0
    assert gross_rent_multiplier(200_000, 0) is None


def test_dscr_scales_with_rent():
    low = dscr(200_000, 8_000, 80.0)
    high = dscr(200_000, 16_000, 80.0)
    assert low is not None and high is not None
    assert high > low  # more rent → more coverage


def test_break_even_occupancy_lower_when_unfinanced():
    financed = break_even_occupancy(200_000, 12_000, 80.0, financed=True)
    cash = break_even_occupancy(200_000, 12_000, 80.0, financed=False)
    assert financed is not None and cash is not None
    assert cash < financed  # no mortgage → lower occupancy needed to break even


def test_missing_rent_yields_none_not_fabrication():
    m = investor_metrics(200_000, None, 80.0)
    assert m["cap_rate"] is None and m["grm"] is None and m["dscr"] is None
    assert all(v is None for v in m["verdicts"].values())


def test_verdicts_are_calibrated():
    # A strong-yield flat should read "good" on cap rate.
    m = investor_metrics(150_000, 12_000, 70.0)
    assert m["verdicts"]["cap_rate"] in {"good", "ok"}
    assert not math.isnan(m["cap_rate"])
