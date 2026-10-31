"""C13: the speed work must not change a single result.

On the published DB (``data/listings.db``, skipped when absent) the real app is driven with
AppTest and the first ten picks of the guide (the owner's two answer sets) and the first ten
search hits (the landing list and the two example searches) are compared with
``fixtures/speed_golden.json``, captured on the code before the caches. The golden also pins a
fingerprint of the DB (active sale rows, newest ``last_seen``): another day's DB is a different
data set, so the comparison is skipped there instead of failing. ``SPEED_GOLDEN=write`` rewrites
the golden (only on the pre-cache code). The buyer score of every listing is compared by hash,
and so (on the golden's own date: cards carry relative dates) is the HTML of every card shown.
Also covered: the map's ranked list and the compare page's default pair.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "listings.db"
APP = str(ROOT / "src" / "scout" / "ui" / "app.py")
GOLDEN = Path(__file__).parent / "fixtures" / "speed_golden.json"

pytestmark = pytest.mark.skipif(not DB.exists(), reason="needs the published DB in data/")

ANSWERS = {
    "guide-160k-rail-new": {"budget": 160_000, "where": "rail", "age": 10},
    "guide-250k-best-any": {"budget": 250_000, "where": "best", "age": None},
}
SEARCHES = {
    "search-landing": None,
    "search-typed": "δυάρι στον Χολαργό έως 180.000 €, από 60 τ.μ., με ανελκυστήρα",
    "search-example-1": "δυάρι στον Χολαργό έως 180Χ με ανελκυστήρα",
    "search-example-2": "έχω 200 χιλιάδες να επενδύσω στον Χολαργό",
    "search-3bed-250k": "τριάρι έως 250 χιλ.",
    "search-marousi": "δυάρι στο Μαρούσι έως 200.000 €",
}


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    """The published DB, read through the app's own settings; secrets out of the way."""
    import streamlit as st

    from scout import db as dbmod
    from scout.config import get_settings

    mp = pytest.MonkeyPatch()
    for var in ("DATABASE_URL", "GITHUB_TOKEN", "ANTHROPIC_API_KEY", "GIST_ID"):
        mp.delenv(var, raising=False)
    mp.setenv("DB_PATH", str(DB))
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._SessionFactory = None
    # A fresh mtime keeps remote_db from replacing the file with today's download mid-test.
    os.utime(DB)
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()
    mp.undo()
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._SessionFactory = None


def _fingerprint() -> dict:
    from sqlalchemy import func, select

    from scout.db import init_db, session_scope
    from scout.models import ListingRow

    init_db()
    with session_scope() as s:
        q = select(func.count(), func.max(ListingRow.last_seen)).where(
            ListingRow.listing_type == "sale", ListingRow.status == "active"
        )
        n, last = s.execute(q).one()
    return {"active_sale": n, "last_seen": str(last)}


def _cards(at) -> str:
    """Hash of every card's HTML on the page, in order (scores, prices, comparables)."""
    cards = [m.value for m in at.markdown if 'class="hg-price"' in m.value]
    return hashlib.sha256("\n".join(cards).encode()).hexdigest()


def _guide_ids(answers: dict) -> tuple[list[str], str]:
    from scout.ui import guide

    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["guide"] = {
        **guide.DEFAULTS,
        "mode": "buy",
        "step": 5,
        "goal": "yield",
        **answers,
    }
    at.run()
    assert not at.exception, at.exception
    keys = [b.key.removeprefix("pick-det-") for b in at.button if b.key.startswith("pick-det-")]
    return keys[:10], _cards(at)


def _page(page: str):
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["page"] = page
    at.run()
    assert not at.exception, at.exception
    return at


def _map() -> tuple[list[str], str]:
    at = _page("Χάρτης")
    keys = [b.key.removeprefix("map-l-2-") for b in at.button if b.key.startswith("map-l-2-")]
    return keys[:10], _cards(at)


def _compare() -> tuple[list[str], str]:
    at = _page("Σύγκριση")
    return [at.selectbox(key="compare_a").value, at.selectbox(key="compare_b").value], _cards(at)


def _search_ids(text: str | None) -> tuple[list[str], str]:
    at = _page("Αναζήτηση")
    if text is not None:
        at.text_input(key="q_text").input(text)
        next(b for b in at.button if b.label == "Αναζήτηση").click()
        at.run()
        assert not at.exception, at.exception
    keys = [b.key.removeprefix("s-1-") for b in at.button if b.key.startswith("s-1-")]
    return keys[:10], _cards(at)


def _guide_listing_ids(keys: list[str], listings: list[dict]) -> list[str]:
    """pick-det-<id> carries the row id; the golden keeps the portal key (stable)."""
    by_id = {str(d["id"]): f"{d['source']}:{d['source_id']}" for d in listings}
    return [by_id.get(k, k) for k in keys]


def _scores_hash(listings: list[dict]) -> str:
    from scout.ui import buyer

    scores = buyer.buyer_scores(listings)
    rows = sorted(f"{d['source']}:{d['source_id']}={scores[d['id']]}" for d in listings)
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def _observed() -> dict:
    from scout.ui import queries

    fp = _fingerprint()
    listings = queries.load_listings(include_excluded=True, only_active=True)
    out = {"fingerprint": fp, "date": str(date.today()), "scores_sha256": _scores_hash(listings)}
    cards = {}
    for name, answers in ANSWERS.items():
        keys, cards[name] = _guide_ids(answers)
        out[name] = _guide_listing_ids(keys, listings)
    for name, text in SEARCHES.items():
        out[name], cards[name] = _search_ids(text)
    out["map"], cards["map"] = _map()
    out["compare"], cards["compare"] = _compare()
    out["cards_sha256"] = cards
    return out


def test_results_identical_to_golden(published):
    seen = _observed()
    if os.environ.get("SPEED_GOLDEN") == "write":
        GOLDEN.write_text(json.dumps(seen, ensure_ascii=False, indent=1) + "\n")
        pytest.skip("golden written")
    golden = json.loads(GOLDEN.read_text())
    if seen["fingerprint"] != golden["fingerprint"]:
        pytest.skip(f"another data set than the golden's ({seen['fingerprint']})")
    assert any(seen[k] for k in (*ANSWERS, *SEARCHES)), "nothing rendered at all"
    for key in ("scores_sha256", *ANSWERS, *SEARCHES, "map", "compare"):
        assert seen[key] == golden[key], key
    if seen["date"] == golden["date"]:  # cards say «σήμερα» / «πριν από N ημέρες»
        assert seen["cards_sha256"] == golden["cards_sha256"]
