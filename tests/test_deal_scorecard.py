"""Transparent Athens-calibrated deal scorecard (complements investment.deal_grade)."""

from __future__ import annotations

from scout.deal_scorecard import scorecard


def _strong_listing() -> dict:
    """A genuinely good Athens buy-to-let: real high rent, cheap, under model, motivated."""
    return dict(
        price=150_000,
        area_m2=75.0,
        net_yield=0.05,
        gross_yield=0.072,
        listed_rent=900,
        est_monthly_rent=900,
        rent_estimated=False,  # a REAL listed rent, so the yield check counts
        value_gap_pct=0.15,
        days_on_market=200,
        negotiation_score=60,
        energy_class="B",
        is_private_seller=True,
    )


def _weak_listing() -> dict:
    """Overpriced, thin imputed rent, poor energy, no motivation — should read Pass."""
    return dict(
        price=400_000,
        area_m2=40.0,
        net_yield=0.01,
        gross_yield=0.018,
        est_monthly_rent=500,
        rent_estimated=True,
        value_gap_pct=None,
        days_on_market=5,
        negotiation_score=5,
        energy_class="F",
        is_private_seller=False,
    )


def _find(card: dict, label: str) -> dict:
    return next(c for c in card["checks"] if c["label"] == label)


def test_shape_is_stable():
    card = scorecard(_strong_listing())
    assert set(card) == {"checks", "points", "max_points", "pct", "verdict"}
    for c in card["checks"]:
        assert set(c) == {"label", "points", "max_points", "note"}
    # Documented 14-point scorecard.
    assert card["max_points"] == 14


def test_strong_listing_scores_high():
    card = scorecard(_strong_listing())
    assert card["verdict"] == "Strong"
    assert card["pct"] >= 70.0
    assert card["points"] >= 10


def test_weak_listing_is_a_pass():
    card = scorecard(_weak_listing())
    assert card["verdict"] == "Pass"
    assert card["pct"] < 45.0


def test_imputed_rent_scores_zero_on_yield_with_honest_note():
    d = _strong_listing()
    d["rent_estimated"] = True  # same numbers, but the rent is now imputed
    card = scorecard(d)
    ny = _find(card, "Net yield")
    assert ny["points"] == 0
    assert "estimated" in ny["note"].lower()


def test_missing_everything_is_low_and_does_not_crash():
    card = scorecard({})
    assert card["verdict"] == "Pass"
    assert card["pct"] < 45.0
    # Every unknown input is honestly labelled, never scored as good.
    assert all(c["points"] == 0 for c in card["checks"])
    assert any("unknown" in c["note"].lower() for c in card["checks"])


def test_missing_keys_never_raise():
    for d in ({}, {"price": None}, {"price": "oops", "area_m2": "bad"}, {"energy_class": 3}):
        card = scorecard(d)
        assert card["verdict"] == "Pass"


def test_points_never_exceed_max_points():
    for d in (_strong_listing(), _weak_listing(), {}):
        card = scorecard(d)
        assert 0 <= card["points"] <= card["max_points"]
        for c in card["checks"]:
            assert 0 <= c["points"] <= c["max_points"]


def test_unknown_value_gap_is_not_credited():
    d = _strong_listing()
    d["value_gap_pct"] = None
    gap = _find(scorecard(d), "Value gap")
    assert gap["points"] == 0
    assert "unknown" in gap["note"].lower()
