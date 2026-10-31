from __future__ import annotations

from scout import market_intel, picks

YEAR = 2026
RENTS = [
    {"neighborhood": "Νέα Ιωνία (Περισσός)", "rent_per_m2": 11.0, "samples": 20},
    {"neighborhood": "Γαλάτσι (Λαμπρινή)", "rent_per_m2": 12.0, "samples": 20},
]


def flat(i, price, hood="Νέα Ιωνία (Περισσός)", year=2024, m2=80, **kw):
    return {
        "id": i,
        "url": f"https://x/{i}",
        "title": f"Διαμέρισμα {m2} τ.μ.",
        "price": price,
        "area_m2": m2,
        "price_per_m2": price / m2,
        "floor": 2.0,
        "year_built": year,
        "neighborhood": hood,
        "is_fresh": True,
        **kw,
    }


def run(rows, **kw):
    return picks.find(rows, market_intel.build(rows, YEAR), RENTS, 300_000, year=YEAR, **kw)


def test_station_is_read_from_the_neighbourhood_name():
    assert picks.station({"neighborhood": "Αθήνα (Αμπελόκηποι)"}).startswith("Μετρό Αμπελόκηποι")
    assert picks.station({"neighborhood": "Γαλάτσι (Λαμπρινή)"}) is None


def test_only_new_finished_near_rail_in_budget_and_best_yield_first():
    rows = [
        flat(1, 300_000),  # 80 m² → ~11 €/m² ×1.1 new
        flat(2, 270_000, m2=78, year=2023),  # cheaper per m² → higher yield
        flat(3, 280_000, year=1975),  # old
        flat(4, 290_000, is_unfinished=True),  # shell
        flat(5, 290_000, hood="Γαλάτσι (Λαμπρινή)"),  # no station
        flat(6, 420_000),  # over budget
        flat(7, 295_000, floor=0.0),  # ground floor
    ]
    got = [p.listing["id"] for p in run(rows)]
    assert got == [2, 1]
    best = run(rows)[0]
    assert 0.03 < best.gross < 0.06 and best.net < best.gross
    assert best.rent_low < best.rent < best.rent_high and best.offer < 270_000
    assert any("Σταθμός" in w for w in best.why) and any("Απόδοση" in w for w in best.why)
    # loosening the rules lets the old and the no-station flats in
    assert {3, 5} <= {p.listing["id"] for p in run(rows, new_only=False, near_rail=False, top=10)}


def test_built_this_year_is_flagged_and_numbers_are_greek():
    p = run([flat(1, 300_000, year=YEAR)])[0]
    assert any("παραδοθεί" in r for r in p.risks)
    assert "," in picks.gr_pct(p.gross) and "." not in picks.gr_pct(p.gross)
