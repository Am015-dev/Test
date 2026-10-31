"""The app shell: phone navigation pills, the data status line, deep links and compare."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("streamlit.testing.v1")

from .test_ui_gauntlet import APP, AppTest, env, ok  # noqa: E402,F401

SHORT_TO_KEY = {
    "Βρες μου σπίτι": "Βρες μου σπίτι",
    "Περιοχές": "Πού να αγοράσω",
    "Αναζήτηση": "Αναζήτηση",
    "Χάρτης": "Χάρτης",
    "Αγαπημένα": "Αγαπημένα",
    "Σύγκριση": "Σύγκριση",
}


def _app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60).run()
    ok(at, "start")
    return at


def test_default_page_is_first_nav_entry_and_renders(env):  # noqa: F811
    at = _app()
    assert at.session_state["page"] == "Βρες μου σπίτι"
    assert at.pills(key="nav_pill").value == "Βρες μου σπίτι"
    assert len(at.main) > 0


@pytest.mark.parametrize("short", list(SHORT_TO_KEY))
def test_every_short_label_routes_to_its_nav_key(env, short):  # noqa: F811
    at = _app()
    assert list(at.pills(key="nav_pill").options) == list(SHORT_TO_KEY)
    at.pills(key="nav_pill").set_value(short).run()
    ok(at, short)
    assert at.session_state["page"] == SHORT_TO_KEY[short]
    assert at.pills(key="nav_pill").value == short


def test_data_status_line_has_greek_numbers_and_no_english(env):  # noqa: F811
    at = _app()
    line = next(c.value for c in at.caption if c.value.startswith("Αγγελίες XE.gr"))
    assert re.fullmatch(
        r"Αγγελίες XE\.gr · ενημέρωση \d\d/\d\d · [\d.]+ ενεργές · [\d.]+ ελεγμένες σελίδες",
        line,
    ), line
    assert not re.search(r"[A-Za-z]{3,}", line.replace("XE.gr", ""))
    assert "," not in line  # Greek thousands separator is «.»


def test_deep_link_via_session_state_selects_page_and_pill(env):  # noqa: F811
    at = _app()
    at.session_state["page"] = "Σύγκριση"
    at.run()
    ok(at, "deep link")
    assert at.pills(key="nav_pill").value == "Σύγκριση"
    assert any(s.value == "Σύγκριση" for s in at.subheader)
    # a page without a pill («Αγγελία») stays selected; the pill row just shows none
    at.session_state["page"] = "Αγγελία"
    at.run()
    ok(at, "detail")
    assert at.session_state["page"] == "Αγγελία"
    assert at.pills(key="nav_pill").value is None


def test_tapping_the_selected_pill_again_keeps_the_page(env):  # noqa: F811
    at = _app()
    at.pills(key="nav_pill").set_value("Χάρτης").run()
    at.pills(key="nav_pill").set_value(None).run()
    ok(at, "deselect")
    assert at.session_state["page"] == "Χάρτης"
    assert at.pills(key="nav_pill").value == "Χάρτης"


def test_compare_is_a_three_column_facts_table_for_two_flats(env):  # noqa: F811
    at = _app()
    at.pills(key="nav_pill").set_value("Σύγκριση").run()
    ok(at, "compare")
    opts = at.selectbox(key="compare_a").options
    at.selectbox(key="compare_a").set_value(opts[0]).run()
    at.selectbox(key="compare_b").set_value(opts[1]).run()
    ok(at, "two flats")
    assert not at.dataframe
    table = next(m.value for m in at.markdown if m.value.startswith("| | Α | Β |"))
    rows = [r for r in table.splitlines() if r.startswith("|")]
    assert all(r.count("|") == 4 for r in rows)  # field · Α · Β
    fields = [r.split("|")[1].strip() for r in rows[2:]]
    for want in (
        "€/τ.μ.",
        "Ενοίκιο (εκτίμηση)",
        "Μικτή απόδοση",
        "Καθαρή απόδοση",
        "Παρόμοια",
        "Κατάσταση",
        "Σταθμός",
    ):
        assert want in fields, fields
    # two flats at most: exactly two pickers, no multiselect (its notice is English)
    assert len(at.selectbox) == 2 and not at.multiselect
    at.selectbox(key="compare_b").set_value(opts[0]).run()
    assert any("διαφορετικές" in i.value for i in at.info)
