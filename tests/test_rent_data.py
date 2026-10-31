"""Rentals as first-class listing rows (contract C1): migration, collector, pipeline, comps,
queries. No network: the XE rental cards are a real captured page."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.collectors.base import Collector
from scout.collectors.xe import XeCollector, parse_available_from, parse_furnished
from scout.config import Strategy
from scout.models import Base, ListingRow, RentCompRow

FIXTURE = Path(__file__).parent / "fixtures" / "xe_rent_search.html"


def _use_engine(monkeypatch, engine):
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: engine)


@pytest.fixture
def mem_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _use_engine(monkeypatch, engine)
    return engine


class TwoTypeCollector(Collector):
    source = "xe"

    def __init__(self, sales, rentals):
        super().__init__(Strategy(), save_raw=False)
        self._sales, self._rentals = sales, rentals

    def search_urls(self, strategy):
        return []

    def parse_card(self, html, base_url):
        return {}

    def collect(self) -> Iterator[dict]:
        yield from self._sales

    def collect_rentals(self) -> Iterator[dict]:
        yield from self._rentals


def _raw(sid, price, hood="Χολαργός (Τσακός)", area=80.0, **extra):
    return {
        "source": "xe",
        "source_id": sid,
        "url": f"https://www.xe.gr/property/d/x/{sid}/cholargos",
        "title": f"Διαμέρισμα {int(area)} τ.μ.",
        "price": price,
        "area_m2": area,
        "floor": 2.0,
        "year_built": 2005,
        "neighborhood": hood,
        **extra,
    }


def _rent(sid, rent, hood="Χολαργός (Τσακός)", **extra):
    return _raw(sid, rent, hood=hood, listing_type="rent", **extra)


# ---- migration -------------------------------------------------------------


def test_migration_adds_rent_columns_to_an_existing_db(tmp_path, monkeypatch):
    """A DB created before C1 (no listing_type / furnished / available_from, no index) gets
    the columns from init_db; legacy rows read as sales; running it twice is a no-op."""
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_listing_type_status"))
        for col in ("listing_type", "furnished", "available_from"):
            conn.execute(text(f"ALTER TABLE listing DROP COLUMN {col}"))
        conn.execute(
            text(
                "INSERT INTO listing (source, source_id, url, price, area_m2, first_seen,"
                " last_seen, status, search_area, excluded, score, rent_estimated,"
                " is_unfinished, is_private_seller, is_currently_rented, negotiation_score,"
                " is_opportunity, is_watched) VALUES ('xe', 'old1', 'u', 250000, 80,"
                " '2026-09-01', '2026-10-30', 'active', 'Cholargos', 0, 50, 1, 0, 0, 0, 0,"
                " 0, 0)"
            )
        )
    assert "listing_type" not in {c["name"] for c in inspect(engine).get_columns("listing")}
    _use_engine(monkeypatch, engine)

    db.init_db()
    db.init_db()  # idempotent

    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("listing")}
    assert {"listing_type", "furnished", "available_from"} <= cols
    assert "ix_listing_type_status" in {i["name"] for i in insp.get_indexes("listing")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT listing_type, furnished FROM listing")).one() == (
            "sale",
            None,
        )
    from scout.ui.queries import load_listings, load_rent_listings

    assert [d["source_id"] for d in load_listings()] == ["old1"]
    assert load_rent_listings() == []


# ---- collector ---------------------------------------------------------------


def test_real_xe_rental_cards_parse_as_full_listings():
    """Six cards captured from XE's rental search for Χολαργός (runner, 2026-10-31)."""
    xe = XeCollector(Strategy(), save_raw=False)
    cards = HTMLParser(FIXTURE.read_text(encoding="utf-8")).css(xe.CARD_SELECTOR)
    raws = [
        xe.parse_rental_card(c.html, base_url="https://www.xe.gr/property/results") for c in cards
    ]
    assert len(raws) == 6
    assert all(r["listing_type"] == "rent" for r in raws)
    assert all(r["source_id"] and r["url"].startswith("https://www.xe.gr/property/") for r in raws)
    assert all(r["price"] and 300 <= r["price"] <= 5000 for r in raws)  # monthly rent, €
    assert all(r["area_m2"] for r in raws) and all(r["neighborhood"] for r in raws)
    first = raws[0]
    assert (first["price"], first["area_m2"], first["floor"]) == (800, 51.0, 3.0)
    assert first["neighborhood"] == "Αγία Παρασκευή (Δημοδιδασκάλων)"
    assert first["is_private_seller"] is True
    tsakos = raws[1]
    assert (tsakos["price"], tsakos["bedrooms"], tsakos["year_built"]) == (1950, 2, 2008)
    # furnished from the card text: «επιπλωμένο» on three cards, silence on the rest; the
    # Blueground card also says «ανεπίπλωτα» only to compare prices — still furnished.
    assert [r["furnished"] for r in raws] == [True, True, True, None, None, None]
    assert all(r["available_from"] is None for r in raws)


