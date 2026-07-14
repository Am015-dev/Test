"""Internal-consistency 'verify this' flags."""

from scout.consistency import consistency_flags


def test_clean_listing_has_no_flags():
    assert (
        consistency_flags(
            {
                "price_per_m2": 3000,
                "area_m2": 75,
                "price": 225000,
                "energy_class": "B",
                "year_built": 2010,
            }
        )
        == []
    )


def test_low_ppm2_flagged():
    flags = consistency_flags({"price_per_m2": 424, "area_m2": 330, "price": 140000})
    assert any("low €/m²" in f for f in flags)


def test_high_ppm2_flagged():
    assert any("high €/m²" in f for f in consistency_flags({"price_per_m2": 15000, "area_m2": 40}))


def test_tiny_area_and_low_price_flagged():
    flags = consistency_flags({"area_m2": 10, "price": 15000, "price_per_m2": 1500})
    assert any("small floor area" in f for f in flags)
    assert any("low price" in f for f in flags)


def test_good_energy_on_old_unrenovated_build_flagged():
    flags = consistency_flags(
        {"price_per_m2": 3000, "energy_class": "A+", "year_built": 1965, "renovated_year": None}
    )
    assert any("top energy" in f for f in flags)


def test_good_energy_on_old_build_with_renovation_is_ok():
    flags = consistency_flags(
        {"price_per_m2": 3000, "energy_class": "A+", "year_built": 1965, "renovated_year": 2020}
    )
    assert not any("top energy" in f for f in flags)


def test_missing_fields_never_crash():
    assert consistency_flags({}) == []
