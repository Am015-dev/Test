"""What the listing page says (description), how many photos it has, and when it was read —
parsed from the page, stored without being blanked by card sightings, exposed to the UI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.collectors.parse_helpers import clean_description
from scout.collectors.xe import XeCollector, parse_detail_jsonld, parse_photo_count
from scout.models import Base, ListingRow
from scout.normalize import normalize
from scout.ui.queries import load_listings

from .conftest import make_listing

FIXTURES = Path(__file__).parent / "fixtures"
OFFPLAN = (FIXTURES / "xe_detail_offplan.html").read_text(encoding="utf-8")


# --- parsers ----------------------------------------------------------------------------


def test_photo_count_is_the_listings_own_jsonld_photos_not_stray_image_counts():
    # the page's image_count values (25, 19, 6) are similar ads'; this ad lists 2 photos
    # (3 URLs: one photo in two formats + one png)
    assert "&quot;image_count&quot;:25" in OFFPLAN
    assert parse_photo_count(OFFPLAN) == 2


def test_photo_count_ignores_a_larger_image_count_even_when_it_comes_first():
    html = OFFPLAN.replace(
        '<div id="app-state"', '<i data-x="{&quot;image_count&quot;:40}"></i><div id="app-state"'
    )
    assert parse_photo_count(html) == 2


def test_photo_count_counts_distinct_jsonld_photos_on_the_older_real_page():
    # the older real fixture's JSON-LD lists 19 photos of its own, while the page holds
    # ~240 photo URLs of "similar listings" that must not be counted
    html = (FIXTURES / "xe_detail.html").read_text(encoding="utf-8")
    assert parse_photo_count(html) == 19


def test_photo_count_unknown_without_listing_data():
    assert parse_photo_count("<html><body>τίποτα</body></html>") is None
    assert parse_photo_count('<i data-x="{&quot;image_count&quot;:7}"></i>') is None


def test_clean_description_collapses_whitespace_and_caps_length():
    assert clean_description("Α1 95τμ \n\n ΠΑΡΑΔΟΣΗ\tΤΕΛΗ 27-ΑΡΧΕΣ 28") == (
        "Α1 95τμ ΠΑΡΑΔΟΣΗ ΤΕΛΗ 27-ΑΡΧΕΣ 28"
    )
    assert clean_description("  \n ") is None and clean_description(None) is None
    assert len(clean_description("λ" * 5000)) == 1500


def test_enrich_from_detail_fills_description_and_photo_count(monkeypatch):
    collector = XeCollector.__new__(XeCollector)
    monkeypatch.setattr(collector, "_fetch_detail", lambda session, url: OFFPLAN)
    raw = {"url": "https://www.xe.gr/property/d/poliseis-katoikion/999000111/neo-irakleio"}
    collector._enrich_from_detail(None, raw)
    assert raw["photo_count"] == 2
    assert raw["description"].startswith("Α1 95τμ ΠΑΡΑΔΟΣΗ ΤΕΛΗ 27-ΑΡΧΕΣ 28.")
    assert "Αποπεράτωση σε 1,5 χρόνο" in raw["description"]
    assert "\n" not in raw["description"] and "  " not in raw["description"]
    assert raw["is_unfinished"] is True  # same page, the existing check still fires
    raw.update(source="xe", source_id="999000111", price=310_000, area_m2=95.0)
    listing = normalize(raw)
    assert listing.photo_count == 2 and "Οι φωτογραφίες είναι ενδεικτικές" in listing.description


def test_results_page_cards_carry_no_photo_signal():
    # Checked against the real card fixtures: no image_count / photo counter on the card,
    # so photo_count can only come from the listing page.
    collector = XeCollector.__new__(XeCollector)
    for name in ("xe_card.html", "xe_card_v2.html"):
        html = (FIXTURES / name).read_text(encoding="utf-8")
        assert "image_count" not in html
        assert "photo_count" not in collector.parse_card(html, base_url="https://www.xe.gr")


def test_detail_jsonld_still_parses_the_offplan_fixture():
    detail = parse_detail_jsonld(OFFPLAN)
    assert detail["energy_class"] == "Α+" and detail["bedrooms"] == 2


# --- storage ----------------------------------------------------------------------------


@pytest.fixture
def mem_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    yield engine


def test_card_sighting_never_blanks_what_the_page_said(mem_db):
    with db.session_scope() as s:
        db.upsert_listing_with_history(
            s, make_listing(source_id="p", description="ΠΑΡΑΔΟΣΗ ΤΕΛΗ 27", photo_count=2)
        )
    with db.session_scope() as s:  # weekly card-only sighting: neither field known
        db.upsert_listing_with_history(s, make_listing(source_id="p", price=190_000))
    with db.session_scope() as s:
        row = s.query(ListingRow).one()
        assert (row.description, row.photo_count, row.price) == ("ΠΑΡΑΔΟΣΗ ΤΕΛΗ 27", 2, 190_000)
    with db.session_scope() as s:  # a later page read refreshes them
        db.upsert_listing_with_history(s, make_listing(source_id="p", photo_count=9))
    with db.session_scope() as s:
        assert s.query(ListingRow).one().photo_count == 9


def test_init_db_adds_the_columns_to_a_legacy_table_twice_safely(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE listing DROP COLUMN description"))
        conn.execute(text("ALTER TABLE listing DROP COLUMN photo_count"))
        cols = {"source": "'xe'", "source_id": "'old'", "url": "'u'", "price": "1"}
        cols.update({"area_m2": "1", "first_seen": "'2026-01-01'", "last_seen": "'2026-01-01'"})
        for c in inspect(conn).get_columns("listing"):
            if not c["nullable"] and c["name"] not in cols and c["name"] != "id":
                cols[c["name"]] = "'active'" if c["name"] == "status" else "0"
        conn.execute(
            text(f"INSERT INTO listing ({', '.join(cols)}) VALUES ({', '.join(cols.values())})")
        )
    monkeypatch.setattr(db, "_engine", engine)
    db.init_db()
    db.init_db()  # idempotent
    names = {c["name"] for c in inspect(engine).get_columns("listing")}
    assert {"description", "photo_count"} <= names
    with engine.connect() as conn:
        row = conn.execute(text("SELECT description, photo_count FROM listing")).one()
    assert tuple(row) == (None, None)  # legacy rows: page not read yet


# --- UI dict -----------------------------------------------------------------------------


def test_load_listings_exposes_page_facts(mem_db):
    checked = datetime(2026, 10, 31, 12)
    with db.session_scope() as s:
        db.upsert_listing_with_history(
            s, make_listing(source_id="few", description="Οι φωτογραφίες είναι ενδεικτικές")
        )
        db.upsert_listing_with_history(
            s, make_listing(source_id="many", photo_count=12, price=250_000, area_m2=101.0)
        )
        db.upsert_listing_with_history(
            s, make_listing(source_id="never", price=330_000, area_m2=131.0)
        )
        rows = {r.source_id: r for r in s.query(ListingRow)}
        rows["few"].photo_count = 2
        rows["few"].detail_checked_at = checked
    by_id = {d["source_id"]: d for d in load_listings()}
    few, many, never = by_id["few"], by_id["many"], by_id["never"]
    assert few["few_photos"] is True and few["photo_count"] == 2
    assert few["description"] == "Οι φωτογραφίες είναι ενδεικτικές"
    assert few["page_checked_at"] == checked and few["page_checked"] is True
    assert many["few_photos"] is False and many["photo_count"] == 12
    # unknown is not "few": no photo count means we don't know, not that it has none
    assert never["few_photos"] is False and never["photo_count"] is None
    assert never["page_checked_at"] is None and never["description"] is None


def test_new_builds_reread_writes_description_and_photo_count(mem_db, monkeypatch):
    """The weekly ``enrich_details --new-builds`` path stores the new fields (no network:
    the page is served as if it were cached on disk)."""
    from scripts import enrich_details

    url = "https://www.xe.gr/property/d/poliseis-katoikion/999000111/neo-irakleio"
    with db.session_scope() as s:
        db.upsert_listing_with_history(
            s,
            make_listing(
                source="xe",
                source_id="999000111",
                url=url,
                year_built=datetime.utcnow().year,
                price_per_m2=3263.0,
            ),
        )
    monkeypatch.setattr(XeCollector, "_read_cache", lambda self, u, ttl: OFFPLAN)
    monkeypatch.setattr(XeCollector, "_fetch_detail", lambda self, session, u: OFFPLAN)
    summary = enrich_details.enrich(limit=5, rescore=False, new_builds=True)
    assert summary["processed"] == 1 and summary["fetched"] == 0
    assert summary["photo_count"] == 1 and summary["description"] == 1
    with db.session_scope() as s:
        row = s.query(ListingRow).one()
        assert row.photo_count == 2 and row.is_unfinished is True
        assert row.description.startswith("Α1 95τμ ΠΑΡΑΔΟΣΗ ΤΕΛΗ 27-ΑΡΧΕΣ 28.")
        assert row.detail_checked_at is not None


def test_listing_page_without_photos_counts_zero_not_unknown():
    start = OFFPLAN.index('"image":[')
    html = OFFPLAN[:start] + '"image":[]' + OFFPLAN[OFFPLAN.index("]", start) + 1 :]
    assert parse_photo_count(html) == 0


def test_new_builds_queue_rereads_checked_pages_missing_photos_after_unchecked(mem_db):
    from scripts.enrich_details import _new_build_rows

    year = datetime.utcnow().year
    checked = datetime(2026, 11, 1)
    with db.session_scope() as s:
        for sid, ppm2 in (("done", 1000.0), ("backfill", 1500.0), ("unchecked", 4000.0)):
            db.upsert_listing_with_history(
                s,
                make_listing(
                    source="xe",
                    source_id=sid,
                    url=f"https://www.xe.gr/{sid}",
                    year_built=year,
                    price_per_m2=ppm2,
                    neighborhood="Νέο Ηράκλειο",
                ),
            )
        rows = {r.source_id: r for r in s.query(ListingRow)}
        rows["done"].detail_checked_at, rows["done"].photo_count = checked, 7
        rows["backfill"].detail_checked_at = checked
    with db.session_scope() as s:
        picked = [r.source_id for r in _new_build_rows(s, 10)]
    assert picked == ["unchecked", "backfill"]  # fully read pages leave the queue


def test_days_on_market_counts_from_the_earliest_evidence(mem_db):
    from datetime import timedelta

    from scout.ui.buyer import dom_text

    now = datetime.utcnow()
    with db.session_scope() as s:
        # first seen 108 days ago; the agent re-posted the ad 2 days ago (XE resets the date)
        db.upsert_listing_with_history(
            s,
            make_listing(
                source_id="reposted", listed_date=now - timedelta(days=2), first_seen=None
            ),
            observed_at=now - timedelta(days=108),
        )
        # posted 60 days ago, first seen by us 40 days ago: the posting date is the evidence
        db.upsert_listing_with_history(
            s,
            make_listing(
                source_id="posted",
                price=255_000,
                area_m2=98.0,
                listed_date=now - timedelta(days=60),
                first_seen=None,
            ),
            observed_at=now - timedelta(days=40),
        )
        db.upsert_listing_with_history(
            s,
            make_listing(source_id="cardonly", price=260_000, area_m2=99.0, first_seen=None),
            observed_at=now - timedelta(days=40),
        )
    by_id = {d["source_id"]: d for d in load_listings()}
    rep, posted, card = by_id["reposted"], by_id["posted"], by_id["cardonly"]
    assert (rep["days_on_market"], rep["dom_basis"]) == (108, "seen")
    assert rep["relisted_on"].date() == (now - timedelta(days=2)).date()
    assert "108 μέρες στην αγορά (από τότε που τη βλέπουμε) · η αγγελία ανανεώθηκε" in dom_text(rep)
    assert (posted["days_on_market"], posted["dom_basis"], posted["relisted_on"]) == (
        60,
        "listed",
        None,
    )
    assert (card["days_on_market"], card["dom_basis"], card["relisted_on"]) == (40, "seen", None)
    assert "ανανεώθηκε" not in dom_text(card)
