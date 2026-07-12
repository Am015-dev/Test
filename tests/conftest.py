"""Shared fixtures and helpers for tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from scout.config import Strategy
from scout.models import Listing


def make_listing(**overrides) -> Listing:
    """Build a valid Listing with sensible defaults, overridable per test."""
    base = dict(
        source="spitogatos",
        source_id="0001",
        url="https://example.gr/0001",
        title="2-bedroom flat in Ano Cholargos",
        price=200_000,
        area_m2=80.0,
        rooms=3,
        bedrooms=2,
        floor=2.0,
        neighborhood="Ano Cholargos",
        address="Ano Cholargos, Athens",
        lat=38.0,
        lng=23.8,
        metro_distance_m=400,
        nearest_metro="Holargos",
        location_precision="exact",
        price_per_m2=2500.0,
        est_monthly_rent=900,
        rent_estimated=False,
        gross_yield=0.054,
        first_seen=datetime(2026, 6, 1),
        last_seen=datetime(2026, 6, 19),
    )
    base.update(overrides)
    return Listing(**base)


@pytest.fixture
def strategy() -> Strategy:
    return Strategy()
