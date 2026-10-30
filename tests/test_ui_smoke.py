"""Smoke test: the Streamlit app renders without crashing against a real DB.

Uses Streamlit's in-process AppTest (no browser/server). Guards the two states
that matter most: a normal render with eligible listings, and the "never blank"
path where every listing is excluded but data must still show.
"""

from __future__ import annotations

from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

from scout.config import get_settings  # noqa: E402
from scout.scoring import compute_market_stats, score  # noqa: E402

from .conftest import make_listing  # noqa: E402

# Absolute path: newer Streamlit resolves a relative AppTest path against THIS test file's
# directory (→ tests/src/...), not the repo root, so anchor it explicitly.
APP = str(Path(__file__).resolve().parents[1] / "src" / "scout" / "ui" / "app.py")


def _open(at, label: str):
    """Switch the sidebar page (the home page is now Αναζήτηση, not Opportunities)."""
    at.radio(key="page").set_value(label).run()
    return at


OPPS = "🏆 Ευκαιρίες"


def _seed_db(db_path, *, exclude_all: bool) -> None:
    import scout.db as dbmod

    dbmod._engine = None
    dbmod._SessionFactory = None
    from scout.config import load_strategy
    from scout.db import init_db, session_scope, upsert_listing_with_history

    init_db()
    strategy = load_strategy()
    listings = [
        make_listing(source_id="ui-1", price=200_000, neighborhood="Ano Cholargos"),
        make_listing(source_id="ui-2", price=180_000, neighborhood="Faneromeni"),
    ]
    stats = compute_market_stats(listings)
    with session_scope() as session:
        for lst in listings:
            row = upsert_listing_with_history(session, lst)
            scored = score(lst, stats, strategy)
            row.score = scored.score
            if exclude_all:
                row.excluded = True
                row.exclusion_reason = "too far from metro"
                row.score = 0.0
            else:
                row.excluded = scored.excluded


@pytest.fixture
def _db(tmp_path, monkeypatch):
    def _make(exclude_all: bool):
        import streamlit as st

        monkeypatch.delenv("DATABASE_URL", raising=False)  # force the SQLite fixture path
        monkeypatch.setenv("DB_PATH", str(tmp_path / "ui.db"))
        get_settings.cache_clear()
        # get_listings is @st.cache_resource (shared object, survives across AppTest
        # instances in-process) — clear BOTH cache kinds or tests leak into each other.
        st.cache_data.clear()
        st.cache_resource.clear()
        _seed_db(tmp_path / "ui.db", exclude_all=exclude_all)

    return _make


def test_app_renders_with_opportunities(_db):
    _db(exclude_all=False)
    at = _open(AppTest.from_file(APP, default_timeout=30).run(), OPPS)
    assert not at.exception
    # KPI header + ranked table present. The header leads with honest counts, not the
    # inflated "every eligible listing is an opportunity" — so assert the tracked-count and
    # the regulatory differentiator metrics render.
    labels = {m.label for m in at.metric}
    assert "Αγγελίες" in labels
    assert "Διάμεσο €/τ.μ." in labels
    assert len(at.dataframe) >= 1


def test_app_never_blank_when_all_excluded(_db):
    """All listings filtered out -> still render them with a reason, no crash."""
    _db(exclude_all=True)
    at = _open(AppTest.from_file(APP, default_timeout=30).run(), OPPS)
    assert not at.exception
    assert len(at.warning) >= 1  # the "showing all with reasons" banner
    df = at.dataframe[0].value
    assert df.shape[0] == 2
    assert "Λόγος αποκλεισμού" in list(df.columns)


def _seed_valued_db(tmp_path) -> None:
    """Seed enough comps that the hedonic model actually fits, then apply + persist
    valuations — so the confidence banner and Fair value columns render for real."""
    import scout.db as dbmod

    dbmod._engine = None
    dbmod._SessionFactory = None
    from scout.config import load_strategy
    from scout.db import init_db, session_scope, upsert_listing_with_history
    from scout.valuation import fit_and_apply_by_area

    init_db()
    strategy = load_strategy()
    listings = []
    for i in range(30):
        area = 55.0 + (i % 30)
        listings.append(
            make_listing(
                source_id=f"v-{i}",
                price=int(3000 * area) + (i % 5 - 2) * 8000,  # mostly on-line, a few off
                area_m2=area,
                floor=float(1 + i % 5),
                year_built=1990 + i % 30,
                energy_class="C",
                bedrooms=2,
                metro_distance_m=300 + (i % 6) * 50,
                neighborhood="Ano Cholargos",
                search_area="Cholargos",
            )
        )
    models = fit_and_apply_by_area(listings)
    assert models  # sanity: the fixture must actually fit a model
    stats = compute_market_stats(listings)
    with session_scope() as session:
        for lst in listings:
            row = upsert_listing_with_history(session, lst)
            scored = score(lst, stats, strategy)
            row.score = scored.score
            row.excluded = scored.excluded
            row.predicted_price = lst.predicted_price
            row.value_gap_pct = lst.value_gap_pct


def test_app_renders_fair_value_views(tmp_path, monkeypatch):
    """The fitted-model paths — confidence banner + Fair value / Value gap columns —
    render without crashing. This is the demo's headline surface."""
    import streamlit as st

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "ui.db"))
    get_settings.cache_clear()
    st.cache_data.clear()
    st.cache_resource.clear()  # get_listings is cache_resource — shared across AppTests
    _seed_valued_db(tmp_path)

    at = _open(AppTest.from_file(APP, default_timeout=30).run(), OPPS)
    assert not at.exception
    # The confidence banner is a success or warning box (fitted path), not the info stub.
    banner_text = " ".join(b.value for b in [*at.success, *at.warning])
    assert "Μοντέλο εκτιμώμενης αξίας" in banner_text
    # The product listing-card grid renders (custom HTML, not a bare dataframe).
    md = " ".join(m.value for m in at.markdown)
    assert "ph-grid" in md and "ph-card" in md
    # The table view is still available (inside the expander) with the model columns.
    # (Search all dataframes — the coverage panel also renders one.)
    assert any(
        "Εκτιμώμενη αξία" in df.value.columns and "Απόκλιση αξίας" in df.value.columns
        for df in at.dataframe
    )
