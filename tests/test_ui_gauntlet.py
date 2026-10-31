"""The UI gauntlet: every page renders, every widget works, and the buyer journey holds.

* ``test_every_page_renders`` and ``test_buyer_journey`` run in CI.
* ``test_every_widget_on_every_page`` clicks/sets EVERY button, checkbox, select, slider, input…
  on every page, one at a time, and fails on any exception. It is slow (hundreds of app runs),
  so it only runs with ``GAUNTLET=1 pytest tests/test_ui_gauntlet.py``.

Streamlit's in-process AppTest drives the real app against a seeded SQLite DB; the GitHub gist
store and the Claude parser are replaced by in-memory fakes, and no network is touched.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

from scout.config import get_settings  # noqa: E402
from scout.nl_search import SearchFilters  # noqa: E402
from scout.scoring import compute_market_stats, score  # noqa: E402

from .conftest import make_listing  # noqa: E402
from .test_shortlist import FakeGist  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "src" / "scout" / "ui" / "app.py")
SEARCH, SHORTLIST, STARRED = "Αναζήτηση", "Αποθηκευμένες αναζητήσεις", "Αγαπημένα"
DETAIL = "Αγγελία"
AREAS = "Πού να αγοράσω"
FIND = "Βρες μου σπίτι"
PAGES = [FIND, AREAS, SEARCH, "Χάρτης", STARRED, SHORTLIST, "Σύγκριση", DETAIL]
KINDS = [
    "button",
    "checkbox",
    "toggle",
    "selectbox",
    "radio",
    "select_slider",
    "slider",
    "multiselect",
    "number_input",
    "text_input",
    "text_area",
]


def _seed(db_path) -> None:
    import scout.db as dbmod

    dbmod._engine = None
    dbmod._SessionFactory = None
    from scout.config import load_strategy
    from scout.db import init_db, session_scope, upsert_listing_with_history
    from scout.valuation import fit_and_apply_by_area

    init_db()
    strategy = load_strategy()
    titles = [
        "Διαμέρισμα {a} τ.μ. ανακαινισμένο",
        "Μεζονέτα {a} τ.μ.",
        "Μονοκατοικία {a} τ.μ.",
        "Διαμέρισμα {a} τ.μ. με ανελκυστήρα",
    ]
    hoods = ["Χολαργός", "Παπάγου", "Αγία Παρασκευή"]
    areas = ["Cholargos", "Papagou", "Agia Paraskevi"]
    listings = []
    for i in range(45):
        a = 55 + (i % 40)
        price = int(3000 * a) + (i % 7 - 3) * 9000
        listings.append(
            make_listing(
                source="xe",
                source_id=f"g-{i}",
                url=f"https://www.xe.gr/property/d/x/g-{i}",
                title=titles[i % 4].format(a=a),
                price=price,
                area_m2=float(a),
                floor=float(i % 6),
                year_built=1980 + i % 40,
                energy_class="BCD"[i % 3],
                bedrooms=1 + i % 3,
                metro_distance_m=300 + (i % 6) * 60,
                neighborhood=hoods[i % 3],
                address=hoods[i % 3],
                search_area=areas[i % 3],
                is_private_seller=bool(i % 2),
                price_per_m2=price / a,
                image_url="https://example.com/p.jpg" if i % 5 == 0 else None,
            )
        )
    # Two areas with enough fresh, usable (1st floor+) flats to qualify for «Πού να αγοράσω»
    # (area_insights.MIN_FRESH), one with recorded rent sample counts and one without.
    for j, (hood, area, base) in enumerate(
        [("Χαλάνδρι (Κέντρο)", "Chalandri", 3300)] * 26
        + [("Γαλάτσι (Λαμπρινή)", "Galatsi", 2600)] * 24
    ):
        a = 60 + j % 35
        price = int(base * a) + (j % 5 - 2) * 6000
        listings.append(
            make_listing(
                source="xe",
                source_id=f"q-{j}",
                url=f"https://www.xe.gr/property/d/x/q-{j}",
                title=f"Διαμέρισμα {a} τ.μ.",
                price=price,
                area_m2=float(a),
                floor=float(1 + j % 4),
                year_built=1990 + j % 33,
                energy_class="BCD"[j % 3],
                bedrooms=1 + j % 3,
                metro_distance_m=400 + (j % 5) * 50,
                neighborhood=hood,
                address=hood,
                search_area=area,
                is_private_seller=bool(j % 2),
                price_per_m2=price / a,
            )
        )
    listings.append(  # an unfinished shell: cheapest of all, passes the default filters
        make_listing(
            source="xe",
            source_id="g-unf",
            url="https://www.xe.gr/property/d/x/g-unf",
            title="Διαμέρισμα 40 τ.μ. ημιτελές",
            price=95_000,
            area_m2=40.0,
            floor=2.0,
            year_built=2012,
            bedrooms=1,
            neighborhood="Χολαργός",
            address="Χολαργός",
            search_area="Cholargos",
            price_per_m2=95_000 / 40,
            is_unfinished=True,
        )
    )
    fit_and_apply_by_area(listings)
    stats = compute_market_stats(listings)
    with session_scope() as session:
        for lst in listings:
            row = upsert_listing_with_history(session, lst)
            scored = score(lst, stats, strategy)
            row.score = scored.score
            row.excluded = scored.excluded
            row.predicted_price = lst.predicted_price
            row.value_gap_pct = lst.value_gap_pct
    from scout.rent_comps import OVERALL_KEY, save_rent_comps

    save_rent_comps("Chalandri", {OVERALL_KEY: 13.0, "Χαλάνδρι (Κέντρο)": 13.0}, {OVERALL_KEY: 42})
    save_rent_comps("Galatsi", {OVERALL_KEY: 10.5, "Γαλάτσι (Λαμπρινή)": 10.5})


@pytest.fixture
def env(tmp_path, monkeypatch):
    import requests
    import streamlit as st

    import scout.nl_search as nl
    import scout.remote_db as rdb
    import scout.shortlist as sl

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "g.db"))
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    st.cache_data.clear()
    st.cache_resource.clear()
    _seed(tmp_path / "g.db")
    fake = FakeGist()
    monkeypatch.setattr(requests, "request", fake.request)
    monkeypatch.setattr(sl, "_gist_id", None)
    monkeypatch.setattr(sl, "_recent", None)

    def no_net(*a, **k):
        raise OSError("no network in tests")

    monkeypatch.setattr(rdb.requests, "get", no_net)
    monkeypatch.setattr(
        nl,
        "parse_query",
        lambda text, client=None: SearchFilters(areas=["Χολαργός", "Cholargos"], price_max=400_000),
    )
    import scout.advisor as adv

    def fake_review(query, rows, client=None, max_rows=12):
        labels = ["Αξίζει", "Με επιφύλαξη", "Απόφυγε"]
        return adv.Review(
            summary="Δοκιμαστική γνώμη συμβούλου.",
            verdicts=[
                adv.Verdict(key=adv.key_of(r), label=labels[i % 3], reason="δοκιμή")
                for i, r in enumerate(rows[:max_rows])
            ],
        )

    monkeypatch.setattr(adv, "review", fake_review)
    return fake


def fresh(page: str):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    if page != PAGES[0]:  # the app opens on the first menu entry
        if page in at.radio(key="page").options:
            at.radio(key="page").set_value(page).run()
        else:  # «Αγγελία» is not a menu item: open it from a card, like a user does
            at.radio(key="page").set_value("Αναζήτηση").run()
            next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
            assert at.session_state["page"] == page
    return at


def ok(at, where: str) -> None:
    assert not at.exception, f"{where}: " + " | ".join(e.value[:300] for e in at.exception)


def test_every_page_renders(env):
    for page in PAGES:
        at = fresh(page)
        ok(at, page)
        assert len(at.main) > 0, page


def test_buyer_journey(env):
    """Search → card actions → details → star → favourites → saved search → review → delete."""
    at = fresh(SEARCH)
    # landing state shows the best listings with working card buttons
    assert any(b.label == "☆ Αγαπημένο" for b in at.button)
    # an example search runs and shows what was understood
    at.button(key="ex0").click().run()
    ok(at, "example")
    assert "Χολαργός" in at.expander[0].label  # the filter panel's label says what is applied
    # the AI second opinion is optional: only on request, then its verdicts are on the cards
    assert not any("Δεύτερη γνώμη από τεχνητή νοημοσύνη**" in m.value for m in at.markdown)
    at.button(key="advice_again").click().run()
    ok(at, "second opinion")
    assert any("Δεύτερη γνώμη από τεχνητή νοημοσύνη" in m.value for m in at.markdown)
    assert any("Δεύτερη γνώμη από τεχνητή νοημοσύνη: Αξίζει" in m.value for m in at.markdown)
    # star the first result
    next(b for b in at.button if b.label == "☆ Αγαπημένο").click().run()
    ok(at, "star")
    assert any(b.label == "★ Αφαίρεση" for b in at.button)
    # it is on the favourites page and persisted in the gist
    at.radio(key="page").set_value(STARRED).run()
    ok(at, "favourites")
    assert any(m.value == "## Αγαπημένα (1)" for m in at.markdown)
    # open its details from the favourites page
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "details")
    assert at.session_state["page"] == DETAIL
    # the listing page: what the listing says, rent & yield, comparables, no investor jargon
    text = " ".join(m.value for m in at.markdown)
    assert "Τι λέει η αγγελία" in text and "Ενοίκιο και απόδοση" in text
    assert "#### Παρόμοια (" in text or "#### Λίγα παρόμοια" in text
    assert "12 × ενοίκιο ÷ τιμή" in " ".join(c.value for c in at.caption)
    assert "Έξοδα αγοράς" in text and "Καθαρή απόδοση" in text
    assert not any(w in text for w in ("Golden Visa", "Airbnb", "DSCR", "cap rate", "GRM"))
    # a second opinion on this one listing
    calls = at.session_state.get("advice_calls", 0)
    next(b for b in at.button if b.label == "Δεύτερη γνώμη από τεχνητή νοημοσύνη").click().run()
    ok(at, "listing advice")
    assert at.session_state["advice_calls"] == calls + 1
    assert any(
        "Δεύτερη γνώμη από τεχνητή νοημοσύνη:" in m.value and "hg-advice" in m.value
        for m in at.markdown
    )
    # unstar from the listing page
    next(b for b in at.button if b.label == "★ Αφαίρεση").click().run()
    ok(at, "unstar")
    at.radio(key="page").set_value(STARRED).run()
    assert any("Δεν έχεις αγαπημένα" in i.value for i in at.info)
    # save the search
    at.radio(key="page").set_value(SEARCH).run()
    at.button(key="save_mandate").click().run()
    ok(at, "save mandate")
    assert any("Αποθηκεύτηκε" in s.value for s in at.success)
    # shortlist: the mandate shows with picks; approve one, reject one
    at.radio(key="page").set_value(SHORTLIST).run()
    ok(at, "shortlist")
    next(b for b in at.button if b.label == "Έγκριση").click().run()
    ok(at, "approve")
    next(b for b in at.button if b.label == "Απόρριψη").click().run()
    ok(at, "reject")
    assert any("εγκρίθηκαν 1" in e.label and "απορρίφθηκαν 1" in e.label for e in at.expander)
    # the approved one is now starred
    at.radio(key="page").set_value(STARRED).run()
    assert any(m.value == "## Αγαπημένα (1)" for m in at.markdown)
    # delete the mandate
    at.radio(key="page").set_value(SHORTLIST).run()
    next(b for b in at.button if b.label == "Διαγραφή αναζήτησης").click().run()
    ok(at, "delete")
    assert any("Καμία αποθηκευμένη αναζήτηση" in i.value for i in at.info)


def test_search_filter_editor_sort_and_clear(env):
    at = fresh(SEARCH)
    at.button(key="ex0").click().run()
    ver = at.session_state["f_ver"]
    calls = at.session_state["advice_calls"] if "advice_calls" in at.session_state else 0
    at.number_input(key=f"fe_year_{ver}").set_value(0).run()
    at.number_input(key=f"fe_floor_{ver}").set_value(0).run()
    at.number_input(key=f"fe_pmax_{ver}").set_value(200_000).run()
    ok(at, "price filter")
    at.selectbox(key="sort").set_value("Χαμηλότερη τιμή").run()
    ok(at, "sort")
    nums = _card_prices(at)
    assert nums, "no result cards shown"
    assert nums == sorted(nums) and all(n <= 200_000 for n in nums)
    # filter and sort tweaks never call the AI on their own
    assert (at.session_state["advice_calls"] if "advice_calls" in at.session_state else 0) == calls
    at.button(key="advice_again").click().run()
    ok(at, "new advice")
    assert at.session_state["advice_calls"] == calls + 1
    at.button(key="clear_q").click().run()
    ok(at, "clear")
    assert "nl_filters" not in at.session_state


def test_compare_lines_up_every_picked_listing(env):
    """Two flats in the same neighbourhood used to share one column (the later overwrote it),
    and the mixed int/"—" days-on-market row broke Arrow serialisation."""
    at = fresh("Σύγκριση")
    opts = at.selectbox(key="compare_a").options
    at.selectbox(key="compare_a").set_value(opts[0]).run()
    at.selectbox(key="compare_b").set_value(opts[1]).run()
    ok(at, "compare")
    legend = next(m.value for m in at.markdown if m.value.startswith("**Α**"))
    assert "**Β**" in legend
    table = next(m.value for m in at.markdown if m.value.startswith("| | Α | Β |"))
    assert all(r.count("|") == 4 for r in table.splitlines())


def test_where_to_buy_cards_table_and_handoff(env):
    at = fresh(AREAS)
    ok(at, AREAS)
    assert any("πρόσφατες αγγελίες" in c.value for c in at.caption)
    text = " ".join(m.value for m in at.markdown)
    cards = [m.value[5:] for m in at.markdown if m.value.startswith("#### ")]
    assert sorted(cards) == ["1. Γαλάτσι", "2. Χαλάνδρι"], cards
    assert "n=42" in text and "δείγμα ενοικίων μη καταγεγραμμένο" in text
    assert "Για απόδοση:" in text and "Προσοχή" in text
    df = at.dataframe[0].value
    assert list(df["Περιοχή"]) == ["Γαλάτσι", "Χαλάνδρι"]
    assert len(df.columns) <= 4  # phone: the rest is in the card
    go = [b for b in at.button if b.label == "Δες τις αγγελίες"]
    assert len(go) == 3  # two top cards + the detail card under «Όλες οι περιοχές»
    go[1].click().run()
    ok(at, "handoff")
    assert at.session_state["page"] == SEARCH
    # the search page applied the pick: Χαλάνδρι preselected, key consumed
    area = next(m for m in at.multiselect if m.label == "Περιοχή")
    assert area.value == ["Χαλάνδρι"]
    assert "area_pick" not in at.session_state


ADMIN_PAGES = [  # only listed with ?admin=1
    "🧮 Ανάλυση επενδυτή",
    "📊 Αγορά",
    "🏆 Ευκαιρίες",
    "📰 Σήμερα",
    "💼 Deals",
    "⚙️ Strategy",
    "🛠 Debug",
]


def fresh_admin(page: str):
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["admin"] = "1"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    at.radio(key="page").set_value(page).run()
    return at


@pytest.mark.skipif(not os.environ.get("GAUNTLET"), reason="slow: set GAUNTLET=1")
def test_every_widget_on_every_page(env, tmp_path, monkeypatch):
    import copy
    import shutil

    import scout.config as cfg
    import scout.shortlist as sl

    # The Strategy page's "Save & re-score" writes strategy.yaml — point it at a scratch copy.
    strat = tmp_path / "strategy.yaml"
    shutil.copy(cfg.DEFAULT_STRATEGY_PATH, strat)
    monkeypatch.setattr(cfg, "DEFAULT_STRATEGY_PATH", strat)
    pristine_strategy = strat.read_text(encoding="utf-8")

    # Give Favourites / Shortlist / Detail something to act on: two starred listings and one
    # saved search. Every interaction then starts from this SAME persisted state — otherwise a
    # click in one run (e.g. "★ Αφαίρεση") changes what the next fresh run renders and the
    # widget indices drift (spurious IndexErrors that are the crawler's fault, not the app's).
    sl.set_watch("xe:g-0", True)
    sl.set_watch("xe:g-1", True)
    sl.save_mandate("Χολαργός έως 400.000", SearchFilters(areas=["Cholargos"], price_max=400_000))
    snapshot = copy.deepcopy(env.gists)

    def reset() -> None:
        env.gists = copy.deepcopy(snapshot)
        sl._gist_id = None
        sl._recent = None
        strat.write_text(pristine_strategy, encoding="utf-8")

    def start(page: str):
        reset()
        return fresh_admin(page) if page in ADMIN_PAGES else fresh(page)

    failures = []
    runs = 0
    for page in PAGES + ADMIN_PAGES:
        base = start(page)
        print(page, {k: len(getattr(base, k)) for k in KINDS if len(getattr(base, k))})
        for kind in KINDS:
            for i, el in enumerate(getattr(base, kind)):
                if getattr(el, "key", None) == "page":
                    continue
                label = getattr(el, "label", "")
                for tag, act in _variants(el, kind):
                    try:
                        at = start(page)
                        act(getattr(at, kind)[i])
                        at.run()
                        runs += 1
                        if at.exception:
                            failures.append(
                                f"{page} | {kind}[{i}] '{label}' {tag}: {at.exception[0].value[:200]}"
                            )
                    except Exception as e:  # a widget that cannot even be driven is a failure too
                        failures.append(
                            f"{page} | {kind}[{i}] '{label}' {tag}: {type(e).__name__}: {str(e)[:200]}"
                        )
    print(f"{runs} interactions, {len(failures)} failures")
    assert not failures, f"{len(failures)} failures in {runs} interactions:\n" + "\n".join(failures)


def _variants(el, kind: str):
    if kind == "button":
        return [("click", lambda w: w.click())]
    if kind in ("checkbox", "toggle"):
        return [("toggle", lambda w: w.set_value(not w.value))]
    if kind in ("selectbox", "radio", "select_slider"):
        opts = list(el.options)
        picks = opts[:1] + opts[len(opts) // 2 : len(opts) // 2 + 1] + opts[-1:]
        return [
            (f"={o!s:.30}", (lambda v: lambda w: w.set_value(v))(o)) for o in dict.fromkeys(picks)
        ]
    if kind == "multiselect":
        opts = list(el.options)
        return [("some", lambda w: w.set_value(opts[:3])), ("none", lambda w: w.set_value([]))]
    if kind == "slider" and isinstance(el.value, (list, tuple)):
        # A range slider always sends two handles; drive it like a user would (both ends
        # pushed to one extreme) instead of a scalar a real browser can never produce.
        lo, hi = el.min, el.max
        return [
            ("min", lambda w: w.set_range(lo, lo)),
            ("max", lambda w: w.set_range(hi, hi)),
            ("full", lambda w: w.set_range(lo, hi)),
        ]
    if kind in ("slider", "number_input"):
        lo, hi = getattr(el, "min", None), getattr(el, "max", None)
        # An unbounded number_input accepts anything the user types: try 0 / a huge value.
        lo = 0 if lo is None else lo
        hi = 1_000_000 if hi is None else hi
        return [("min", lambda w: w.set_value(lo)), ("max", lambda w: w.set_value(hi))]
    return [("text", lambda w: w.set_value("Χολαργός δυάρι"))]


def test_floor_and_age_filters_are_on_screen_without_a_search(env):
    """The home page shows every filter up front; the defaults hide 40+-year-old buildings and
    flats with no stated floor, and loosening them brings more listings back."""
    import re

    at = fresh(SEARCH)

    def count():
        m = next(m.value for m in at.markdown if 'class="hg-count"' in m.value)
        return int(re.search(r"<b>([\d.]+)</b>", m).group(1).replace(".", ""))

    def years():
        return [int(y) for m in at.markdown for y in re.findall(r"κτίριο (\d{4})", m.value)]

    assert at.number_input(key="fe_year_0").value == date.today().year - 40
    assert at.number_input(key="fe_floor_0").value == 1
    strict = count()
    assert years() and all(y >= date.today().year - 40 for y in years())
    at.number_input(key="fe_year_0").set_value(0).run()
    at.number_input(key="fe_floor_0").set_value(0).run()
    ok(at, "loosen")
    assert count() > strict
    at.number_input(key="fe_year_0").set_value(date.today().year - 10).run()
    ok(at, "new builds")
    assert years() and all(y >= date.today().year - 10 for y in years())


def test_type_and_must_have_filters_accept_any_selection(env):
    at = fresh(SEARCH)
    for label in ("Τύπος", "Να έχει"):
        ms = next(m for m in at.multiselect if m.label == label)
        ms.set_value(list(ms.options)[:3]).run()
        ok(at, label)
        next(m for m in at.multiselect if m.label == label).set_value([]).run()
        ok(at, label)


# ---- buyer UX: one score, rent/yield, unfinished, no developer text, "Δείξε όλες" ----------


def _cards(at) -> list[str]:
    return [m.value for m in at.markdown if 'class="hg-card"' in m.value]


def _card_prices(at) -> list[int]:
    import re

    return [
        int(re.search(r'class="hg-price">([\d.]+) €<', c).group(1).replace(".", ""))
        for c in _cards(at)
    ]


def _buyer_scores() -> tuple[list[dict], dict[int, int]]:
    from scout.ui import buyer, queries

    listings = queries.load_listings(include_excluded=True, only_active=True)
    return listings, buyer.buyer_scores(listings)


def test_one_score_on_map_and_cards(env):
    listings, scores = _buyer_scores()
    # the buyer score really differs from the stored thesis score somewhere (else trivial)
    assert any(scores[d["id"]] != round(d.get("score") or 0) for d in listings)
    at = fresh("Χάρτης")
    ok(at, "map")
    # the map shows up to 5 cards, none with a score, and no score legend
    cards = _cards(at)
    assert 0 < len(cards) <= 5 and not any("hg-score" in c or "Σκορ" in c for c in cards)
    assert not any("Σκορ 0–100" in c.value for c in at.caption)
    # the search cards carry no score number (its parts are not figures), but every card carries
    # the basis of each of its numbers one tap away
    at = fresh(SEARCH)
    cards = _cards(at)
    assert cards and not any("hg-score" in c or "Σκορ" in c for c in cards)
    assert all("<details><summary>Από πού βγαίνουν</summary>" in c for c in cards)
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "details")
    assert not any("hg-score" in m.value for m in at.markdown if "<style" not in m.value)


def test_yield_line_on_cards(env):
    at = fresh(SEARCH)
    cards = _cards(at)
    text = [re.sub(r"<[^>]+>", "", c) for c in cards]
    assert text and all("Ενοίκιο (εκτίμηση) ~" in c and "/μήνα · Μικτή απόδοση " in c for c in text)
    assert any("~900 €/μήνα" in c for c in cards)
    assert "Υψηλότερη απόδοση" in at.selectbox(key="sort").options
    assert "Καλύτερη αντιστοιχία" not in at.selectbox(key="sort").options


def test_unfinished_listing_is_labelled_and_ranks_low(env):
    from scout.ui import buyer

    at = fresh(SEARCH)
    assert not any("hg-st-bad" in c for c in _cards(at))  # hidden by default
    at.checkbox(key="fe_unf_0").check().run()
    at.selectbox(key="sort").set_value("Χαμηλότερη τιμή").run()
    ok(at, "unfinished shown")
    # the cheapest listing is the unfinished shell: shown first here, clearly marked
    cards = _cards(at)
    assert f'hg-st-bad">{buyer.UNFINISHED_NOTE}<' in cards[0]
    # in the suggested order it goes to the bottom
    at.selectbox(key="sort").set_value(buyer.DEFAULT_SORT).run()
    assert not any("hg-st-bad" in c for c in _cards(at))  # not among the first page
    listings, _ = _buyer_scores()
    from scout import market_intel

    intel = market_intel.build(listings)
    hits = [((100, []), d, buyer.buyer_view(d, intel)) for d in listings if not d["excluded"]]
    hits.sort(key=lambda h: buyer.SORTS[buyer.DEFAULT_SORT](h[0][0], h[2], h[1]))
    assert hits[-1][1]["is_unfinished"]
    hits.sort(key=lambda h: buyer.SORTS["Υψηλότερη απόδοση"](h[0][0], h[2], h[1]))
    assert hits[-1][1]["is_unfinished"]


def test_show_all_button_relaxes_floor_and_age(env):
    import re

    at = fresh(SEARCH)

    def count():
        m = next(m.value for m in at.markdown if 'class="hg-count"' in m.value)
        return int(re.search(r"<b>([\d.]+)</b>", m).group(1).replace(".", ""))

    before = count()
    note = next(m.value for m in at.markdown if 'class="hg-count"' in m.value)
    assert "ισόγεια/υπόγεια" in note and f"κτίριο πριν το {date.today().year - 40}" in note
    btn = at.button(key="show_all_btn")
    back = int(re.search(r"\(\+([\d.]+)\)", btn.label).group(1).replace(".", ""))
    btn.click().run()
    ok(at, "show all")
    assert count() == before + back
    ver = at.session_state["f_ver"] if "f_ver" in at.session_state else 0
    assert at.number_input(key=f"fe_floor_{ver}").value == 0
    assert at.number_input(key=f"fe_year_{ver}").value == 0
    note = next(m.value for m in at.markdown if 'class="hg-count"' in m.value)
    assert "ισόγεια" not in note and "κτίριο πριν" not in note
    # clearing brings the defaults back
    at.button(key="ex0").click().run()
    at.button(key="clear_q").click().run()
    assert count() == before


def test_compare_opens_with_favourites_and_shows_yield(env):
    import scout.shortlist as sl

    sl.set_watch("xe:g-2", True)
    sl.set_watch("xe:g-1", True)
    at = fresh("Σύγκριση")
    ok(at, "compare")
    picked = [at.selectbox(key="compare_a").value, at.selectbox(key="compare_b").value]
    assert len(set(picked)) == 2 and all(v.startswith("★ ") for v in picked)
    table = next(m.value for m in at.markdown if m.value.startswith("| | Α | Β |"))
    assert all(
        f"| {f} |" in table for f in ("Ενοίκιο (εκτίμηση)", "Μικτή απόδοση", "Καθαρή απόδοση")
    )


DEV_WORDS = ("GITHUB_TOKEN", "GITHUB", "ANTHROPIC", "agent", "Agent", "🤖", "Κατάλαβα", "token")


def test_no_developer_text_without_keys(env, monkeypatch):
    """No storage token and no AI key: plain-language copy only, AI buttons hidden, and the
    text box still narrows the results through the simple reader."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    def texts(at) -> list[str]:
        out = [m.value for m in at.markdown if not m.value.lstrip().startswith("<style")]
        for kind in ("caption", "info", "warning", "error", "success", "subheader", "title"):
            out += [e.value for e in getattr(at, kind)]
        out += [b.label for b in at.button] + [e.label for e in at.expander]
        return out

    for page in PAGES:
        at = fresh(page)
        ok(at, page)
        found = [(w, t[:80]) for t in texts(at) for w in DEV_WORDS if w in t]
        assert not found, (page, found)
        assert not any("τεχνητή νοημοσύνη" in b.label for b in at.button), page
    at = fresh(SEARCH)
    assert any("Τα αγαπημένα κρατιούνται" in c.value for c in fresh(STARRED).caption)
    # the listing page has no AI button either
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "details")
    assert not any("τεχνητή νοημοσύνη" in b.label for b in at.button)
    found = [(w, t[:80]) for t in texts(at) for w in DEV_WORDS if w in t]
    assert not found, found
    # free text without AI: area + price are read, the filters follow
    at = fresh(SEARCH)
    at.text_input(key="q_text").set_value("δυάρι στον Χολαργό έως 200.000")
    next(b for b in at.button if b.label == "Αναζήτηση").click().run()
    ok(at, "local parse")
    label = at.expander[0].label
    assert "Χολαργός" in label and "200.000" in label
    assert at.session_state["nl_filters"].bedrooms_min == 1


