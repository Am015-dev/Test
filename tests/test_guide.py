"""«Οδηγός»: the five-step flow, the answer chips, paging by 10, and the loan maths."""

from __future__ import annotations

import re

import pytest

from scout import market_intel, picks
from scout.ui import guide

from .test_picks import RENTS, YEAR, flat
from .test_ui_gauntlet import FIND, env, fresh, ok  # noqa: F401 — AppTest harness


def _text(at) -> str:
    return " ".join(m.value for m in at.markdown)


def _cards(at) -> list[str]:
    return [b.key for b in at.button if b.key and b.key.startswith("pick-no-")]


def walk(at, budget="guide-b250", goal="yield", where="best", age="any"):
    assert "### Τι ψάχνεις;" in _text(at) and "Βήμα" not in _text(at)
    at.button(key="guide-mode-buy").click().run()
    assert at.session_state["guide"]["mode"] == "buy"
    assert "Βήμα 1 από 5" in _text(at) and "Πόσα θες να βάλεις;" in _text(at)
    at.toggle(key="guide_loan").set_value(True).run()
    at.button(key=budget).click().run()
    ok(at, "step 1")
    assert "Βήμα 2 από 5" in _text(at) and "Τι σε νοιάζει πιο πολύ;" in _text(at)
    at.button(key=f"guide-g-{goal}").click().run()
    ok(at, "step 2")
    assert "Βήμα 3 από 5" in _text(at) and "### Πού;" in _text(at)
    at.button(key=f"guide-w-{where}").click().run()
    ok(at, "step 3")
    assert "Βήμα 4 από 5" in _text(at) and "Τι σπίτι;" in _text(at)
    at.button_group(key="guide_age").set_value(age).run()
    at.button(key="guide-show").click().run()
    ok(at, "step 4")
    assert "Βήμα 5 από 5" in _text(at) and "### Η πρότασή μου" in _text(at)
    return at


def test_five_steps_chips_and_ten_more(env):  # noqa: F811 — the gauntlet's app fixture
    at = walk(fresh(FIND))
    chips = at.button_group(key="guide_chips")
    assert list(chips.options) == [
        "να αγοράσω",
        "250 χιλ. · με δάνειο",
        "απόδοση",
        "όπου βγαίνει",
        "οποιαδήποτε ηλικία",
    ]  # fmt: skip
    text = _text(at)
    assert (
        "Πρόταση: **" in text
        and "Δόση ~" in text
        and "Πηγές: XE.gr · " in " ".join(c.value for c in at.caption)
    )
    total = int(re.search(r"\*\*(\d+)\*\* αγγελίες", text).group(1))
    assert total > picks.PAGE
    first = _cards(at)
    assert len(first) == picks.PAGE
    more = at.button(key="guide-more-btn")
    assert more.label.startswith("Δείξε άλλες ")
    more.click().run()
    ok(at, "more")
    after = _cards(at)
    assert after[: picks.PAGE] == first and len(after) == min(2 * picks.PAGE, total)
    # a chip reopens its question; answering it lands back on the result
    at.button_group(key="guide_chips").set_value("απόδοση").run()
    ok(at, "chip")
    assert "Βήμα 2 από 5" in _text(at)
    at.button(key="guide-g-safety").click().run()
    assert at.session_state["guide"]["goal"] == "safety"
    assert at.session_state["guide"]["step"] == 3  # the next question; the rest is kept
    at.button(key="guide-back").click().run()
    assert "Βήμα 2 από 5" in _text(at)


def test_drop_moves_the_next_up_and_relaxation_has_exact_counts(env):  # noqa: F811
    at = walk(fresh(FIND), budget="guide-b200", where="rail", age="10")
    text = _text(at)
    assert (
        at.session_state["guide"]["age"] == 10
        and "νεόδμητο" in at.button_group(key="guide_chips").options
    )
    assert "Καμία αγγελία" in text  # the seed has no station neighbourhoods
    relax = [b for b in at.button if b.key and b.key.startswith("relax-")]
    no_rail = next(b for b in relax if b.label.startswith("Χωρίς όρο σταθμού (+"))
    added = int(no_rail.label.split("(+")[1].split(",")[0].rstrip(")"))
    no_rail.click().run()
    ok(at, "relax")
    assert at.session_state["guide"]["where"] == "best"
    assert f"**{added}** αγγελίες" in _text(at)
    cards = _cards(at)
    assert cards and "Δεν έχει ελεγχθεί ακόμα" in _text(at)
    at.button(key=cards[0]).click().run()
    ok(at, "drop")
    assert cards[0] not in _cards(at)
    assert any(e.label == "Απέρριψες 1" for e in at.expander)
    assert any(e.label == "Πώς υπολογίζω" for e in at.expander)
    assert not at.metric


def test_loan_maths_on_a_synthetic_listing():
    # 300.000 €: 70 % = 210.000 at 4 % over 25 years → 1.108,46 €/month (annuity)
    assert picks.instalment(300_000) == pytest.approx(1108.46, abs=0.01)
    assert picks.instalment(100_000, ltv=1, rate=0, years=10) == pytest.approx(100_000 / 120)
    rows = [flat(1, 300_000, m2=100)]  # 11 €/m² × 100 m² (2024 = new, +10 %) = 1.210 €
    p = picks.find(rows, market_intel.build(rows, YEAR), RENTS, 300_000, year=YEAR, loan=True)[0]
    assert (p.rent, p.instalment, p.cashflow) == (1210, 1110, 100)
    assert p.loan and p.loan_line == (
        "Δόση ~1.110 €/μήνα (δάνειο 70 %, 4 %, 25 έτη) → μένουν 100 €"
    )
    rows = [flat(2, 320_000, m2=80)]
    p = picks.find(rows, market_intel.build(rows, YEAR), RENTS, 300_000, year=YEAR, loan=True)[0]
    assert p.cashflow < 0 and p.loan_line.endswith(f"λείπουν {-p.cashflow} €")


