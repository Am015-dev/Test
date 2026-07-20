"""Rent honesty: a rent is REAL only when the listing states its OWN rent.

An area/neighbourhood comp median is a fine ESTIMATE, but it must never brand the yield
as measured — no matter how many comps back it. Regression for the "real_rent: 100%"
overclaim where any existing area comp flipped ``rent_estimated`` to False.
"""

from __future__ import annotations

from scout.enrich import enrich_listing

from .conftest import make_listing


def test_area_comp_without_own_rent_is_estimated():
    """No own listed_rent → estimated, even when a real area-comp median is applied."""
    lst = make_listing(listed_rent=None, rent_estimated=False)
    enriched = enrich_listing(lst, median_rent_per_m2=12.0, use_network=False)
    assert enriched.rent_estimated is True
    # The comp still drives the yield MATH (estimate is fine as an estimate).
    assert enriched.est_monthly_rent == round(12.0 * 80.0)


def test_own_listed_rent_is_real():
    """Listing states its own rent → measured, not estimated."""
    lst = make_listing(listed_rent=900, rent_estimated=True)
    enriched = enrich_listing(lst, median_rent_per_m2=12.0, use_network=False)
    assert enriched.rent_estimated is False
    assert enriched.est_monthly_rent == 900


def test_no_rent_at_all_is_estimated():
    """No own rent and no comp (baseline only) → still estimated."""
    lst = make_listing(listed_rent=None, rent_estimated=False)
    enriched = enrich_listing(lst, median_rent_per_m2=None, use_network=False)
    assert enriched.rent_estimated is True
