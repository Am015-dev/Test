"""Unit tests for Greek-label parsing helpers."""

from __future__ import annotations

import pytest

from scout.collectors.parse_helpers import (
    parse_float,
    parse_floor,
    parse_int,
    parse_private_seller,
    parse_rent,
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


def test_parse_private_seller():
    assert parse_private_seller("Πωλείται από ιδιώτη")
    assert parse_private_seller("όχι μεσίτες")
    assert not parse_private_seller("Μεσιτικό γραφείο ΑΒΓ")


def test_parse_int():
    assert parse_int("215.000 €") == 215000
    assert parse_int("1.250.000€") == 1250000
    assert parse_int(None) is None


def test_parse_float():
    assert parse_float("82,5 τμ") == 82.5
    assert parse_float("110 m²") == 110.0
    assert parse_float(None) is None
