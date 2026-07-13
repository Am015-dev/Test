"""Tests for saved searches, negotiation playbook, and the score-known breakdown."""

from __future__ import annotations

from scout.saved_search import SavedSearch, matches


def _l(**kw):
    base = dict(region="Κέντρο Αθήνας", price=200_000, net_yield=0.04, deal_grade="B", score=50)
    base.update(kw)
    return base


def test_saved_search_region_and_price_filter():
    s = SavedSearch(id=None, name="m", regions=["Κέντρο Αθήνας"], max_price=250_000)
    assert matches(s, _l())
    assert not matches(s, _l(region="Πειραιάς"))
    assert not matches(s, _l(price=300_000))


def test_saved_search_grade_floor():
    s = SavedSearch(id=None, name="m", regions=[], min_grade="B")
    assert matches(s, _l(deal_grade="A"))
    assert matches(s, _l(deal_grade="B"))
    assert not matches(s, _l(deal_grade="C"))


def test_saved_search_yield_floor():
    s = SavedSearch(id=None, name="m", regions=[], min_net_yield=0.05)
    assert not matches(s, _l(net_yield=0.04))
    assert matches(s, _l(net_yield=0.06))


def test_negotiation_playbook():
    from datetime import datetime, timedelta

    from scout.negotiation import analyze, playbook

    now = datetime(2026, 7, 13)
    r = analyze(
        price_history=[(now, 200_000)],
        first_seen=now,
        now=now,
        current_price=200_000,
        ppm2=2500,
        area_median_ppm2=2500,
        listed_date=now - timedelta(days=200),
    )
    tips = playbook(r, suggested_offer=180_000)
    assert tips and any("market" in t.lower() for t in tips)


def test_score_exposes_known_signals(strategy):
    from scout.scoring import MarketStats, NeighborhoodStats, score

    from .conftest import make_listing

    stats = MarketStats(
        by_neighborhood={
            "Ano Cholargos": NeighborhoodStats(median_price_per_m2=2800, price_sample_count=8)
        },
        overall_median_price_per_m2=2800,
    )
    # A card-only listing: energy/year unknown → those signals flagged not-known.
    s = score(make_listing(energy_class=None, year_built=None), stats, strategy)
    assert s.signal_known["energy_class"] is False
    assert s.signal_known["newness"] is False
    assert s.signal_known["is_private_seller"] is True  # always evaluable
