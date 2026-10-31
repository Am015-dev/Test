from __future__ import annotations

from scout import market_intel as mi
from scout.nl_search import advise

YEAR = 2026


def flat(i, ppm, year=2010, m2=70, floor=2.0, hood="Χολαργός (Άνω)", **kw):
    return {
        "id": i,
        "price": round(ppm * m2),
        "price_per_m2": ppm,
        "area_m2": m2,
        "floor": floor,
        "year_built": year,
        "neighborhood": hood,
        **kw,
    }


def test_comps_compare_like_with_like_not_the_area_median():
    new = [flat(i, 5000, year=2024) for i in range(6)]
    old = [flat(10 + i, 2500, year=1970) for i in range(6)]
    target = flat(99, 4500, year=2023)
    c = mi.build([*new, *old, target], YEAR).comps(target)
    assert c["n"] == 6 and c["ppm"] == 5000  # only the new builds, not the 1970 blocks
    assert round(c["pct"], 2) == -0.10
    assert "έως 5 ετών" in c["label"] and "Χολαργός" in c["label"]


def test_comps_relax_floor_then_size_and_need_five():
    others = [flat(i, 3000, floor=5.0) for i in range(5)]
    target = flat(99, 3000, floor=1.0)
    c = mi.build([*others, target], YEAR).comps(target)
    assert c["n"] == 5 and "όροφος" not in c["label"] and "65–90" in c["label"]
    few = [flat(i, 3000) for i in range(4)]
    assert mi.build([*few, target], YEAR).comps(target) is None


def test_comps_skip_other_areas_suspect_and_unfinished():
    pool = [flat(i, 3000, year=2005 + i) for i in range(5)]
    noise = [
        flat(20, 9000, hood="Παπάγου (Σύνορα με Χολαργό)"),
        flat(21, 9000, is_suspect=True),
        flat(22, 9000, is_unfinished=True),
        flat(23, 9000, excluded=True),
    ]
    target = flat(99, 3300)
    c = mi.build([*pool, *noise, target], YEAR).comps(target)
    assert c["n"] == 5 and c["ppm"] == 3000


def test_twins_are_the_same_flat_from_other_agents():
    a = flat(1, 4000, m2=80)
    b = {**flat(2, 3900, m2=80), "price": 312_000}
    far = {**flat(3, 3000, m2=80), "price": 240_000}  # >10% apart: a different flat
    other_floor = flat(4, 4000, m2=80, floor=3.0)
    intel = mi.build([a, b, far, other_floor], YEAR)
    assert [t["id"] for t in intel.twins(a)] == [2]
    assert intel.twins(other_floor) == []


def test_age_table_and_comparable_value_drive_the_score():
    rows = [flat(i, 4800, year=2024) for i in range(5)] + [
        flat(10 + i, 3200, year=2000) for i in range(5)
    ]
    table = mi.build(rows, YEAR).age_table("Χολαργός")
    assert [r["band"] for r in table] == ["έως 5 ετών", "16–30 ετών"]
    d = {"score": 60, "year_built": 2010}
    assert advise(d, comp_pct=-0.20)["score"] > advise(d, comp_pct=0.15)["score"]


def test_houses_are_compared_with_houses_not_flats():
    flats = [flat(i, 4000, year=2015 + i % 5) for i in range(6)]
    houses = [
        {**flat(20 + i, 2400, m2=100 + 10 * i), "title": "Μονοκατοικία 160 τ.μ."} for i in range(5)
    ]
    house = {**flat(99, 2300), "title": "Μονοκατοικία 150 τ.μ."}
    c = mi.build([*flats, *houses, house], YEAR).comps(house)
    assert c["ppm"] == 2400 and "μονοκατοικίες" in c["label"]


def test_far_under_comparables_is_a_warning_not_a_bonus():
    d = {"score": 60, "year_built": 2010, "gross_yield": 0.09}
    normal = advise(d, comp_pct=-0.20)
    odd = advise(d, comp_pct=-0.50)
    assert odd["too_cheap"] and not normal["too_cheap"]
    assert odd["score"] < normal["score"]
