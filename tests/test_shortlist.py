from __future__ import annotations

from scout.nl_search import SearchFilters
from scout.shortlist import Mandate, digest, pick


def L(i, price, score=50, **kw):
    return {
        "id": i,
        "price": price,
        "score": score,
        "neighborhood": "Χολαργός",
        "url": f"u{i}",
        "excluded": False,
        **kw,
    }


def test_pick_ranks_filters_and_skips():
    ls = [L(1, 100_000, 40), L(2, 120_000, 70), L(3, 300_000, 99), L(4, 90_000, 80, excluded=True)]
    f = SearchFilters(price_max=200_000)
    assert [d["id"] for d, _, _ in pick(f, ls, set())] == [2, 1]
    assert [d["id"] for d, _, _ in pick(f, ls, {2})] == [1]
    assert len(pick(f, ls, set(), n=1)) == 1


def test_digest_lists_picks():
    f = SearchFilters()
    txt = digest(Mandate(1, "δυάρι", f), pick(f, [L(1, 100_000)], set()))
    assert "δυάρι" in txt and "100,000" in txt and "u1" in txt


def test_seen_covers_sent_approved_rejected():
    assert Mandate(1, "x", SearchFilters(), {1}, {2}, {3}).seen == {1, 2, 3}


def test_mandate_table_is_created_on_first_use(tmp_path, monkeypatch):
    # Simulates the deployed dashboard: DB exists, init_db never ran, no `mandate` table yet.
    import scout.db as db
    import scout.shortlist as sl
    from scout.config import get_settings

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    get_settings.cache_clear()
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(sl, "_table_ready", False)
    assert sl.list_mandates() == []
    mid = sl.save_mandate("δυάρι", SearchFilters(price_max=1))
    assert [m.id for m in sl.list_mandates()] == [mid]