def test_rental_text_helpers():
    assert parse_furnished("Διαμέρισμα, μη επιπλωμένο") is False
    assert parse_furnished("Χωρίς έπιπλα") is False
    assert parse_furnished("Διαμέρισμα 70 τ.μ.") is None
    assert parse_available_from("Διαθέσιμο από: 1/12/2026") == date(2026, 12, 1)
    assert parse_available_from("Διαθέσιμο από 31/2/2026") is None


# ---- pipeline ----------------------------------------------------------------


def test_two_type_run_stores_both_and_scores_only_the_sale(mem_db):
    from scout.pipeline import run

    sales = [_raw("s1", 250_000), _raw("s2", 260_000)]
    rentals = [_rent(f"r{i}", 900 + 50 * i, furnished=i == 0) for i in range(4)]
    summary = run(
        strategy=Strategy(),
        collectors=[TwoTypeCollector(sales, rentals)],
        use_network=False,
        observed_at=datetime(2026, 10, 31, 9),
        area="Cholargos",
    )
    assert summary["stored"] == 2 and summary["rentals_stored"] == 4
    with sessionmaker(bind=mem_db, future=True)() as s:
        rows = {r.source_id: r for r in s.scalars(select(ListingRow)).all()}
        assert {k for k, r in rows.items() if r.listing_type == "rent"} == {"r0", "r1", "r2", "r3"}
        for k in ("s1", "s2"):
            assert rows[k].listing_type == "sale" and not rows[k].excluded
            assert rows[k].score > 0 and rows[k].gross_yield
        for k in ("r0", "r1", "r2", "r3"):
            r = rows[k]
            assert r.excluded and r.exclusion_reason == "rent" and r.score == 0
            assert r.gross_yield is None and r.est_monthly_rent is None
            assert r.search_area == "Cholargos" and r.status == "active"
        assert rows["r0"].furnished is True and rows["r1"].furnished is False
        # the sale yield uses the stored rentals' median: (950+1000)/2 €/80 m², on 80 m²
        comp = s.scalar(select(RentCompRow).where(RentCompRow.neighborhood.is_(None)))
        assert comp.samples == 4 and comp.updated_at == datetime(2026, 10, 31, 9)
        assert rows["s1"].est_monthly_rent == 975


def test_a_run_without_rentals_retires_no_rentals_and_vice_versa(mem_db):
    """Sales and rentals retire in their own passes: a failed rental search must not retire
    the stored rentals, and a rental-only result must not retire the sales."""
    from scout.pipeline import run

    def go(sales, rentals, day):
        return run(
            strategy=Strategy(),
            collectors=[TwoTypeCollector(sales, rentals)],
            use_network=False,
            observed_at=datetime(2026, 10, day),
            area="Cholargos",
        )

    go([_raw("s1", 250_000)], [_rent("r1", 900), _rent("r2", 950)], 1)
    assert go([_raw("s1", 250_000)], [], 2)["rentals_gone"] == 0
    assert go([], [_rent("r1", 900)], 3)["marked_gone"] == 0
    with sessionmaker(bind=mem_db, future=True)() as s:
        status = {r.source_id: r.status for r in s.scalars(select(ListingRow)).all()}
    assert status == {"s1": "active", "r1": "active", "r2": "gone"}  # r2 unseen on day 3


def test_rental_price_change_appends_history_once(mem_db):
    from scout.models import PriceHistoryRow
    from scout.pipeline import run

    for day, rent in ((1, 900), (2, 900), (3, 850)):
        run(
            strategy=Strategy(),
            collectors=[TwoTypeCollector([], [_rent("r1", rent)])],
            use_network=False,
            observed_at=datetime(2026, 10, day),
            area="Cholargos",
        )
    with sessionmaker(bind=mem_db, future=True)() as s:
        prices = [p.price for p in s.scalars(select(PriceHistoryRow)).all()]
    assert prices == [900, 850]


# ---- rent comps --------------------------------------------------------------


