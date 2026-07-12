"""Tests for the Athens regional grouping."""

from __future__ import annotations

from scout.regions import REGIONS, all_areas, region_of


def test_known_areas_map_to_expected_regions():
    assert region_of("Cholargos") == "Βόρεια Προάστια"
    assert region_of("Koukaki") == "Κέντρο Αθήνας"
    assert region_of("Glyfada") == "Νότια Προάστια"
    assert region_of("Aigaleo") == "Δυτικά Προάστια"
    assert region_of("Piraeus") == "Πειραιάς"


def test_unknown_or_missing_area_returns_none():
    assert region_of("Atlantis") is None
    assert region_of(None) is None


def test_every_area_is_unique_and_reachable():
    areas = all_areas()
    assert len(areas) == len(set(areas))  # no municipality in two regions
    # Every strategy area resolves back to exactly one region.
    for a in areas:
        assert region_of(a) in REGIONS