def test_local_parse_reads_area_price_size():
    from scout.ui.buyer import local_parse

    areas = ["Χολαργός", "Παπάγου", "Αγία Παρασκευή"]
    f = local_parse("τριάρι στο Παπάγου ή στην Αγία Παρασκευή κάτω από 250.000€ με πάρκινγκ", areas)
    assert f.areas == ["Παπάγου", "Αγία Παρασκευή"] and f.price_max == 250_000
    assert f.bedrooms_min == f.bedrooms_max == 2 and f.wants == ["parking"]
    f = local_parse("δυάρι στον Χολαργό έως 180Χ, από 60 τ.μ.", areas)
    assert (f.areas, f.price_max, f.area_min) == (["Χολαργός"], 180_000, 60)
    f = local_parse("έχω 200 χιλιάδες να επενδύσω στον Χολαργό", areas)
    assert f.budget == 200_000 and f.price_max is None
    assert local_parse("κάτι", areas) == local_parse("", [])


def test_card_shows_build_year_and_renovation_apart():
    from scout.ui import buyer

    d = {"id": 1, "price": 200_000, "floor": 2.0, "year_built": 1975, "renovated_year": 2021}
    card = buyer.card_html(d, {})
    assert "κτίριο 1975, ανακαίνιση 2021" in card
    assert "έτος: δεν δηλώνεται" in buyer.card_html({**d, "year_built": None}, {})
    assert buyer.DEFAULT_AGE == 40 and buyer.DEFAULT_FLOOR == 1


