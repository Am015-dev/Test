"""The app shell: phone navigation pills, the data status line, deep links and compare."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("streamlit.testing.v1")

from .test_ui_gauntlet import APP, AppTest, env, ok  # noqa: E402,F401

try:  # the home page is the guide (W8) once it lands, «Βρες μου σπίτι» before
    from scout.ui.guide import TITLE as HOME

    HOME_PILL = "Οδηγός"
except ImportError:
    HOME = HOME_PILL = "Βρες μου σπίτι"

SHORT_TO_KEY = {
    HOME_PILL: HOME,
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
    assert at.session_state["page"] == HOME
    assert at.pills(key="nav_pill").value == HOME_PILL
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
    line = next(c.value for c in at.caption if c.value.startswith("XE.gr"))
    # the sources present in the data (only XE.gr in the fixture), then date and counts
    assert re.fullmatch(
        r"XE\.gr(, [^·]+)? · \d\d/\d\d · [\d.]+ ενεργές · [\d.]+ ελεγμένες",
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


def test_detail_page_is_not_a_menu_item_but_opens_from_a_card(env):  # noqa: F811
    at = _app()
    assert "Αγγελία" not in at.pills(key="nav_pill").options
    at.pills(key="nav_pill").set_value("Αναζήτηση").run()
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "detail")
    assert at.session_state["page"] == "Αγγελία"
    assert at.pills(key="nav_pill").value is None
    assert "Αγγελία" not in at.pills(key="nav_pill").options  # never a pill, even while open
    at.pills(key="nav_pill").set_value("Χάρτης").run()
    assert at.session_state["page"] == "Χάρτης"


# C9 — one navigation: the pills on every width; the sidebar keeps sign-in, refresh and
# the saved searches link, nothing that lists the pages.


def test_one_navigation_no_page_menu_in_the_sidebar(env):  # noqa: F811
    at = _app()
    assert not at.radio  # the old sidebar menu is gone everywhere
    assert [b.key for b in at.sidebar.button] == ["login_go", "login_new", "refresh", "nav_saved"]
    assert not any(b.label in SHORT_TO_KEY for b in at.sidebar.button)
    assert at.sidebar.button(key="nav_saved").label == "Αποθηκευμένες αναζητήσεις"
    assert at.sidebar.button(key="nav_saved").proto.type == "tertiary"  # link-style


def test_saved_searches_open_from_the_sidebar_and_from_search(env):  # noqa: F811
    at = _app()
    at.sidebar.button(key="nav_saved").click().run()
    ok(at, "sidebar saved")
    assert at.session_state["page"] == "Αποθηκευμένες αναζητήσεις"
    assert any(m.value == "## Αποθηκευμένες αναζητήσεις" for m in at.markdown)
    assert at.pills(key="nav_pill").value is None
    at.pills(key="nav_pill").set_value("Αναζήτηση").run()
    assert at.button(key="to_saved").label == "Αποθηκευμένες"
    at.button(key="to_saved").click().run()
    ok(at, "search saved")
    assert at.session_state["page"] == "Αποθηκευμένες αναζητήσεις"


def test_unknown_page_in_state_falls_back_home(env):  # noqa: F811
    at = _app()
    at.session_state["page"] = "🛠 Debug"  # an owner page without ?admin=1
    at.run()
    ok(at, "fallback")
    assert at.session_state["page"] == HOME
    assert at.pills(key="nav_pill").value == HOME_PILL


def test_admin_pages_are_pills_after_the_buyer_pages(env):  # noqa: F811
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["admin"] = "1"
    at.run()
    ok(at, "admin")
    opts = list(at.pills(key="nav_pill").options)
    assert opts[: len(SHORT_TO_KEY)] == list(SHORT_TO_KEY)
    assert "Debug" in opts  # Streamlit shows a leading emoji as the pill's icon
    at.pills(key="nav_pill").set_value("🛠 Debug").run()
    ok(at, "debug")
    assert at.session_state["page"] == "🛠 Debug"
    assert at.pills(key="nav_pill").value == "🛠 Debug"


def test_listing_page_back_returns_where_it_was_opened(env):  # noqa: F811
    at = _app()
    at.pills(key="nav_pill").set_value("Αναζήτηση").run()
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "detail")
    assert at.session_state["page"] == "Αγγελία"
    assert any(m.value == "## Αγγελία" for m in at.markdown)
    at.button(key="listing-back").click().run()
    ok(at, "back")
    assert at.session_state["page"] == "Αναζήτηση"
    # nothing to return to: «Πίσω» goes home
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    at.session_state["detail_from"] = None
    at.button(key="listing-back").click().run()
    assert at.session_state["page"] == HOME


def test_empty_favourites_offer_the_guide(env):  # noqa: F811
    at = _app()
    at.pills(key="nav_pill").set_value("Αγαπημένα").run()
    at.button(key="watch_to_guide").click().run()
    ok(at, "to guide")
    assert at.session_state["page"] == HOME


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
    assert fields == [
        "Βαθμολογία",  # C7: the score is the first row
        "Τιμή",
        "€/τ.μ.",
        "τ.μ.",
        "Όροφος",
        "Έτος",
        "Ενοίκιο (εκτίμηση)",
        "Μικτή απόδοση",
        "Σταθμός",
    ]
    assert len(fields) <= 9  # C3's eight rows + C7's score, one value per cell
    for r in rows[2:-1]:  # «Μετρό Χολαργός · 360 μ.» (the station row) is one value
        assert all(" · " not in c for c in r.split("|")[2:4]), r
    # then the two compact cards, two buttons each
    assert sum(1 for b in at.button if b.label == "Λεπτομέρειες") == 2
    assert not any(b.label.startswith("Άνοιγμα") for b in at.main.button)
    # two flats at most: exactly two pickers, no multiselect (its notice is English)
    assert len(at.selectbox) == 2 and not at.multiselect
    at.selectbox(key="compare_b").set_value(opts[0]).run()
    assert any("διαφορετικές" in i.value for i in at.info)


def test_compare_opens_filled_with_top_picks_when_no_favourites(env):  # noqa: F811
    at = _app()
    at.pills(key="nav_pill").set_value("Σύγκριση").run()
    ok(at, "compare")
    a, b = at.selectbox(key="compare_a").value, at.selectbox(key="compare_b").value
    assert a and b and a != b
    assert any(m.value.startswith("| | Α | Β |") for m in at.markdown)


def test_map_page_is_the_map_with_the_ranked_list_under_it(env):  # noqa: F811
    at = _app()
    at.pills(key="nav_pill").set_value("Χάρτης").run()
    ok(at, "map")
    assert not at.dataframe  # no table to scroll to in order to understand a dot
    assert [e.label for e in at.main.expander] == ["Φίλτρα"]  # the filters stay in one place
    try:
        import scout.ui.maplist  # noqa: F401
    except ImportError:  # before W9: today's map + top cards
        return
    assert any(m.value.startswith("#### Όλες με τη σειρά") for m in at.markdown)


def test_status_is_one_short_line_and_refresh_lives_in_the_sidebar(env):  # noqa: F811
    at = _app()
    # one header line «Σκάουτ ακινήτων», the data line right under it
    heads = [m.value for m in at.main.markdown if m.value.startswith('<div class="hg-app-head"')]
    assert len(heads) == 1 and "Σκάουτ ακινήτων" in heads[0]
    line = next(c.value for c in at.caption if c.value.startswith("XE.gr ·"))
    assert len(line) <= 48  # one line at 390 px
    assert any(b.key == "refresh" for b in at.sidebar.button)
    assert not any(b.key == "refresh" for b in at.main.button)


# ---- accounts in the shell ---------------------------------------------------------------


def _sign_up(at: AppTest, name: str, pin: str, new: bool = True) -> AppTest:
    at.sidebar.text_input(key="login_name").input(name)
    at.sidebar.text_input(key="login_pin").input(pin)
    at.sidebar.button(key="login_new" if new else "login_go").click().run()
    ok(at, "login")
    return at


def test_login_block_renders_in_the_sidebar(env):  # noqa: F811
    at = _app()
    assert [e.label for e in at.sidebar.expander] == ["Σύνδεση"]
    assert at.sidebar.text_input(key="login_pin").proto.type == 1  # PASSWORD
    assert any(c.value.startswith("Χωρίς σύνδεση") for c in at.sidebar.caption)


def test_sign_up_shows_who_and_logout_returns_to_anonymous(env):  # noqa: F811
    at = _sign_up(_app(), "Μαρία", "1234")
    assert any("Συνδεδεμένος ως **Μαρία**" in m.value for m in at.sidebar.markdown)
    stored = __import__("json").loads(env.gists["g1"]["files"]["mandates.json"]["content"])
    prof = stored["profiles"]["μαρια"]
    assert "1234" not in __import__("json").dumps(stored)  # never the PIN itself
    assert set(prof) >= {"salt", "hash", "data"}
    at.sidebar.button(key="logout").click().run()
    ok(at, "logout")
    assert at.session_state["page"] == HOME
    assert any(e.label == "Σύνδεση" for e in at.sidebar.expander)


def test_wrong_pin_is_refused_without_echoing_it(env):  # noqa: F811
    at = _sign_up(_app(), "Νίκος", "4321")
    at.sidebar.button(key="logout").click().run()
    at = _sign_up(at, "Νίκος", "9999", new=False)
    texts = [w.value for w in at.sidebar.warning] + [c.value for c in at.sidebar.caption]
    assert any("Λάθος PIN" in t for t in texts) and not any("9999" in t for t in texts)
    assert not any("Συνδεδεμένος" in m.value for m in at.sidebar.markdown)


def test_favourites_follow_the_profile(env):  # noqa: F811
    at = _sign_up(_app(), "Ελένη", "1111")
    at.pills(key="nav_pill").set_value("Αναζήτηση").run()
    star = next(b for b in at.main.button if b.label == "Αγαπημένο")
    star.click().run()
    ok(at, "star")
    starred = set(at.session_state["watch"])
    assert starred
    at.sidebar.button(key="logout").click().run()
    assert buyer_watch(at) == set()  # the anonymous profile has its own (empty) list
    at = _sign_up(at, "Ελένη", "1111", new=False)
    assert buyer_watch(at) == starred


def buyer_watch(at: AppTest) -> set[str]:
    at.pills(key="nav_pill").set_value("Αγαπημένα").run()
    ok(at, "favourites")
    return set(at.session_state["watch"])


def test_deep_link_still_works_when_signed_in(env):  # noqa: F811
    at = _sign_up(_app(), "Κώστας", "2468")
    at.session_state["page"] = "Σύγκριση"
    at.run()
    ok(at, "deep link")
    assert at.pills(key="nav_pill").value == "Σύγκριση"
