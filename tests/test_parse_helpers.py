"""Unit tests for Greek-label parsing helpers."""

from __future__ import annotations

import pytest

from scout.collectors.parse_helpers import (
    parse_float,
    parse_floor,
    parse_int,
    parse_private_seller,
    parse_rent,
    source_id_from_url,
)


@pytest.mark.parametrize(
    "label,expected",
    [
        ("ισόγειο", 0.0),
        ("ΙΣΟΓΕΙΟ", 0.0),
        ("ημιυπόγειο", -1.0),
        ("υπόγειο", -1.0),
        ("ημιώροφος", 0.5),
        ("1ος", 1.0),
        ("3ος όροφος", 3.0),
        ("5ου", 5.0),
        # A combined maisonette label must keep the numeric level, not collapse to the
        # ground word (regression: "Ισόγειο,1ος" used to read 0.0).
        ("Ισόγειο,1ος", 1.0),
        (None, None),
        ("garbage", None),
    ],
)
def test_parse_floor(label, expected):
    assert parse_floor(label) == expected


def test_parse_rent_detects_amount():
    rented, rent = parse_rent("Ακίνητο μισθωμένο για 850 € τον μήνα")
    assert rented is True
    assert rent == 850


def test_parse_rent_no_rent():
    rented, rent = parse_rent("Φωτεινό διαμέρισμα, ανακαινισμένο")
    assert rented is False
    assert rent is None


def test_parse_rent_handles_thousands_separator():
    """Regression: a rent ≥ 1000 written with the Greek thousands dot must not be
    truncated ("1.200 €" -> 1200, not 200)."""
    rented, rent = parse_rent("Μισθωμένο, μηνιαίο μίσθωμα 1.200 €.")
    assert rented is True
    assert rent == 1200


def test_parse_rent_skips_sale_price_picks_rent():
    """Regression: with both a sale price and a rent present, the full sale price is
    out of the rent band and skipped, so the real rent is chosen (not a fragment)."""
    rented, rent = parse_rent("Τιμή πώλησης 92.500 €. Μισθωμένο, ενοίκιο 850 € μηνιαίως.")
    assert rented is True
    assert rent == 850


def test_parse_rent_yield_pitch_is_not_rented():
    """Regression: an 'απόδοση' (yield) sales pitch on a vacant flat must NOT flip
    is_currently_rented."""
    rented, rent = parse_rent("Άριστη επενδυτική ευκαιρία με απόδοση 6% ετησίως.")
    assert rented is False
    assert rent is None


def test_source_id_from_url_strips_tracking_query():
    """Regression: tracking params must not leak into the id, or the same listing looks
    new every crawl and dedup breaks."""
    assert (
        source_id_from_url(
            "https://www.spitogatos.gr/en/property/12345-flat?from=search&position=3"
        )
        == "12345-flat"
    )
    assert source_id_from_url("https://www.indomio.gr/p/999/") == "999"
    assert source_id_from_url(None) is None


def test_parse_private_seller():
    assert parse_private_seller("Πωλείται από ιδιώτη")
    assert parse_private_seller("όχι μεσίτες")
    assert not parse_private_seller("Μεσιτικό γραφείο ΑΒΓ")
    # Regression (P2-2): the adjective "ιδιωτικό" (private parking/pool) must NOT
    # be read as a private seller.
    assert not parse_private_seller("Διαμέρισμα με ιδιωτικό πάρκινγκ και ιδιωτική πισίνα")


def test_parse_int():
    assert parse_int("215.000 €") == 215000
    assert parse_int("1.250.000€") == 1250000
    assert parse_int(None) is None


def test_parse_float():
    assert parse_float("82,5 τμ") == 82.5
    assert parse_float("110 m²") == 110.0
    assert parse_float(None) is None
