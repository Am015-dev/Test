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
SEARCH, SHORTLIST, STARRED = "🔎 Αναζήτηση", "🤖 Shortlist", "⭐ Αγαπημένα"
DETAIL = "🏠 Αγγελία"
PAGES = [
    SEARCH,
    SHORTLIST,
    STARRED,
    "🗺 Χάρτης",
    DETAIL,
    "📊 Αγορά",
    "🏆 Ευκαιρίες",
    "📰 Σήμερα",
    "💼 Deals",
    "⚖️ Σύγκριση",
]
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
                search_area=areas[i % 3],
                is_private_seller=bool(i % 2),
                price_per_m2=price / a,
                image_url="https://example.com/p.jpg" if i % 5 == 0 else None,
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
    return fake


def fresh(page: str):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    if page != SEARCH:
        at.radio(key="page").set_value(page).run()
    return at


def ok(at, where: str) -> None:
    assert not at.exception, f"{where}: " + " | ".join(e.value[:300] for e in at.exception)


def test_every_page_renders(env):
    for page in PAGES:
        at = fresh(page)
        ok(at, page)
        assert len(at.main) > 0, page


def test_buyer_journey(env):
    """Search → card actions → details → star → favourites → agent → shortlist review → delete."""
    at = fresh(SEARCH)
    # landing state shows the best listings with working card buttons
    assert any(b.label == "☆ Αγαπημένο" for b in at.button)
    # an example search runs and shows what was understood
    at.button(key="ex0").click().run()
    ok(at, "example")
    assert any("Κατάλαβα" in m.value for m in at.markdown)
    # star the first result
    next(b for b in at.button if b.label == "☆ Αγαπημένο").click().run()
    ok(at, "star")
    assert any(b.label == "★ Αφαίρεση" for b in at.button)
    # it is on the favourites page and persisted in the gist
    at.radio(key="page").set_value(STARRED).run()
    ok(at, "favourites")
    assert at.metric[0].value == "1"
    # open its details from the favourites page
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "details")
    assert at.session_state["page"] == DETAIL
    # unstar from the detail page checkbox
    at.checkbox[0].uncheck().run()
    ok(at, "unstar")
    at.radio(key="page").set_value(STARRED).run()
    assert any("Δεν έχεις αγαπημένα" in i.value for i in at.info)
    # save the search for the agent
    at.radio(key="page").set_value(SEARCH).run()
    at.button(key="save_mandate").click().run()
    ok(at, "save mandate")
    assert any("Αποθηκεύτηκε" in s.value for s in at.success)
    # shortlist: the mandate shows with picks; approve one, reject one
    at.radio(key="page").set_value(SHORTLIST).run()
    ok(at, "shortlist")
    next(b for b in at.button if b.label == "✅ Έγκριση").click().run()
    ok(at, "approve")
    next(b for b in at.button if b.label == "❌ Απόρριψη").click().run()
    ok(at, "reject")
    assert any("✅ 1" in e.label and "❌ 1" in e.label for e in at.expander)
    # the approved one is now starred
    at.radio(key="page").set_value(STARRED).run()
    assert at.metric[0].value == "1"
    # delete the mandate
    at.radio(key="page").set_value(SHORTLIST).run()
    next(b for b in at.button if b.label.startswith("🗑")).click().run()
    ok(at, "delete")
    assert any("Καμία αποθηκευμένη αναζήτηση" in i.value for i in at.info)


def test_search_filter_editor_sort_and_clear(env):
    at = fresh(SEARCH)
    at.button(key="ex0").click().run()
    ver = at.session_state["f_ver"]
    at.number_input(key=f"fe_pmax_{ver}").set_value(150_000).run()
    ok(at, "price filter")
    at.selectbox(key="sort").set_value("Χαμηλότερη τιμή").run()
    ok(at, "sort")
    prices = [m.value for m in at.markdown if m.value.startswith("### ") and m.value.endswith(" €")]
    assert prices, "no result cards shown"
    nums = [int(p.replace("### ", "").replace(" €", "").replace(".", "")) for p in prices]
    assert nums == sorted(nums) and all(n <= 150_000 for n in nums)
    at.button(key="clear_q").click().run()
    ok(at, "clear")
    assert "nl_filters" not in at.session_state


def test_compare_lines_up_every_picked_listing(env):
    """Two flats in the same neighbourhood used to share one column (the later overwrote it),
    and the mixed int/"—" days-on-market row broke Arrow serialisation."""
    at = fresh("⚖️ Σύγκριση")
    picks = at.multiselect[0].options[:4]
    at.multiselect[0].set_value(picks).run()
    ok(at, "compare")
    cols = list(at.dataframe[0].value.columns)
    assert len(cols) == len(set(cols)) == 4, cols


ADMIN_PAGES = ["⚙️ Strategy", "🛠 Debug"]  # only listed with ?admin=1


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
