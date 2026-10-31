"""«Να νοικιάσω»: step 0, the five rent steps, ranking, relaxations and the assistant facts.

Rental dicts follow contract C1 (``queries.load_rent_listings``: the sale keys with
``price`` = monthly rent, plus ``rent_per_m2``, ``furnished``, ``available_from``,
``days_on_market`` / ``dom_basis`` / ``relisted_on``, ``is_fresh``, ``page_checked``).
Until W16's loader lands the AppTest patches it in with ``RENTALS``.
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest

from scout import picks_rent
from scout.ui import rent_guide

from .test_ui_gauntlet import FIND, env, fresh, goto, ok  # noqa: F401 — AppTest harness

YEAR = 2026


def rental(i, price, m2, hood="Χαλάνδρι (Κέντρο)", **kw):
    return {
        "id": 10_000 + i,
        "listing_type": "rent",
        "source": "xe",
        "source_id": f"r-{i}",
        "url": f"https://www.xe.gr/property/d/r/{i}",
        "title": f"Διαμέρισμα {m2} τ.μ.",
        "price": price,
        "area_m2": m2,
        "price_per_m2": price / m2,
        "rent_per_m2": price / m2,
        "floor": 2.0,
        "year_built": 2005,
        "bedrooms": 2,
        "neighborhood": hood,
        "is_fresh": True,
        "page_checked": False,
        "furnished": None,
        "available_from": None,
        "days_on_market": 20,
        "dom_basis": "listed",
        "relisted_on": None,
        "is_private_seller": False,
        "energy_class": "B",
        **kw,
    }


def _fixture() -> list[dict]:
    rows = []
    hoods = ["Χαλάνδρι (Κέντρο)", "Γαλάτσι (Λαμπρινή)", "Νέα Ιωνία (Περισσός)"]
    for i in range(36):
        m2 = 50 + (i % 6) * 10  # 50…100
        per = 10 + (i % 5) * 0.5 + (hoods.index(hoods[i % 3]) * 0.5)
        rows.append(
            rental(
                i,
                round(per * m2 / 10) * 10,
                m2,
                hood=hoods[i % 3],
                bedrooms=1 + i % 3,
                year_built=1990 + i % 35,
                furnished=True if i % 4 == 0 else None,
                available_from=date(2026, 12, 1) if i % 7 == 0 else None,
                days_on_market=3 + i,
                is_private_seller=bool(i % 2),
                energy_class=None if i % 5 == 0 else "C",
                relisted_on=date(2026, 10, 20) if i % 9 == 0 else None,
            )
        )
    return rows


RENTALS = _fixture()


@pytest.fixture
def rent_env(env, monkeypatch):  # noqa: F811
    from scout.ui import assistant, queries

    monkeypatch.setattr(queries, "load_rent_listings", lambda: RENTALS, raising=False)
    calls: list[dict] = []

    class Messages:
        def create(self, **req):
            calls.append(req)
            text = "Το #1 έχει το χαμηλότερο ενοίκιο ανά τ.μ. Ρώτα εγγύηση και κοινόχρηστα."
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn"
            )

    monkeypatch.setattr(assistant, "_client", lambda: SimpleNamespace(messages=Messages()))
    return calls


def _text(at) -> str:
    return " ".join(m.value for m in at.markdown)


def _cards(at) -> list[str]:
    return [b.key for b in at.button if (b.key or "").startswith("rent-det-")]


def walk_rent(at, budget="guide-rb800", beds="2", where="best", age="any", furnished=False):
    assert "### Τι ψάχνεις;" in _text(at)
    at.button(key="guide-mode-rent").click().run()
    ok(at, "mode")
    assert at.session_state["guide"]["mode"] == "rent"
    assert "Βήμα 1 από 5" in _text(at) and "### Πόσο τον μήνα;" in _text(at)
    at.button(key=budget).click().run()
    ok(at, "step 1")
    assert "Βήμα 2 από 5" in _text(at) and "### Πόσα υπνοδωμάτια;" in _text(at)
    at.button(key=f"guide-rbd-{beds}").click().run()
    ok(at, "step 2")
    assert "Βήμα 3 από 5" in _text(at) and "### Πού;" in _text(at)
    at.button(key=f"guide-rw-{where}").click().run()
    ok(at, "step 3")
    assert "Βήμα 4 από 5" in _text(at) and "### Τι σπίτι;" in _text(at)
    if furnished:
        at.toggle(key="rent_furn").set_value(True).run()
    at.button_group(key="rent_age").set_value(age).run()
    at.button(key="guide-rshow").click().run()
    ok(at, "step 4")
    assert "Βήμα" not in _text(at) and "### Η πρότασή μου" in _text(at)
    return at


def test_rent_flow_end_to_end(rent_env):
    at = walk_rent(fresh(FIND), budget="guide-rb1000", beds="any")
    assert list(at.button_group(key="rent_chips").options) == [
        "να νοικιάσω",
        "έως 1.000 €/μήνα",
        "υπν. αδιάφορο",
        "όλες οι περιοχές",
        "οποιαδήποτε ηλικία",
    ]
    text = _text(at)
    total = int(re.search(r"\*\*(\d+)\*\* αγγελίες ενοικίασης έως 1\.100 €/μήνα", text).group(1))
    assert total == len(picks_rent.find(RENTALS, 1000, top=10**6))
    assert total > 10 and "Σου προτείνω " in text
    # C17: exactly two buttons per card, no «Εγκρίνω» / «Δεν μου κάνει» in the guide
    assert not any(b.label in ("Εγκρίνω", "Δεν μου κάνει") for b in at.button)
    assert "από τα διπλανά (" in text and "Ιδιώτης ή μεσιτικό" in text
    assert "/μήνα" in text and "Από πού βγαίνουν" in text
    assert "Δεν έχει ελεγχθεί ακόμα" not in text  # no rental page is read: no page-check chip
    assert 'hg-st-neu">Επιπλωμένο<' in text and 'hg-st-neu">Διαθέσιμο από 01/12<' in text
    assert "Ενεργειακή κλάση" in text and "Φρεσκάδα" in text and "Τιμή έναντι παρόμοιων" in text
    assert "απόδοση" not in text.lower()  # no yield talk for renters
    first = _cards(at)
    assert len(first) == 10
    at.button(key="guide-rmore-btn").click().run()
    ok(at, "more")
    assert len([b for b in at.button if (b.key or "").startswith("rent-star-")]) == min(20, total)
    # the assistant note rendered from facts["listings"] with renter rules
    assert "**Σημείωμα**" in _text(at) and rent_env
    req = rent_env[0]
    assert "απόδοση" in req["system"] and "εγγύηση" in req["system"]  # «Δεν μιλάς για απόδοση»
    assert '"mode": "rent"' in req["messages"][0]["content"]
    # a «Δεν μου κάνει» verdict (saved-searches page) drops the card and the next moves up
    from scout import shortlist

    lid = int(first[0].removeprefix("rent-det-"))
    d = next(x for x in RENTALS if x["id"] == lid)
    at.session_state["pick_review"] = {shortlist.lkey(d): "no"}
    at.run()
    ok(at, "drop")
    assert first[0] not in _cards(at) and any(e.label == "Απέρριψες 1" for e in at.expander)
    # details open inline
    det = next(b for b in at.button if (b.key or "").startswith("rent-det-"))
    det.click().run()
    ok(at, "details")
    assert "Ρώτα τον ιδιοκτήτη" in " ".join(c.value for c in at.caption)
    # a starred rental is on «Αγαπημένα», under «Ενοίκια»
    star = next(b for b in at.button if (b.key or "").startswith("rent-star-"))
    star.click().run()
    ok(at, "star")
    goto(at, "Αγαπημένα")
    ok(at, "favourites")
    assert "## Αγαπημένα (1)" in _text(at) and "### Ενοίκια" in _text(at)
    assert any((b.key or "").startswith("wrent-star-") for b in at.button)
    goto(at, "Οδηγός")
    # a chip reopens its question; the mode chip reopens step 0
    at.button_group(key="rent_chips").set_value("υπν. αδιάφορο").run()
    assert "Βήμα 2 από 5" in _text(at)
    at.button(key="guide-rbd-2").click().run()
    assert at.session_state["guide"]["rent"]["step"] == 3
    at.button(key="guide-back").click().run()
    assert "Βήμα 2 από 5" in _text(at)
    at.button(key="guide-back").click().run()
    at.button(key="guide-back").click().run()
    assert "### Τι ψάχνεις;" in _text(at) and at.session_state["guide"]["mode"] is None
    # switching to buy keeps the rent answers, and back again
    at.button(key="guide-mode-buy").click().run()
    assert "Βήμα 1 από 5" in _text(at) and "Πόσα θες να βάλεις;" in _text(at)
    at.button(key="guide-back").click().run()
    at.button(key="guide-mode-rent").click().run()
    assert at.session_state["guide"]["rent"]["budget"] == 1000
    ok(at, "switch")


def test_relaxation_has_exact_counts(rent_env):
    at = walk_rent(fresh(FIND), budget="guide-rb800", beds="any", where="rail", age="10")
    relax = [b for b in at.button if (b.key or "").startswith("rent-relax-")]
    assert relax
    first = relax[0]
    added = int(first.label.split("(+")[1].rstrip(")"))
    # the exact matches before (C7: near matches follow them and are not counted here)
    m0 = re.search(r"\*\*(\d+)\*\* αγγελί\w+ ενοικίασης", _text(at))
    before = int(m0.group(1)) if m0 else 0
    first.click().run()
    ok(at, "relax")
    m = re.search(r"\*\*(\d+)\*\* αγγελίες ενοικίασης", _text(at))
    assert m and int(m.group(1)) == before + added


def test_page_says_rents_are_coming_without_the_loader(env, monkeypatch):  # noqa: F811
    from scout.ui import queries

    monkeypatch.delattr(queries, "load_rent_listings", raising=False)
    at = fresh(FIND)
    ok(at, "no loader")
    rent = at.button(key="guide-mode-rent")
    assert rent.disabled and any(rent_guide.SOON in c.value for c in at.caption)
    assert "### Τι ψάχνεις;" in _text(at)


def test_page_says_no_rentals_yet_on_the_real_loader(env):  # noqa: F811
    from scout.ui import queries

    assert queries.load_rent_listings() == []  # the seeded DB has sales only
    at = fresh(FIND)
    ok(at, "empty")
    assert at.button(key="guide-mode-rent").disabled
    assert any(rent_guide.SOON in c.value for c in at.caption)
    assert not at.button(key="guide-mode-buy").disabled


def test_a_saved_rent_mode_without_rentals_returns_to_step_zero(env):  # noqa: F811
    """A profile that chose «Να νοικιάσω» before the first weekly run with rentals must not
    open on an empty rent flow: the guide resets the mode and shows step 0."""
    at = fresh(FIND)
    at.session_state["guide"] = {**guide_defaults(), "mode": "rent"}
    at.run()
    ok(at, "stranded")
    assert "### Τι ψάχνεις;" in _text(at) and "Βήμα" not in _text(at)
    assert at.session_state["guide"]["mode"] is None


def guide_defaults() -> dict:
    from scout.ui import guide

    return dict(guide.DEFAULTS)


def test_mode_is_saved_in_the_profile_store(monkeypatch):
    import sys
    import types

    import scout.ui
    from scout.ui import guide

    class Store:
        data: dict = {}

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

    store = Store()
    acc = types.ModuleType("scout.ui.account")
    acc.storage = lambda: store
    monkeypatch.setitem(sys.modules, "scout.ui.account", acc)
    monkeypatch.setattr(scout.ui, "account", acc, raising=False)
    guide._save({**guide.DEFAULTS, "mode": "rent"})
    assert store.data["guide"]["mode"] == "rent"


# ---- engine --------------------------------------------------------------------------------


def test_rank_by_value_against_the_neighbourhood_then_freshness():
    hood = [rental(i, 800, 80, days_on_market=10) for i in range(6)]  # 10 €/τ.μ. ×6
    cheap = rental(50, 720, 80, days_on_market=40)  # 9 €/τ.μ. → 10 % under
    cheap_fresh = rental(51, 720, 80, days_on_market=2)  # same value, fresher
    bait = rental(52, 400, 80)  # 5 €/τ.μ. → 50 % under: a warning, sorted after
    over = rental(53, 1120, 80)  # over the 1.000 × 1,10 band
    rows = [*hood, cheap, cheap_fresh, bait, over]
    got = picks_rent.find(rows, 1000, top=50)
    ids = [p.listing["id"] for p in got]
    assert ids[:2] == [10_051, 10_050] and ids[-1] == 10_052 and 10_053 not in ids
    p = got[0]
    assert p.comps_n == 9 and p.comps_where == "Χαλάνδρι (Κέντρο)"  # the others in the hood
    assert p.vs_area_pct == pytest.approx(-0.1) and p.comps_line == "Παρόμοια ενοίκια: 10 % κάτω"
    assert [k for k, _ in p.checks] == [
        "Τιμή έναντι παρόμοιων",
        "Φρεσκάδα",
        "Ιδιώτης ή μεσιτικό",
        "Ενεργειακή κλάση",
    ]
    assert dict(p.checks)["Φρεσκάδα"] == "νέα αγγελία (2 μέρες)"
    assert dict(p.checks)["Τιμή έναντι παρόμοιων"] == (
        "9,0 €/τ.μ. τον μήνα. Τα διπλανά ζητούν συνήθως 10,0 €/τ.μ. (9 αγγελίες, Χαλάνδρι (Κέντρο))"
    )
    assert picks_rent.fresh_verdict({"days_on_market": 75}) == (
        "75 μέρες στην αγορά. Ρώτα γιατί δεν έχει νοικιαστεί ακόμα"
    )
    assert got[-1].too_cheap and got[-1].risks[0].startswith("Πολύ κάτω από τα παρόμοια")
    # within the band but above the budget: said so
    near = picks_rent.find([*hood, rental(60, 1050, 100)], 1000, top=50)
    assert any(r == "50 € πάνω από το ποσό σου." for p in near for r in p.risks)


def test_filters_and_area_fallback():
    rows = [rental(i, 900, 90, hood="Γαλάτσι (Λαμπρινή)") for i in range(3)]
    rows += [rental(10 + i, 900, 90, hood="Γαλάτσι (Κέντρο)") for i in range(3)]
    one = rental(99, 800, 90, hood="Γαλάτσι (Λαμπρινή)", furnished=True, bedrooms=3)
    rows.append(one)
    p = next(p for p in picks_rent.find(rows, 1000, top=50) if p.listing is one)
    assert p.comps_where == "Γαλάτσι" and p.comps_n == 6  # 3 in the hood < 5: the area
    assert [x.listing for x in picks_rent.find(rows, 1000, furnished=True)] == [one]
    assert [x.listing for x in picks_rent.find(rows, 1000, bedrooms=3)] == [one]
    assert picks_rent.find(rows, 1000, near_rail=True) == []
    assert picks_rent.find(rows, 1000, areas=["Χαλάνδρι"]) == []
    assert len(picks_rent.find(rows, 1000, max_age=10, year=YEAR)) == 0  # all built 2005
    assert len(picks_rent.find(rows, 1000, max_age=25, year=YEAR)) == 7


def test_relaxations_count_exactly():
    rows = [rental(i, 900, 90) for i in range(6)]
    rows += [rental(10, 1050, 90), rental(11, 1060, 90)]  # need budget +10 %
    rows += [rental(20, 800, 90, furnished=True)]
    rows += [rental(30, 850, 90, year_built=2022), rental(31, 850, 90, year_built=2020)]
    base = picks_rent.find(rows, 900, furnished=True, max_age=10, year=YEAR, top=50)
    assert base == []
    got = picks_rent.relaxations(rows, 900, furnished=True, max_age=10, year=YEAR)
    texts = {r.label: r for r in got}
    assert set(texts) == {"Και χωρίς έπιπλα"}  # each alone: only this one adds
    assert texts["Και χωρίς έπιπλα"].added == 2 and texts["Και χωρίς έπιπλα"].text.endswith("(+2)")
    got = picks_rent.relaxations(rows, 900, year=YEAR)
    assert [(r.label, r.added) for r in got] == [("Ποσό +10 %", 2)]  # band 990 → 1.089


def test_rent_flow_on_the_real_loader(env):  # noqa: F811
    """No patch: rentals stored in the seeded DB come through ``queries.load_rent_listings``."""
    from scout.db import session_scope, upsert_listing_with_history

    from .conftest import make_listing

    with session_scope() as session:
        for i in range(12):
            m2 = 60 + i * 3
            upsert_listing_with_history(
                session,
                make_listing(
                    source="xe",
                    source_id=f"rent-{i}",
                    url=f"https://www.xe.gr/property/d/r/rent-{i}",
                    title=f"Διαμέρισμα {m2} τ.μ.",
                    listing_type="rent",
                    price=10 * m2 + (i % 4) * 30,
                    area_m2=float(m2),
                    floor=2.0,
                    year_built=2000 + i,
                    bedrooms=2,
                    neighborhood="Χαλάνδρι (Κέντρο)",
                    address="Χαλάνδρι (Κέντρο)",
                    search_area="Chalandri",
                    furnished=bool(i % 2),
                ),
            )
    from scout.ui import queries

    real = queries.load_rent_listings()
    assert len(real) == 12 and all(d["listing_type"] == "rent" for d in real)
    at = walk_rent(fresh(FIND), budget="guide-rb1000", beds="2", furnished=True)
    text = _text(at)
    want = len(picks_rent.find(real, 1000, bedrooms=2, furnished=True, top=10**6))
    assert want and f"**{want}** αγγελίες ενοικίασης" in text
    assert "από τα διπλανά (" in text and "Επιπλωμένο" in text


def test_rent_card_has_the_value_score_its_basis_and_the_near_chip():
    from scout.ui import buyer, rent_guide

    rows = [*RENTALS, rental(90, 1150, 80)]  # +15 % over 1.000: a near match on the amount
    got = picks_rent.find(rows, 1000, bedrooms=2, top=10**6, near=True)
    p = next(x for x in got if x.listing["id"] == 10_090)
    assert p.relaxed == "ποσό +15 %"
    html = buyer.card_html(p.listing, rent_guide.card_adv(p), False, compact=True)
    assert f">Βαθμολογία {p.score}<" in html.split("hg-l2")[0]
    assert (
        f"Βαθμολογία {p.score} από 100: " in html and "για την τιμή σε σχέση με τα παρόμοια" in html
    )
    assert f"Ξεφεύγει: {p.relaxed}" in html
