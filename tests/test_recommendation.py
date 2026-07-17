"""The BUY/WATCH/PASS recommendation engine."""

from scout.recommendation import recommend


def _base(**kw):
    d = {
        "price": 200_000,
        "area_m2": 80.0,
        "est_monthly_rent": 900,
        "rent_estimated": False,
        "net_yield": 0.05,
        "value_gap_pct": None,
        "days_on_market": 30,
        "energy_class": "B",
        "is_private_seller": False,
        "strategy_tags": [],
        "excluded": False,
    }
    d.update(kw)
    return d


def test_excluded_is_pass():
    r = recommend(_base(excluded=True, exclusion_reason="ground/low floor"))
    assert r.verdict == "PASS" and "floor" in r.headline


def test_weak_dscr_is_pass_with_honest_reason():
    # tiny rent → mortgage not covered → PASS, and the reason is stated
    r = recommend(_base(price=400_000, est_monthly_rent=500, net_yield=0.01))
    assert r.verdict == "PASS"
    assert any("mortgage" in x or "yield" in x for x in r.risks)


def test_undervalued_long_sitting_is_buy():
    r = recommend(_base(value_gap_pct=0.25, days_on_market=300, net_yield=0.05))
    assert r.verdict == "BUY"
    assert "offer" in r.headline.lower() or "buy" in r.headline.lower()


def test_ordinary_listing_is_watch_or_pass_not_hyped():
    r = recommend(_base(net_yield=0.038, value_gap_pct=None, days_on_market=20))
    assert r.verdict in {"WATCH", "PASS"}


def test_value_add_play_on_poor_energy():
    r = recommend(_base(energy_class="F", strategy_tags=["Value-add"], net_yield=0.04))
    assert "renovate" in r.play.lower() or "value-add" in r.play.lower()
    assert any("EPBD" in x or "renovation" in x for x in r.risks + r.rationale)


def test_imputed_rent_is_flagged_as_risk():
    r = recommend(_base(rent_estimated=True))
    assert any("estimate" in x for x in r.risks)


def test_never_raises_on_empty():
    r = recommend({})
    assert r.verdict in {"BUY", "WATCH", "PASS"}
