"""Tests for the negotiation-intelligence engine."""

from __future__ import annotations

from datetime import datetime, timedelta

from scout.negotiation import analyze

NOW = datetime(2026, 7, 12)


def _hist(*prices, start_days_ago=100):
    """Build a price_history [(t, price)] spread across the tracking window."""
    n = len(prices)
    return [
        (NOW - timedelta(days=start_days_ago - i * (start_days_ago // max(n, 1))), p)
        for i, p in enumerate(prices)
    ]


def test_fresh_listing_scores_low():
    r = analyze(
        price_history=[(NOW, 200_000)],
        first_seen=NOW,
        now=NOW,
        current_price=200_000,
        ppm2=2500,
        area_median_ppm2=2500,
    )
    assert r.score < 15
    assert not r.is_motivated
    assert r.num_cuts == 0


def test_stale_and_cut_listing_is_motivated():
    r = analyze(
        price_history=_hist(230_000, 215_000, 200_000, start_days_ago=110),
        first_seen=NOW - timedelta(days=110),
        now=NOW,
        current_price=200_000,
        ppm2=2500,
        area_median_ppm2=2500,
    )
    assert r.days_on_market == 110
    assert r.num_cuts == 2
    assert r.total_cut_pct > 0.12
    assert r.is_motivated
    assert any("On market" in x for x in r.reasons)
    assert any("Price cut" in x for x in r.reasons)


def test_overpriced_and_stale_adds_negotiation_room():
    stale_fair = analyze(
        price_history=[(NOW, 300_000)],
        first_seen=NOW - timedelta(days=100),
        now=NOW,
        current_price=300_000,
        ppm2=2500,
        area_median_ppm2=2500,
    )
    stale_over = analyze(
        price_history=[(NOW, 300_000)],
        first_seen=NOW - timedelta(days=100),
        now=NOW,
        current_price=300_000,
        ppm2=3000,  # 20% above area
        area_median_ppm2=2500,
    )
    assert stale_over.score > stale_fair.score
    assert any("Over-asked" in x for x in stale_over.reasons)


def test_relisted_and_private_raise_score():
    base = analyze(
        price_history=[(NOW, 200_000)],
        first_seen=NOW - timedelta(days=30),
        now=NOW,
        current_price=200_000,
        ppm2=2500,
        area_median_ppm2=2500,
    )
    flagged = analyze(
        price_history=[(NOW, 200_000)],
        first_seen=NOW - timedelta(days=30),
        now=NOW,
        current_price=200_000,
        ppm2=2500,
        area_median_ppm2=2500,
        relisted=True,
        is_private_seller=True,
    )
    assert flagged.score > base.score
    assert flagged.relisted
