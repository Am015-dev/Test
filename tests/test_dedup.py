"""Cross-source deduplication tests."""

from __future__ import annotations

from scout.dedup import deduplicate

from .conftest import make_listing


def test_exact_same_source_id_collapses():
    a = make_listing(source="spitogatos", source_id="1", price=200_000)
    b = make_listing(source="spitogatos", source_id="1", price=190_000)  # re-post, newer
    groups = deduplicate([a, b])
    assert len(groups) == 1


def test_cross_source_match_merges():
    a = make_listing(
        source="spitogatos",
        source_id="1",
        price=200_000,
        area_m2=80.0,
        neighborhood="Ano Cholargos",
        title="Bright 2BR Ano Cholargos",
    )
    b = make_listing(
        source="xe",
        source_id="9",
        price=205_000,
        area_m2=81.0,
        neighborhood="Ano Cholargos",
        title="2 bedroom Ano Cholargos bright",
    )
    groups = deduplicate([a, b])
    assert len(groups) == 1
    # Cheaper one is canonical.
    assert groups[0].canonical.price == 200_000
    assert len(groups[0].duplicates) == 1


def test_different_area_does_not_merge():
    a = make_listing(source="spitogatos", source_id="1", area_m2=80.0)
    b = make_listing(source="xe", source_id="9", area_m2=120.0)
    groups = deduplicate([a, b])
    assert len(groups) == 2


def test_cross_source_match_merges_greek_neighborhoods():
    """Regression (P0-1): Greek location text must produce tokens so dedup can match."""
    a = make_listing(
        source="spitogatos",
        source_id="1",
        price=200_000,
        area_m2=80.0,
        neighborhood="Χολαργός (Τσακός)",
        title="Διαμέρισμα",
        address="Χολαργός (Τσακός)",
    )
    b = make_listing(
        source="xe",
        source_id="9",
        price=204_000,
        area_m2=81.0,
        neighborhood="Χολαργός (Τσακός)",
        title="Διαμέρισμα",
        address="Χολαργός (Τσακός)",
    )
    groups = deduplicate([a, b])
    assert len(groups) == 1


def test_same_source_similar_flats_do_not_merge():
    """Two distinct ads from the SAME source must not be fuzzy-merged away."""
    a = make_listing(
        source="xe",
        source_id="1",
        price=200_000,
        area_m2=80.0,
        neighborhood="Χολαργός (Τσακός)",
        address="Χολαργός (Τσακός)",
    )
    b = make_listing(
        source="xe",
        source_id="2",
        price=201_000,
        area_m2=80.0,
        neighborhood="Χολαργός (Τσακός)",
        address="Χολαργός (Τσακός)",
    )
    groups = deduplicate([a, b])
    assert len(groups) == 2


def test_different_location_does_not_merge():
    a = make_listing(
        source="spitogatos",
        source_id="1",
        area_m2=80.0,
        price=200_000,
        neighborhood="Ano Cholargos",
        title="flat in Ano Cholargos",
        address="Ano Cholargos",
    )
    b = make_listing(
        source="xe",
        source_id="9",
        area_m2=80.0,
        price=201_000,
        neighborhood="Faneromeni",
        title="flat in Faneromeni",
        address="Faneromeni",
    )
    groups = deduplicate([a, b])
    assert len(groups) == 2
