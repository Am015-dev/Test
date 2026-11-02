"""Favourites at a glance: ranked by score, one line each, the price linking to the ad."""

from __future__ import annotations

from scout.ui import buyer


def test_shortlist_lines_rank_link_and_numbers():
    a = {"price": 220_000, "area_m2": 50.0, "url": "https://x/a", "neighborhood": "Αθήνα (Κυψέλη)",
         "est_monthly_rent": 580}  # fmt: skip
    b = {"price": 180_000, "area_m2": 60.0, "url": "https://x/b", "neighborhood": "Χολαργός"}
    text = buyer.shortlist_lines([(a, {"score": 61}), (b, {"score": 40})])
    first, second = text.split("  \n")
    assert first.startswith("1. [220.000 €](https://x/a) · 50 τ.μ. · 3,2 % · Βαθμολογία 61")
    assert first.endswith("Αθήνα (Κυψέλη)")
    assert second.startswith("2. [180.000 €](https://x/b) · 60 τ.μ.")
    assert "Βαθμολογία 40" in second
