from __future__ import annotations

from scout.comps_panel import comparable_listings


def make_listing(
    id: int,
    price: int,
    area_m2: float,
    neighborhood: str | None = "Holargos",
    search_area: str | None = "Athens North",
    region: str | None = "North",
    price_per_m2: float | None = None,
    energy_class: str | None = "C",
    year_built: int | None = 2000,
    excluded: bool = False,
    status: str = "active",
) -> dict:
    return {
        "id": id,
        "price": price,
        "area_m2": area_m2,
        "neighborhood": neighborhood,
        "search_area": search_area,
        "region": region,
        "price_per_m2": price_per_m2,
        "energy_class": energy_class,
        "year_built": year_built,
        "excluded": excluded,
        "status": status,
    }


def make_target(
    id: int = 1,
    price: int = 200_000,
    area_m2: float = 80.0,
    neighborhood: str | None = "Holargos",
) -> dict:
    return make_listing(id=id, price=price, area_m2=area_m2, neighborhood=neighborhood)


def test_empty_pool_returns_empty():
    assert comparable_listings(make_target(), []) == []


def test_target_itself_excluded():
    target = make_target(id=1)
    same = make_listing(id=1, price=205_000, area_m2=82.0)
    other = make_listing(id=2, price=205_000, area_m2=82.0)

    result = comparable_listings(target, [same, other])

    ids = [r["id"] for r in result]
    assert 1 not in ids
    assert ids == [2]


def test_missing_price_per_m2_and_area_skipped():
    target = make_target()
    no_area = make_listing(id=2, price=200_000, area_m2=0.0)
    # No price_per_m2 and no derivable ppm2 (price missing/zero, area zero).
    no_ppm2 = {"id": 3, "area_m2": 0.0, "price": 0, "neighborhood": "Holargos"}
    ok = make_listing(id=4, price=205_000, area_m2=82.0)

    result = comparable_listings(target, [no_area, no_ppm2, ok])

    assert [r["id"] for r in result] == [4]


def test_same_neighborhood_preferred_over_same_region():
    target = make_target(neighborhood="Holargos")
    # Different neighborhood but same search_area/region — a very close size/price match.
    region_match = make_listing(
        id=2,
        price=200_000,
        area_m2=80.0,
        neighborhood="Chalandri",
        search_area="Athens North",
    )
    # Same neighborhood, a somewhat worse size/price match.
    neighborhood_match = make_listing(
        id=3,
        price=230_000,
        area_m2=92.0,
        neighborhood="Holargos",
    )

    result = comparable_listings(target, [region_match, neighborhood_match])

    # Same-neighborhood comp ranks first despite being a looser size/price match.
    assert [r["id"] for r in result] == [3, 2]


def test_different_region_ranks_last():
    target = make_target(neighborhood="Holargos")
    far = make_listing(
        id=2,
        price=200_000,
        area_m2=80.0,
        neighborhood="Glyfada",
        search_area="Athens South",
        region="South",
    )
    near = make_listing(id=3, price=230_000, area_m2=92.0, neighborhood="Holargos")

    result = comparable_listings(target, [far, near])

    assert [r["id"] for r in result] == [3, 2]


def test_closer_size_ranks_higher_within_same_neighborhood():
    # target ppm2 = 2500. Hold ppm2 constant so only size drives the ranking.
    target = make_target(price=200_000, area_m2=80.0)
    close = make_listing(id=2, price=205_000, area_m2=82.0, price_per_m2=2500.0)
    far = make_listing(id=3, price=250_000, area_m2=100.0, price_per_m2=2500.0)

    result = comparable_listings(target, [far, close])

    assert [r["id"] for r in result] == [2, 3]


def test_results_capped_at_n():
    target = make_target()
    pool = [make_listing(id=i, price=200_000 + i * 1_000, area_m2=80.0 + i) for i in range(2, 12)]

    result = comparable_listings(target, pool, n=3)

    assert len(result) == 3


def test_ppm2_delta_pct_computed_and_signed():
    # target ppm2 = 2500; comp ppm2 = 2800 -> +12% delta.
    target = make_target(price=200_000, area_m2=80.0)
    dearer = make_listing(id=2, price=224_000, area_m2=80.0, price_per_m2=2800.0)

    result = comparable_listings(target, [dearer])

    assert len(result) == 1
    assert result[0]["ppm2_delta_pct"] == 12.0


def test_inactive_and_excluded_listings_skipped():
    target = make_target()
    inactive = make_listing(id=2, price=205_000, area_m2=82.0, status="sold")
    excluded = make_listing(id=3, price=205_000, area_m2=82.0, excluded=True)
    active = make_listing(id=4, price=205_000, area_m2=82.0)

    result = comparable_listings(target, [inactive, excluded, active])

    assert [r["id"] for r in result] == [4]


def test_never_raises_on_garbage_fields():
    target = make_target()
    garbage = {"id": 2, "area_m2": "big", "price_per_m2": None, "neighborhood": 123}

    # Should simply skip the unusable candidate, not raise.
    assert comparable_listings(target, [garbage]) == []
