"""The unattended daily operator wires rescore + health + alerts + audit without crashing."""

from __future__ import annotations

import pytest

from scout.config import get_settings
from scout.scoring import compute_market_stats, score

from .conftest import make_listing


def test_run_daily_no_network_steps(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "daily.db"))
    get_settings.cache_clear()

    import scout.db as dbmod

    dbmod._engine = None
    dbmod._SessionFactory = None
    from scout.config import load_strategy
    from scout.db import init_db, session_scope, upsert_listing_with_history

    init_db()
    strategy = load_strategy()
    listings = [
        make_listing(
            source_id="d1", price=200_000, neighborhood="Ano Cholargos", search_area="Cholargos"
        ),
        make_listing(
            source_id="d2", price=180_000, neighborhood="Faneromeni", search_area="Cholargos"
        ),
    ]
    stats = compute_market_stats(listings)
    with session_scope() as s:
        for lst in listings:
            row = upsert_listing_with_history(s, lst)
            row.score = score(lst, stats, strategy).score

    from scripts.daily import run_daily

    # Network-free run: no enrich, no rent scrape — exercises rescore + health + alerts + audit.
    metrics = run_daily(enrich_limit=0, rent_areas=0)
    assert metrics["rescore"]["rescored"] == 2
    assert "healthy" in metrics["health"]
    assert metrics["alerts"]["sent"] == 0  # no alert sink configured in test
    assert metrics["summary"]["listings"] == 2


if __name__ == "__main__":
    pytest.main([__file__])
