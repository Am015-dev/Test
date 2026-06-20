"""Integration test for the pipeline using a fake collector (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.collectors.base import Collector
from scout.config import Strategy
from scout.models import Base, ListingRow, PriceHistoryRow


class FakeCollector(Collector):
    source = "spitogatos"

    def __init__(self, strategy, rows, source=None):
        super().__init__(strategy, save_raw=False)
        self._rows = rows
        if source is not None:
            self.source = source

    def search_urls(self, strategy):
        return []

    def parse_card(self, html, base_url):
        return {}

    def collect(self) -> Iterator[dict]:
        yield from self._rows


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    """Point scout.db at a shared in-memory SQLite for the whole test."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", Session)
    # init_db / get_engine should not recreate the engine.
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    yield engine


def _raw(source_id, price, floor=2.0, area=80.0, source="spitogatos"):
    return {
        "source": source,
        "source_id": source_id,
        "url": f"https://www.spitogatos.gr/p/{source_id}",
        "title": f"Flat {source_id} Ano Cholargos",
        "price": price,
        "area_m2": area,
        "floor": floor,
        "neighborhood": "Ano Cholargos",
        "lat": 37.9997,
        "lng": 23.7960,
        "listed_rent": 850,
        "is_currently_rented": True,
    }


def _count(engine, model):
    with sessionmaker(bind=engine, future=True)() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_pipeline_stores_and_scores(in_memory_db):
    from scout.pipeline import run

    collector = FakeCollector(Strategy(), [_raw("a", 200_000), _raw("b", 250_000)])
    summary = run(
        strategy=Strategy(),
        collectors=[collector],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
    )
    assert summary["stored"] == 2
    assert _count(in_memory_db, ListingRow) == 2
    assert _count(in_memory_db, PriceHistoryRow) == 2

    with sessionmaker(bind=in_memory_db, future=True)() as s:
        rows = s.scalars(select(ListingRow)).all()
        assert all(r.metro_distance_m is not None for r in rows)  # enriched offline
        assert all(r.score > 0 for r in rows)  # passes hard filters


def test_pipeline_is_idempotent(in_memory_db):
    from scout.pipeline import run

    rows = [_raw("a", 200_000)]
    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), rows)],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
    )
    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), rows)],
        use_network=False,
        observed_at=datetime(2026, 6, 2),
    )
    # Same price both runs -> only one price_history row.
    assert _count(in_memory_db, PriceHistoryRow) == 1


def test_pipeline_records_price_drop(in_memory_db):
    from scout.pipeline import run

    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), [_raw("a", 200_000)])],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
    )
    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), [_raw("a", 180_000)])],
        use_network=False,
        observed_at=datetime(2026, 6, 2),
    )
    assert _count(in_memory_db, PriceHistoryRow) == 2


def test_blocked_portal_does_not_wipe_other_portals_data(in_memory_db):
    """Regression: a portal returning nothing must not retire prior listings.

    Run 1 collects a spitogatos listing. Run 2: spitogatos returns nothing
    (blocked) and only xe returns data. The spitogatos listing must stay active.
    """
    from scout.pipeline import run

    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), [_raw("a", 200_000)])],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
    )
    # Run 2: spitogatos yields nothing; xe brings a fresh listing.
    run(
        strategy=Strategy(),
        collectors=[
            FakeCollector(Strategy(), [], source="spitogatos"),
            FakeCollector(Strategy(), [_raw("z", 210_000, source="xe")], source="xe"),
        ],
        use_network=False,
        observed_at=datetime(2026, 6, 2),
    )
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        by_key = {(r.source, r.source_id): r for r in s.scalars(select(ListingRow)).all()}
        # The spitogatos listing survived the blocked run.
        assert by_key[("spitogatos", "a")].status == "active"
        # The new xe listing was stored and is active.
        assert by_key[("xe", "z")].status == "active"


def test_unscoped_run_does_not_retire_other_areas(in_memory_db):
    """Regression: a plain run() (area=None) must retire only the default
    municipality's listings, never other areas' live inventory."""
    from scout.pipeline import run

    def _run(rows, area, day):
        run(
            strategy=Strategy(),
            collectors=[FakeCollector(Strategy(), rows, source="xe")],
            use_network=False,
            observed_at=datetime(2026, 6, day),
            area=area,
        )

    _run([_raw("a", 200_000, source="xe")], area="Cholargos", day=1)
    _run([_raw("b", 210_000, source="xe")], area="Papagou", day=1)
    # Unscoped run (defaults to municipality "Cholargos") that only re-sees 'a'.
    _run([_raw("a", 200_000, source="xe")], area=None, day=2)

    with sessionmaker(bind=in_memory_db, future=True)() as s:
        by_key = {(r.source, r.source_id): r for r in s.scalars(select(ListingRow)).all()}
        assert by_key[("xe", "a")].status == "active"
        assert by_key[("xe", "a")].search_area == "Cholargos"
        # Papagou's listing is in a different area and must survive the Cholargos run.
        assert by_key[("xe", "b")].status == "active"
        assert by_key[("xe", "b")].search_area == "Papagou"


def test_legacy_null_search_area_backfilled_then_scoped_retired(in_memory_db):
    """Rows predating per-area tagging (search_area NULL) get tagged on the default
    municipality's run, so scoped retirement can still reach them once they vanish."""
    from scout.pipeline import run

    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), [_raw("a", 200_000, source="xe")], source="xe")],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
        area="Cholargos",
    )
    # Simulate a pre-migration row: clear its search_area.
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        s.query(ListingRow).update({ListingRow.search_area: None})
        s.commit()
    # Unscoped run sees a different xe listing (so 'xe' is active) but not 'a'.
    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), [_raw("c", 205_000, source="xe")], source="xe")],
        use_network=False,
        observed_at=datetime(2026, 6, 2),
    )
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        by_key = {(r.source, r.source_id): r for r in s.scalars(select(ListingRow)).all()}
        assert by_key[("xe", "a")].search_area == "Cholargos"  # backfilled
        assert by_key[("xe", "a")].status == "gone"  # then retired within its area


def test_pipeline_excludes_ground_floor(in_memory_db):
    from scout.pipeline import run

    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), [_raw("g", 200_000, floor=0.0)])],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
    )
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        row = s.scalar(select(ListingRow))
        assert row.excluded
        assert row.exclusion_reason == "ground/low floor"
