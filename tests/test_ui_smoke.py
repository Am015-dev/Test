"""Smoke test: the Streamlit app renders without crashing against a real DB.

Uses Streamlit's in-process AppTest (no browser/server). Guards the two states
that matter most: a normal render with eligible listings, and the "never blank"
path where every listing is excluded but data must still show.
"""

from __future__ import annotations

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

from scout.config import get_settings  # noqa: E402
from scout.scoring import compute_market_stats, score  # noqa: E402

from .conftest import make_listing  # noqa: E402

APP = "src/scout/ui/app.py"


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

        monkeypatch.setenv("DB_PATH", str(tmp_path / "ui.db"))
        get_settings.cache_clear()
        st.cache_data.clear()  # get_listings is @st.cache_data — don't leak across tests
        _seed_db(tmp_path / "ui.db", exclude_all=exclude_all)

    return _make


def test_app_renders_with_opportunities(_db):
    _db(exclude_all=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    # KPI header + ranked table present.
    assert any(m.label == "Opportunities" for m in at.metric)
    assert len(at.dataframe) >= 1


def test_app_never_blank_when_all_excluded(_db):
    """All listings filtered out -> still render them with a reason, no crash."""
    _db(exclude_all=True)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.warning) >= 1  # the "showing all with reasons" banner
    df = at.dataframe[0].value
    assert df.shape[0] == 2
    assert "Filtered out" in list(df.columns)
