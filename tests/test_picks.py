from __future__ import annotations

from scout import market_intel, picks

from .test_ui_gauntlet import FIND, env, fresh, ok  # noqa: F401 — AppTest harness

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
    assert any(w.startswith("Σταθμός") for w in best.lines)
    assert any(w.startswith("Ενοίκιο (εκτίμηση) ~") for w in best.lines)
    # loosening the rules lets the old and the no-station flats in
    assert {3, 5} <= {p.listing["id"] for p in run(rows, max_age=None, near_rail=False, top=10)}


def test_built_this_year_is_flagged_and_numbers_are_greek():
    p = run([flat(1, 300_000, year=YEAR)])[0]
    assert any("παραδοθεί" in r for r in p.risks)
    assert "," in picks.gr_pct(p.gross) and "." not in picks.gr_pct(p.gross)


def test_checked_pages_rank_first_and_unchecked_are_flagged():
    rows = [flat(1, 270_000, m2=78), flat(2, 300_000, page_checked=True)]
    got = run(rows)
    assert [p.listing["id"] for p in got] == [2, 1]
    assert got[0].checked and not got[1].checked
    assert got[0].status.startswith("Ελέγχθηκε η περιγραφή")
    assert got[1].status == "Δεν έχει ελεγχθεί ακόμα"


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


def test_unchecked_never_in_top3_while_three_checked_qualify():
    # unchecked flats with far better yields (cheaper per m²) still rank below checked ones
    rows = [flat(i, 265_000 + i * 1000, m2=95, year=2019 + i) for i in range(1, 6)]
    rows += [flat(i, 290_000 + i * 1000, page_checked=True, year=2007 + i) for i in range(10, 13)]
    got = run(rows, top=10)
    assert [p.checked for p in got[:3]] == [True] * 3
    assert max(p.gross for p in got[3:]) > max(p.gross for p in got[:3])


def test_checked_date_is_on_the_status_line():
    from datetime import datetime

    p = run([flat(1, 300_000, page_checked=True, page_checked_at=datetime(2026, 10, 30))])[0]
    assert p.status == ("Ελέγχθηκε η περιγραφή (30/10/2026) — δεν αναφέρει κατασκευή σε εξέλιξη")


def test_few_photos_rank_below_real_photos_and_carry_the_risk_line():
    rows = [
        flat(1, 265_000, m2=95, few_photos=True, photo_count=1),  # best yield, 1 photo
        flat(2, 300_000, photo_count=14),
        flat(3, 310_000),  # photo count unknown (older rows): not penalised
    ]
    got = run(rows, top=10)
    assert [p.listing["id"] for p in got][-1] == 1
    assert got[-1].risks[0] == "Το πολύ 2 φωτογραφίες — συχνά μόνο ψηφιακή απεικόνιση ή λογότυπο"
    assert not any("φωτογραφ" in r for p in got[:2] for r in p.risks)
    # ...but a checked page still beats an unchecked one with real photos
    rows[0]["page_checked"] = True
    assert run(rows, top=10)[0].listing["id"] == 1


def test_description_excerpt_is_short_and_cut_at_a_word():
    long = "Πωλείται διαμέρισμα " + "πολύ φωτεινό με θέα " * 30
    p = run([flat(1, 300_000, description=long)])[0]
    assert p.excerpt.endswith("…") and len(p.excerpt) <= picks.EXCERPT_CHARS + 1
    assert long.startswith(p.excerpt[:-1])
    assert run([flat(1, 300_000)])[0].excerpt is None  # key absent: no expander
    assert picks.excerpt("  σύντομη \n περιγραφή ") == "σύντομη περιγραφή"


def test_relaxations_count_exactly_what_find_would_add():
    rows = [
        flat(1, 300_000, page_checked=True),  # qualifies now
        flat(2, 300_000, year=2013, page_checked=True),  # 13 years old
        flat(3, 280_000, year=2013),
        flat(4, 360_000),  # over 300k + 12 %, inside 330k ± 12 %
        flat(5, 290_000, hood="Γαλάτσι (Λαμπρινή)", page_checked=True),  # no station
        flat(6, 295_000, hood="Γαλάτσι (Λαμπρινή)", m2=90),
        flat(7, 900_000),  # never
    ]
    intel = market_intel.build(rows, YEAR)
    got = picks.relaxations(rows, intel, RENTS, 300_000, year=YEAR)
    by = {r.label: r for r in got}
    assert list(by) == ["Έως 15 ετών", "Προϋπολογισμός +10 %", "Χωρίς όρο σταθμού"]
    assert (by["Έως 15 ετών"].added, by["Έως 15 ετών"].added_checked) == (2, 1)
    assert by["Έως 15 ετών"].text == "Έως 15 ετών (+2, 1 με ελεγμένη περιγραφή)"
    assert by["Προϋπολογισμός +10 %"].changes == {"budget": 330_000}
    for r in got:  # the count is find() with that one rule changed, minus what qualifies now
        kw = {"max_age": 10, "near_rail": True, "budget": 300_000, **r.changes}
        budget = kw.pop("budget")
        wider = picks.find(rows, intel, RENTS, budget, year=YEAR, top=99, **kw)
        assert r.added == len({p.listing["id"] for p in wider} - {1})
    only = picks.relaxations(rows, intel, RENTS, 300_000, year=YEAR, checked_only=True)
    assert "Χωρίς όρο ελεγμένης περιγραφής" not in {
        r.label for r in only
    }  # flat 1 is checked: adds 0
    rows[0]["page_checked"] = False
    only = picks.relaxations(rows, intel, RENTS, 300_000, year=YEAR, checked_only=True)
    assert next(r for r in only if r.label == "Χωρίς όρο ελεγμένης περιγραφής").text == (
        "Χωρίς όρο ελεγμένης περιγραφής (+1)"
    )


def test_find_page_relaxation_tap_and_drop(env):  # noqa: F811 — the gauntlet's app fixture
    at = fresh(FIND)
    ok(at, "find")
    at.number_input(key="find_budget").set_value(230_000).run()  # seed: new flats in Galatsi
    text = " ".join(m.value for m in at.markdown)
    assert "## Βρες μου σπίτι" in text and "Καμία αγγελία" in text  # no station hoods in seed
    relax = [b for b in at.button if b.key and b.key.startswith("relax-")]
    no_rail = next(b for b in relax if b.label.startswith("Χωρίς όρο σταθμού (+"))
    added = int(no_rail.label.split("(+")[1].split(",")[0])
    no_rail.click().run()
    ok(at, "relaxation")
    assert at.toggle(key="find_rail").value is False
    text = " ".join(m.value for m in at.markdown)
    assert f"**{added}** αγγελίες" in text  # the tapped count is what the page now finds
    assert "Δεν έχει ελεγχθεί ακόμα" in text  # status on every card
    assert not at.metric  # no cramped metric rows on a phone
    assert any(e.label == "Πώς υπολογίζω" for e in at.expander)
    first = next(b for b in at.button if b.key and b.key.startswith("pick-no-"))
    first.click().run()
    ok(at, "drop")
    assert first.key not in {b.key for b in at.button if b.key}  # it left the list
    assert any(e.label == "Απέρριψες 1" for e in at.expander)
