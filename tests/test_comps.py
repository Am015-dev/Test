from __future__ import annotations

from scout.comps import find_comparables


def make_listing(
    id: int,
    price: int,
    area_m2: float,
    neighborhood: str | None = "Holargos",
    price_per_m2: float | None = None,
    gross_yield: float | None = None,
    excluded: bool = False,
    status: str = "active",
    url: str = "https://example.com",
    title: str = "Listing",
) -> dict:
    return {
        "id": id,
        "price": price,
        "area_m2": area_m2,
        "neighborhood": neighborhood,
        "price_per_m2": price_per_m2,
        "gross_yield": gross_yield,
        "excluded": excluded,
        "status": status,
        "url": url,
        "title": title,
    }


def make_target(
    id: int = 1,
    price: int = 200_000,
    area_m2: float = 80.0,
    neighborhood: str | None = "Holargos",
    price_per_m2: float | None = None,
) -> dict:
    return make_listing(
        id=id,
        price=price,
        area_m2=area_m2,
        neighborhood=neighborhood,
        price_per_m2=price_per_m2,
    )


def test_same_neighborhood_similar_listings_returned_and_sorted_by_ppm2_closeness():
    # target ppm2 = 200000/80 = 2500
    target = make_target()
    close = make_listing(id=2, price=205_000, area_m2=82.0)  # ppm2 ~2500.0
    medium = make_listing(id=3, price=220_000, area_m2=85.0)  # ppm2 ~2588.2
    far = make_listing(id=4, price=240_000, area_m2=90.0)  # ppm2 ~2666.7

    result = find_comparables(target, [far, close, medium])

    ids = [r["id"] for r in result]
    assert ids == [2, 3, 4]


def test_different_neighborhood_excluded():
    target = make_target(neighborhood="Holargos")
    other = make_listing(id=2, price=200_000, area_m2=80.0, neighborhood="Chalandri")

    result = find_comparables(target, [other])

    assert result == []


def test_neighborhood_match_is_case_insensitive_and_trimmed():
    target = make_target(neighborhood="Holargos")
    other = make_listing(id=2, price=200_000, area_m2=80.0, neighborhood="  HOLARGOS  ")

    result = find_comparables(target, [other])

    assert [r["id"] for r in result] == [2]


def test_target_itself_excluded():
    target = make_target(id=1)
    same_id = make_listing(id=1, price=200_000, area_m2=80.0)

    result = find_comparables(target, [same_id])

    assert result == []


def test_excluded_and_gone_listings_excluded():
    target = make_target()
    excluded_listing = make_listing(id=2, price=200_000, area_m2=80.0, excluded=True)
    gone_listing = make_listing(id=3, price=200_000, area_m2=80.0, status="gone")

    result = find_comparables(target, [excluded_listing, gone_listing])

    assert result == []


def test_area_tolerance_boundary():
    target = make_target(area_m2=80.0, price=200_000)  # 25% area tol -> [60, 100]
    at_boundary = make_listing(id=2, price=200_000, area_m2=100.0)  # exactly +25%
    over_boundary = make_listing(id=3, price=200_000, area_m2=100.01)  # just over +25%

    result = find_comparables(target, [at_boundary, over_boundary])

    assert [r["id"] for r in result] == [2]


def test_price_tolerance_boundary():
    target = make_target(area_m2=80.0, price=200_000)  # 30% price tol -> [140000, 260000]
    at_boundary = make_listing(id=2, price=260_000, area_m2=80.0)  # exactly +30%
    over_boundary = make_listing(id=3, price=260_001, area_m2=80.0)  # just over +30%

    result = find_comparables(target, [at_boundary, over_boundary])

    assert [r["id"] for r in result] == [2]


def test_ppm2_delta_pct_sign_correct_for_cheaper_comp():
    # target ppm2 = 200000/80 = 2500
    target = make_target(price=200_000, area_m2=80.0)
    cheaper = make_listing(id=2, price=180_000, area_m2=90.0)  # ppm2 = 2000 -> -20%
    pricier = make_listing(id=3, price=220_000, area_m2=85.0)  # ppm2 ~2588.2 -> +3.53%

    result = find_comparables(target, [cheaper, pricier])
    by_id = {r["id"]: r for r in result}

    assert by_id[2]["ppm2_delta_pct"] < 0
    assert by_id[2]["ppm2_delta_pct"] == ((2000.0 - 2500.0) / 2500.0 * 100)
    assert by_id[3]["ppm2_delta_pct"] > 0


def test_ppm2_falls_back_to_price_over_area_when_price_per_m2_missing():
    target = make_target(price=200_000, area_m2=80.0, price_per_m2=None)
    comp = make_listing(id=2, price=200_000, area_m2=80.0, price_per_m2=None)

    result = find_comparables(target, [comp])

    assert result[0]["ppm2_delta_pct"] == 0.0


def test_max_results_respected():
    target = make_target()
    listings = [
        make_listing(id=i, price=200_000 + i * 100, area_m2=80.0 + i * 0.1) for i in range(2, 12)
    ]

    result = find_comparables(target, listings, max_results=3)

    assert len(result) == 3


def test_fail_soft_on_target_with_no_neighborhood_returns_empty_list():
    target = make_target(neighborhood=None)
    comp = make_listing(id=2, price=200_000, area_m2=80.0)

    result = find_comparables(target, [comp])

    assert result == []


def test_fail_soft_on_target_with_no_positive_price_returns_empty_list():
    target = make_target(price=0)
    comp = make_listing(id=2, price=200_000, area_m2=80.0)

    assert find_comparables(target, [comp]) == []


def test_fail_soft_on_target_with_no_computable_area_returns_empty_list():
    target = make_target(area_m2=0.0)
    comp = make_listing(id=2, price=200_000, area_m2=80.0)

    assert find_comparables(target, [comp]) == []


def test_empty_listings_returns_empty_list():
    target = make_target()

    assert find_comparables(target, []) == []
