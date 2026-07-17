"""Tests for datePosted extraction and its effect on the negotiation signal.

These prove the "true market age from day one" improvement: a listing's own posting
date, parsed from the detail page, makes days-on-market real on first sight — no daily
tracking required.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from scout.collectors.xe import parse_listed_date
from scout.negotiation import analyze


def test_parse_listed_date_with_trailing_z():
    html = '<script>{"@type":"RealEstateListing","datePosted":"2026-05-29T09:24:18Z"}</script>'
    d = parse_listed_date(html)
    assert d == datetime(2026, 5, 29, 9, 24, 18)


def test_parse_listed_date_without_offset():
    html = '{"datePosted":"2026-07-01T10:00:00"}'
    d = parse_listed_date(html)
    assert d == datetime(2026, 7, 1, 10, 0, 0)


def test_parse_listed_date_absent_returns_none():
    assert parse_listed_date("<html>no date here</html>") is None
    assert parse_listed_date('{"datePosted":"not-a-date"}') is None


def test_posting_date_gives_true_market_age_on_first_sight():
    now = datetime(2026, 7, 12)
    # First seen TODAY (freshly discovered) but the portal says it was posted 150 days ago.
    fresh = analyze(
        price_history=[(now, 250_000)],
        first_seen=now,
        now=now,
        current_price=250_000,
        ppm2=2500,
        area_median_ppm2=2500,
    )
    with_post_date = analyze(
        price_history=[(now, 250_000)],
        first_seen=now,
        now=now,
        current_price=250_000,
        ppm2=2500,
        area_median_ppm2=2500,
        listed_date=now - timedelta(days=150),
    )
    assert fresh.days_on_market == 0
    assert with_post_date.days_on_market == 150
    # The real market age lifts the negotiation score immediately (stale seller) and
    # surfaces the actionable reason — on the very first sight, no daily tracking needed.
    assert with_post_date.score > fresh.score
    assert any("On market" in r for r in with_post_date.reasons)
