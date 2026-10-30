"""Tests for the deal advisor — recommended offer + thesis."""

from __future__ import annotations

from scout.deal import advise


def test_no_asking_price_returns_none():
    assert advise(asking=None) is None
    assert advise(asking=0) is None


def test_fresh_fair_listing_offers_near_asking():
    d = advise(asking=200_000, negotiation_score=0.0, days_on_market=3)
    assert d is not None
    # No motivation, no cuts → the offer barely moves off asking.
    assert d.discount_pct < 0.02
    assert "κοντά στη ζητούμενη" in d.thesis


def test_motivated_stale_listing_gets_a_real_discount():
    d = advise(
        asking=300_000,
        negotiation_score=80.0,
        days_on_market=180,
        num_cuts=2,
    )
    assert d is not None
    assert d.suggested_offer < 300_000
    assert d.discount_pct > 0.05  # meaningful room
    assert any("μέρες στην αγορά" in x for x in d.drivers)
    assert any("μειώσει την τιμή" in x for x in d.drivers)


def test_confident_fair_value_caps_the_offer():
    # Confidently worth 250k but asked at 300k → never recommend above fair value.
    d = advise(
        asking=300_000,
        predicted_price=250_000,
        value_confident=True,
        negotiation_score=90.0,
        days_on_market=200,
    )
    assert d is not None
    assert d.suggested_offer <= 250_000
    assert any("πάνω από την εκτιμώμενη αξία" in x for x in d.drivers)


def test_low_confidence_fair_value_is_ignored_for_the_number():
    # A low-confidence estimate must not cap the offer — the number is motivation-only.
    d = advise(
        asking=300_000,
        predicted_price=250_000,
        value_confident=False,
        negotiation_score=0.0,
        days_on_market=1,
    )
    assert d is not None
    assert d.suggested_offer > 250_000  # not anchored to the untrusted fair value
    assert not any("εκτιμώμενη αξία" in x for x in d.drivers)


def test_offer_is_rounded():
    d = advise(asking=197_314, negotiation_score=50.0, days_on_market=60)
    assert d is not None
    assert d.suggested_offer % 500 == 0
