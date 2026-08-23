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


def test_genuinely_undervalued_high_yield_is_buy():
    # Deep, significance-gated gap AND a solid net yield both past the raised bars → BUY.
    r = recommend(_base(value_gap_pct=0.20, net_yield=0.06, days_on_market=300))
    assert r.verdict == "BUY"
    assert "offer" in r.headline.lower() or "buy" in r.headline.lower()


def test_buy_blocked_when_yield_is_worst_in_area_despite_flat_bar_cleared():
    # 5.5% net yield clears the flat BUY_YIELD bar, but yield_percentile=0.0 (set by
    # relative_value.annotate_relative_value on the whole pool) says it's the WORST yield
    # among 9 comparable local listings — a peripheral high-yield area where 5.5% is
    # actually mediocre. The area-relative gate must hold this at WATCH, not BUY.
    r = recommend(
        _base(
            value_gap_pct=0.20,
            net_yield=0.055,
            days_on_market=300,
            yield_percentile=0.0,
            yield_peers=9,
        )
    )
    assert r.verdict == "WATCH"


def test_buy_allowed_when_yield_is_best_in_area():
    # Same 5.5% net yield, but the best available among 9 local peers (a low-yield prime
    # area) — clears both the flat bar and the local-rank gate, so BUY still fires.
    r = recommend(
        _base(
            value_gap_pct=0.20,
            net_yield=0.055,
            days_on_market=300,
            yield_percentile=1.0,
            yield_peers=9,
        )
    )
    assert r.verdict == "BUY"


def test_buy_gate_falls_back_to_flat_bar_with_too_few_local_peers():
    # Below MIN_PEERS, relative_yield returns None — the local-rank gate must never block
    # (or require) a BUY for lack of data; flat-bar-only behavior, unchanged.
    r = recommend(
        _base(
            value_gap_pct=0.20,
            net_yield=0.06,
            days_on_market=300,
            yield_percentile=0.0,  # would fail the local-rank gate if it were consulted
            yield_peers=3,  # below MIN_PEERS=8
        )
    )
    assert r.verdict == "BUY"


def test_soft_gap_plus_imputed_yield_is_watch_not_buy():
    # Was BUY under the old strong>=2 bar (gap>=.10 + yield>=.045). Both signals are soft
    # (asking-based gap, area-imputed yield) and neither clears the wider BUY bar, so the
    # honest verdict is now WATCH — shortlist and verify, not a green light.
    r = recommend(_base(value_gap_pct=0.12, net_yield=0.05, days_on_market=30))
    assert r.verdict == "WATCH"


def test_imputed_yield_alone_without_value_gap_is_not_buy():
    # A high area-imputed yield with no confirmed discount to fair value is not enough to BUY.
    r = recommend(_base(value_gap_pct=None, net_yield=0.07, days_on_market=30))
    assert r.verdict == "WATCH"


def test_value_gap_alone_without_yield_is_not_buy():
    # A significant asking gap but only an ordinary yield stays WATCH — one soft signal only.
    r = recommend(_base(value_gap_pct=0.20, net_yield=0.04, days_on_market=30))
    assert r.verdict == "WATCH"


def test_ordinary_listing_is_watch_or_pass_not_hyped():
    r = recommend(_base(net_yield=0.038, value_gap_pct=None, days_on_market=20))
    assert r.verdict in {"WATCH", "PASS"}


def test_buy_bar_listing_held_at_watch_when_data_suspect():
    # Clears the BUY bar on the numbers, but self-inconsistent → capped at WATCH, said plainly.
    r = recommend(
        _base(
            value_gap_pct=0.20,
            net_yield=0.06,
            consistency_flags=["€545/m² is implausibly low for an apartment"],
        )
    )
    assert r.verdict == "WATCH"
    assert "verify" in r.headline.lower()


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
