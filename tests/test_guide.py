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
    assert cards and "Δεν έχει ελεγχθεί ακόμα η σελίδα της αγγελίας" in _text(at)
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
        "300 χιλ.",
        "ανατίμηση",
        "κοντά σε μετρό",
        "νεόδμητο · 3+ υπν.",
    ]
    g = {**g, "where": "areas", "areas": ["Γαλάτσι"], "age": None, "bedrooms": None, "loan": True}
    assert guide.answer_chips(g) == [
        "300 χιλ. · με δάνειο",
        "ανατίμηση",
        "Γαλάτσι",
        "οποιαδήποτε ηλικία",
    ]  # fmt: skip