def test_listing_metric_delta_and_position_bar():
    from scout.ui import buyer

    cmp = {"ppm": 3000, "p25": 2700, "p75": 3400, "n": 6, "pct": -0.3}
    assert buyer.confidence(cmp) == "Χαμηλή"
    assert buyer.confidence({**cmp, "n": 14, "p25": 2800, "p75": 3300}) == "Υψηλή"
    assert buyer.confidence({**cmp, "n": 10}) == "Μέτρια"
    bar = buyer.position_bar(2100, cmp)
    assert "2.100 €/τ.μ." in bar and "2.700–3.400 €/τ.μ." in bar
    assert buyer.comps_text({"cmp": cmp}) == "Παρόμοια (6): 30 % κάτω"
    assert buyer.comps_text({"cmp": {**cmp, "pct": 0.12}}) == "Παρόμοια (6): 12 % πάνω"
    assert buyer.comps_text({}) == "Λίγα παρόμοια για σύγκριση"
    # st.metric reads the sign from an ASCII minus: cheaper must render green/down
    assert f"{cmp['pct']:+.0%}".startswith("-")


def test_area_pick_from_another_page_preselects_the_area(env):
    at = fresh(SEARCH)
    at.session_state["area_pick"] = "Παπάγου"
    at.run()
    ok(at, "area pick")
    ver = at.session_state["f_ver"]
    assert at.multiselect(key=f"fe_areas_{ver}").value == ["Παπάγου"]
    assert "area_pick" not in at.session_state  # applied once
    locs = _cards(at)
    assert locs and all("Παπάγου" in v for v in locs)


def test_athens_quarters_are_areas_of_their_own():
    from scout.ui import buyer

    amp = {"neighborhood": "Αθήνα (Αμπελόκηποι)", "title": "Διαμέρισμα", "price": 1}
    hal = {"neighborhood": "Χαλάνδρι (Κέντρο)", "title": "Διαμέρισμα", "price": 1}
    assert buyer.area_name(amp) == "Αμπελόκηποι" and buyer.area_name(hal) == "Χαλάνδρι"
    assert buyer._area_hit(amp, ["Αμπελόκηποι"]) and buyer._area_hit(amp, ["Αθήνα"])
    assert not buyer._area_hit(amp, ["Χαλάνδρι"]) and buyer._area_hit(hal, ["Χαλάνδρι"])
    counts = buyer._municipality_counts([amp, amp, hal])
    assert counts == {"Αμπελόκηποι": 2, "Χαλάνδρι": 1}