def test_answer_chips_and_relax_mapping():
    g = {**guide.DEFAULTS, "budget": 300_000, "goal": "growth", "where": "rail", "bedrooms": 3}
    assert guide.answer_chips(g) == [
        "να αγοράσω",
        "300 χιλ.",
        "ανατίμηση",
        "κοντά σε μετρό",
        "νεόδμητο · 3+ υπν.",
    ]
    g = {**g, "where": "areas", "areas": ["Γαλάτσι"], "age": None, "bedrooms": None, "loan": True}
    assert guide.answer_chips(g) == [
        "να αγοράσω",
        "300 χιλ. · με δάνειο",
        "ανατίμηση",
        "Γαλάτσι",
        "οποιαδήποτε ηλικία",
    ]  # fmt: skip


def test_loan_summary_says_whether_the_rent_covers_the_instalment():
    def pk(cash):
        return picks.Pick(listing={}, rank_score=0, rent=0, rent_low=0, rent_high=0, gross=0,
                          net=0, offer=0, station=None, cashflow=cash)  # fmt: skip

    assert guide.loan_summary([pk(-110), pk(-340), pk(-160)]) == (
        "Με δάνειο: **καμία από τις 3 δεν καλύπτει τη δόση** με το ενοίκιο — "
        "λείπουν 110 €–340 €/μήνα."
    )
    assert guide.loan_summary([pk(-50), pk(20)]) == (
        "Με δάνειο: το ενοίκιο καλύπτει τη δόση σε **1 από τις 2** (στην καλύτερη μένουν 20 €/μήνα)."
    )
    assert guide.loan_summary([]) is None


def test_contract_hooks_line4_and_profile_store(monkeypatch):
    import sys
    import types

    import scout.ui

    # The real scout.metro_line4 (W12): a station counts only when the listing's own sub-area
    # carries its name, so «Γαλάτσι (Άλσος Βεΐκου)» has one and «Νέα Ιωνία (Κέντρο)» none.
    rows = [
        flat(1, 265_000, m2=95, hood="Γαλάτσι (Άλσος Βεΐκου)", page_checked=True),
        flat(2, 265_000, m2=95, hood="Νέα Ιωνία (Κέντρο)", page_checked=True),
    ]
    rents = [
        *RENTS,
        {"neighborhood": "Γαλάτσι (Άλσος Βεΐκου)", "rent_per_m2": 12.0, "samples": 9},
        {"neighborhood": "Νέα Ιωνία (Κέντρο)", "rent_per_m2": 12.0, "samples": 9},
    ]
    got = picks.find(rows, market_intel.build(rows, YEAR), rents, 300_000, year=YEAR,
                     near_rail=False, goal="growth", top=10)  # fmt: skip
    by_id = {p.listing["id"]: p for p in got}
    assert "Γραμμή 4: Άλσος Βεΐκου" in by_id[1].reasons["growth"]
    assert not any("Γραμμή 4" in r for r in by_id[2].reasons["growth"])
    assert picks.line4_stations("Γαλάτσι") == ["Άλσος Βεΐκου", "Γαλάτσι", "Ελικώνος"]
    assert picks.line4_stations("Νέα Ιωνία") == []

    class Store:
        def __init__(self):
            self.data = {"guide": {"budget": 200_000, "step": 2}}

        def get(self, key, default=None):
            return self.data.get(key, default)

        def set(self, key, value):
            self.data[key] = value

    store = Store()
    acc = types.ModuleType("scout.ui.account")
    acc.storage = lambda: store
    monkeypatch.setitem(sys.modules, "scout.ui.account", acc)
    monkeypatch.setattr(scout.ui, "account", acc, raising=False)  # once the real one is imported
    assert guide._load_saved() == {"budget": 200_000, "step": 2}
    guide._save({"budget": 300_000})
    assert store.data["guide"] == {"budget": 300_000}


def test_assistant_gets_its_own_facts_format(monkeypatch):
    """The brief and the «Ρώτα με» panel read ``facts["listings"]``: the guide must hand the
    assistant its own facts_for output, not the page's Greek-keyed summary."""
    from scout import market_intel
    from scout.ui import assistant

    rows = [
        flat(1, 265_000, m2=95, hood="Γαλάτσι (Άλσος Βεΐκου)", page_checked=True),
        flat(2, 265_000, m2=95, hood="Νέα Ιωνία (Κέντρο)", page_checked=True),
    ]
    rents = [
        *RENTS,
        {"neighborhood": "Γαλάτσι (Άλσος Βεΐκου)", "rent_per_m2": 12.0, "samples": 9},
        {"neighborhood": "Νέα Ιωνία (Κέντρο)", "rent_per_m2": 12.0, "samples": 9},
    ]
    intel = market_intel.build(rows, YEAR)
    every = picks.find(rows, intel, rents, 300_000, year=YEAR, near_rail=False, top=10)
    g = {"budget": 300_000, "goal": "yield", "loan": True, "where": "rail", "age": 10}
    facts = guide.assistant_facts(every, g, {}, intel, rents, 300_000, "yield")
    assert len(facts["listings"]) == len(every) and facts["buyer"]["budget"] == 300_000
    assert facts["buyer"]["loan"] is True and "loan" in facts["listings"][0]
    seen = {}
    monkeypatch.setattr(assistant, "brief", lambda f, client=None: seen.setdefault("f", f) and "ok")
    monkeypatch.setattr(assistant, "enabled", lambda: True)
    assert assistant.brief(facts) == "ok" and seen["f"] is facts
