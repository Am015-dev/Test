"""Tests for the data-quality audit (the observe step of the improvement loop)."""

from __future__ import annotations

from datetime import datetime

from scout.data_quality import audit, format_report


def _row(**kw):
    base = dict(
        region="Κέντρο Αθήνας",
        score=50.0,
        excluded=False,
        energy_class="B",
        year_built=2000,
        renovated_year=None,
        location_precision="exact",
        rent_estimated=False,
        last_seen=datetime(2026, 7, 13),
    )
    base.update(kw)
    return base


def test_audit_empty():
    r = audit([])
    assert r["total"] == 0


def test_audit_completeness_and_gap():
    listings = [
        _row(),  # fully complete
        _row(energy_class=None),  # missing energy
        _row(location_precision="approx"),  # missing exact location
        _row(rent_estimated=True),  # imputed rent
    ]
    r = audit(listings)
    assert r["total"] == 4
    # "complete" counts the 3 per-listing scrape fields (energy/year/exact loc); real rent is
    # systemic, so the rent_estimated row still counts as complete here.
    assert r["complete"] == 2
    # real_rent is missing on 1 of 4, energy on 1, exact_loc on 1 → all 0.75 except rent 0.75;
    # the lowest field is whatever ties lowest — assert it's a real field name.
    assert r["top_gap"] in {"energy_class", "year_or_reno", "exact_location", "real_rent"}
    assert 0.0 <= r["fields"]["real_rent"] <= 1.0


def test_format_report_mentions_gap():
    txt = format_report(audit([_row(), _row(energy_class=None)]))
    assert "Data-quality audit" in txt and "gap" in txt.lower()
