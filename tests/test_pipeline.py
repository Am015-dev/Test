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
        # On the Holargos metro station, so the listing passes the ≤600m hard filter
        # (keep in sync with enrich.METRO_STATIONS["Μετρό Χολαργός"]).
        "lat": 38.0049,
        "lng": 23.7947,
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


def test_per_area_worker_does_not_steal_null_tagged_rows(in_memory_db):
    """Regression (CRITICAL): a per-area worker runs as run_for_area does — it sets the
    strategy municipality equal to its area AND passes area=<that area>. The one-time
    legacy backfill must NOT fire for it, or it would re-tag another area's NULL-tagged
    live rows to itself and retire them in the same pass."""
    from scout.pipeline import run

    # Seed a Cholargos listing, then simulate it as a pre-migration (NULL search_area) row.
    run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), [_raw("a", 200_000, source="xe")], source="xe")],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
        area="Cholargos",
    )
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        s.query(ListingRow).update({ListingRow.search_area: None})
        s.commit()

    # A Papagou worker (run_for_area semantics: municipality mutated to "Papagou").
    papagou = Strategy()
    papagou.search.municipality = "Papagou"
    run(
        strategy=papagou,
        collectors=[FakeCollector(papagou, [_raw("b", 210_000, source="xe")], source="xe")],
        use_network=False,
        observed_at=datetime(2026, 6, 2),
        area="Papagou",
    )

    with sessionmaker(bind=in_memory_db, future=True)() as s:
        by_key = {(r.source, r.source_id): r for r in s.scalars(select(ListingRow)).all()}
        # The legacy Cholargos row was neither re-tagged to Papagou nor retired.
        assert by_key[("xe", "a")].status == "active"
        assert by_key[("xe", "a")].search_area != "Papagou"


def test_one_bad_flush_does_not_crash_run_or_lose_good_listings(in_memory_db, monkeypatch):
    """Regression (CRITICAL): a single failed flush (duplicate-key race) must not poison
    the session and roll back the whole run. The good listings around it still persist
    and run() returns its summary instead of raising."""
    import scout.pipeline as pipeline

    real_upsert = pipeline.upsert_listing_with_history

    def flaky_upsert(session, listing, observed_at=None):
        row = real_upsert(session, listing, observed_at=observed_at)
        if listing.source_id == "bad":
            # Force a UNIQUE(source, source_id) violation on flush — the exact
            # duplicate-key race the per-listing SAVEPOINT must contain.
            session.add(
                ListingRow(
                    source=listing.source,
                    source_id=listing.source_id,
                    url="u",
                    price=1,
                    area_m2=1.0,
                    first_seen=observed_at,
                    last_seen=observed_at,
                    status="active",
                )
            )
            session.flush()
        return row

    monkeypatch.setattr(pipeline, "upsert_listing_with_history", flaky_upsert)

    rows = [_raw("good1", 200_000), _raw("bad", 210_000), _raw("good2", 220_000)]
    summary = pipeline.run(
        strategy=Strategy(),
        collectors=[FakeCollector(Strategy(), rows)],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
    )

    assert summary["stored"] == 2  # both good listings stored; the bad one skipped
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        keys = {(r.source, r.source_id) for r in s.scalars(select(ListingRow)).all()}
    assert ("spitogatos", "good1") in keys
    assert ("spitogatos", "good2") in keys
    assert ("spitogatos", "bad") not in keys


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


def test_pipeline_stores_rent_comp_sample_counts(in_memory_db, monkeypatch):
    """rent_comp.samples used to be 0 for every pipeline-scraped area: the counts were
    computed but never passed to save_rent_comps, so the UI could not say what n a rent
    median rests on."""
    import scout.enrich as enrich
    from scout.models import RentCompRow
    from scout.pipeline import run

    def no_net(*a, **k):
        raise enrich.requests.RequestException("no network in tests")

    monkeypatch.setattr(enrich.requests, "get", no_net)

    class RentingCollector(FakeCollector):
        def collect_rent_rows(self):
            hoods = ["Ano Cholargos"] * 4 + ["Tsakos"] * 2
            return [
                {"rent": 1000 + 50 * i, "area_m2": 80, "neighborhood": h}
                for i, h in enumerate(hoods)
            ]

    run(
        strategy=Strategy(),
        collectors=[RentingCollector(Strategy(), [_raw("a", 200_000)])],
        use_network=True,
        observed_at=datetime(2026, 6, 1),
        area="Cholargos",
    )
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        rows = {r.neighborhood: r.samples for r in s.scalars(select(RentCompRow)).all()}
    assert rows == {None: 6, "Ano Cholargos": 4}  # Tsakos: 2 < 3, no own median


def test_same_flat_on_two_portals_is_stored_once_per_portal(in_memory_db):
    """The fuzzy dedup only decides which copy counts in market stats; it must not drop a
    portal's listing. Both rows are stored (the UI groups them as twins), both are seen."""
    from scout.pipeline import run

    xe = FakeCollector(Strategy(), [_raw("x1", 250_000, source="xe")], source="xe")
    gh = FakeCollector(Strategy(), [_raw("g1", 245_000, source="goldenhome")], source="goldenhome")
    summary = run(
        strategy=Strategy(),
        collectors=[xe, gh],
        use_network=False,
        observed_at=datetime(2026, 6, 1),
    )
    assert summary["deduped"] == 1  # one physical flat for market stats
    assert summary["stored"] == 2
    with sessionmaker(bind=in_memory_db, future=True)() as s:
        rows = s.scalars(select(ListingRow)).all()
        assert sorted(r.source for r in rows) == ["goldenhome", "xe"]
        assert all(r.status == "active" and r.score is not None for r in rows)