def test_rent_comps_come_from_stored_rentals_of_the_last_60_days(mem_db):
    from scout.db import session_scope, upsert_listing_with_history
    from scout.normalize import normalize
    from scout.rent_comps import basis_text, comp_basis, recompute_from_stored
    from scout.ui.queries import load_rent_comp_rows

    seen = {
        "a": datetime(2026, 10, 30),
        "b": datetime(2026, 10, 20),
        "c": datetime(2026, 10, 10),
        "old": datetime(2026, 8, 1),  # > 60 days before 31/10: does not count
    }
    with session_scope() as s:
        for sid, when in seen.items():
            rent = 3000 if sid == "old" else 1000
            lst = normalize(_rent(sid, rent), now=when)
            lst.search_area = "Cholargos"
            upsert_listing_with_history(s, lst, observed_at=when)
        sale = normalize(_raw("sale", 300_000), now=seen["a"])  # a sale never counts
        sale.search_area = "Cholargos"
        upsert_listing_with_history(s, sale, observed_at=seen["a"])

    comps = recompute_from_stored("Cholargos", now=datetime(2026, 10, 31))
    assert comps["__overall__"] == pytest.approx(1000 / 80)
    assert comps["Χολαργός (Τσακός)"] == pytest.approx(1000 / 80)
    rows = load_rent_comp_rows()
    assert {(r["neighborhood"], r["samples"]) for r in rows} == {
        (None, 3),
        ("Χολαργός (Τσακός)", 3),
    }
    assert all(r["updated_at"] == datetime(2026, 10, 30) for r in rows)
    assert comp_basis(rows, "Cholargos", "Χολαργός (Τσακός)") == "ενοίκια έως 30/10, 3 αγγελίες"
    assert comp_basis(rows, "Cholargos", "Αλλού") == "ενοίκια έως 30/10, 3 αγγελίες"
    assert comp_basis(rows, "Galatsi", None) == ""
    assert basis_text(datetime(2026, 1, 5), 1) == "ενοίκια έως 05/01, 1 αγγελία"
    assert basis_text(None, 4) == ""
    # an area with no recent rentals writes nothing (earlier comps are never wiped)
    assert recompute_from_stored("Galatsi", now=datetime(2026, 10, 31)) == {}


# ---- queries -----------------------------------------------------------------


def test_load_rent_listings_has_sale_keys_plus_rental_keys(mem_db):
    from scout.pipeline import run
    from scout.ui.queries import load_listings, load_rent_listings

    run(
        strategy=Strategy(),
        collectors=[
            TwoTypeCollector(
                [_raw("s1", 250_000)],
                [_rent("r1", 1000, furnished=True, available_from=date(2026, 12, 1))],
            )
        ],
        use_network=False,
        observed_at=datetime(2026, 10, 31),
        area="Cholargos",
    )
    sales, rents = load_listings(), load_rent_listings()
    assert [d["source_id"] for d in sales] == ["s1"]
    assert [d["source_id"] for d in rents] == ["r1"]
    r = rents[0]
    assert set(sales[0]) <= set(r)
    assert set(r) - set(sales[0]) == {"rent_per_m2"}
    assert r["listing_type"] == "rent" and sales[0]["listing_type"] == "sale"
    assert r["price"] == 1000 and r["rent_per_m2"] == 12.5
    assert r["furnished"] is True and r["available_from"] == date(2026, 12, 1)
    assert r["page_checked"] is False and r["is_fresh"] is True
    assert r["days_on_market"] is not None and r["dom_basis"] == "seen"
    assert r["gross_yield"] is None and r["rec_verdict"] is None and r["deal_grade"] is None


LIVE = Path(os.environ.get("LIVE_DB", Path(__file__).resolve().parents[1] / "data/listings.db"))


@pytest.mark.skipif(not LIVE.exists(), reason="published DB not downloaded (docs/COORDINATION.md)")
def test_migration_on_the_published_db(tmp_path, monkeypatch):
    """init_db on a copy of the real published SQLite: the columns appear, every existing
    row is a sale, the sale loader returns them all and the rent loader none."""
    import shutil

    copy = tmp_path / "live.db"
    shutil.copy(LIVE, copy)
    engine = create_engine(f"sqlite:///{copy}", future=True)
    _use_engine(monkeypatch, engine)
    with engine.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM listing WHERE status='active'")).scalar()
    db.init_db()
    db.init_db()
    with engine.connect() as conn:
        types = dict(
            conn.execute(text("SELECT listing_type, count(*) FROM listing GROUP BY 1")).all()
        )
    assert set(types) <= {"sale", "rent"} and types.get("sale")
    from scout.ui.queries import load_listings, load_rent_listings

    with engine.connect() as conn:
        active_rent = conn.execute(
            text("SELECT count(*) FROM listing WHERE status='active' AND listing_type='rent'")
        ).scalar()
    sales = load_listings(collapse_relistings=False)
    rents = load_rent_listings(collapse_relistings=False)
    assert len(sales) == before - active_rent and len(rents) == active_rent
    assert all(d["listing_type"] == "sale" for d in sales)
    assert all(d["listing_type"] == "rent" for d in rents)
