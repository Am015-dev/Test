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


def test_checked_pages_rank_first_and_unchecked_are_flagged():
    rows = [flat(1, 270_000, m2=78), flat(2, 300_000, page_checked=True)]
    got = run(rows)
    assert [p.listing["id"] for p in got] == [2, 1]
    assert got[0].checked and not got[1].checked
    assert any("δεν έχει ελεγχθεί" in r for r in got[1].risks)


def test_approved_go_first_and_dropped_leave_so_the_next_moves_up():
    from scout.ui.find import arrange

    found = [
        picks.Pick(listing={"source": "xe", "source_id": str(i)}, rank_score=0, rent=0,
                   rent_low=0, rent_high=0, gross=0, net=0, offer=0, station=None)
        for i in range(5)
    ]  # fmt: skip
    shown, dropped = arrange(found, {"xe:0": "no", "xe:3": "ok"})
    assert [p.listing["source_id"] for p in shown] == ["3", "1", "2", "4"]
    assert [p.listing["source_id"] for p in dropped] == ["0"]


def test_review_verdicts_persist_and_approving_stars(monkeypatch):
    import requests

    from scout import shortlist as sl

    from .test_shortlist import FakeGist

    monkeypatch.setattr(requests, "request", FakeGist().request)
    monkeypatch.setattr(sl, "_gist_id", None)
    monkeypatch.setattr(sl, "_recent", None)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    sl.set_review("xe:1", "ok")
    sl.set_review("xe:2", "no")
    assert sl.review_map() == {"xe:1": "ok", "xe:2": "no"} and sl.watch_set() == {"xe:1"}
    sl.set_review("xe:2", None)
    assert sl.review_map() == {"xe:1": "ok"}
