"""Unfinished-building flag (scrape → normalize → DB → UI) plus building_age / is_fresh."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.collectors.xe import XeCollector, is_unfinished_text
from scout.models import Base
from scout.normalize import normalize
from scout.ui import queries
from scout.ui.queries import _building_age, load_listings

from .conftest import make_listing

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "text_in",
    [
        "Ημιτελής οικοδομή στον Χολαργό",
        "ΗΜΙΤΕΛΕΣ διαμέρισμα",
        "Διαμέρισμα ημι-τελές",
        "Πωλείται διαμέρισμα υπό κατασκευή, παράδοση 2027",
        "υπο κατασκευη",
        "Προς αποπεράτωση",
        "σε φάση κατασκευής",
        "Κτίριο σε σκελετό",
        "Ο σκελετός είναι έτοιμος",
        "Apartment under construction",
        "Unfinished maisonette",
    ],
)
def test_unfinished_terms_detected(text_in):
    assert is_unfinished_text(text_in) is True


@pytest.mark.parametrize(
    "text_in",
    [
        "Νεόδμητο ρετιρέ με θέα",
        "Ανακαινισμένο το 2019",
        "Το διαμέρισμα δεν είναι ημιτελές",
        "Κατασκευή 2005, άριστη κατάσταση",
        None,
        "",
    ],
)
def test_finished_texts_not_flagged(text_in):
    assert is_unfinished_text(text_in) is False


def _card(description: str, title: str = "Διαμέρισμα 80 τ.μ.") -> str:
    return f"""
    <div class="common-ad-body">
      <a href="/property/d/poliseis-katoikion/uuid-123/cholargos?x=1">x</a>
      <div class="common-property-ad-title">{title}</div>
      <div class="property-ad-price">250.000 €</div>
      <div id="property-ad-description" class="quill"><pre><div class="ql-editor">
        <p>{description}</p></div></pre></div>
    </div>"""


def _parse(html: str) -> dict:
    return XeCollector.__new__(XeCollector).parse_card(html, base_url="https://www.xe.gr")


def test_parse_card_flags_unfinished_from_description():
    raw = _parse(_card("Πωλείται ημιτελής οικοδομή σε σκελετό, ιδανική για επενδυτή."))
    assert raw["is_unfinished"] is True
    assert normalize(raw).is_unfinished is True


def test_parse_card_flags_unfinished_from_title():
    raw = _parse(_card("Ωραίο σπίτι.", title="Μονοκατοικία 120 τ.μ. υπό κατασκευή"))
    assert raw["is_unfinished"] is True


def test_parse_card_finished_card_not_flagged():
    raw = _parse(_card("Νεόδμητο διαμέρισμα, ανακαινισμένο, άμεσα κατοικήσιμο."))
    assert raw["is_unfinished"] is False


def test_real_fixture_card_reads_description_and_is_not_unfinished():
    html = (FIXTURES / "xe_card_v2.html").read_text(encoding="utf-8")
    collector = XeCollector.__new__(XeCollector)
    raw = collector.parse_card(html, base_url="https://www.xe.gr")
    assert raw["is_unfinished"] is False
    # The selector really finds the card's description text.
    from selectolax.lexbor import LexborHTMLParser

    desc = LexborHTMLParser(html).css_first(XeCollector.SEL_DESCRIPTION)
    assert desc is not None and "Ρετιρέ" in desc.text()
    # ...and the same card with an unfinished phrase injected is flagged.
    flagged = html.replace("Ρετιρέ 4ου ορόφου", "Ημιτελές ρετιρέ 4ου ορόφου", 1)
    assert collector.parse_card(flagged, base_url="https://www.xe.gr")["is_unfinished"] is True


def test_normalize_defaults_missing_flag_to_false():
    raw = {"source": "xe", "source_id": "1", "url": "u", "price": 1, "area_m2": 1.0}
    assert normalize(raw).is_unfinished is False
    raw["is_unfinished"] = None
    assert normalize(raw).is_unfinished is False


def test_init_db_adds_column_to_legacy_table(tmp_path, monkeypatch):
    """A DB created before the column existed gets it (DEFAULT FALSE) and old rows read False."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE listing DROP COLUMN is_unfinished"))
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
    assert "is_unfinished" in {c["name"] for c in inspect(engine).get_columns("listing")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT is_unfinished FROM listing")).scalar() in (0, False)


@pytest.fixture
def mem_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'u.db'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    yield


def test_load_listings_unfinished_age_and_freshness(mem_db):
    newest = datetime(2026, 10, 28)  # an old-ish snapshot: freshness is relative to the data
    with db.session_scope() as s:
        db.upsert_listing_with_history(
            s,
            make_listing(source_id="a", is_unfinished=True, year_built=1965, price=210_000),
            observed_at=newest,
        )
        db.upsert_listing_with_history(
            s,
            make_listing(source_id="b", year_built=1965, renovated_year=2015, price=220_000),
            observed_at=newest - timedelta(days=9),
        )
        db.upsert_listing_with_history(
            s, make_listing(source_id="c", price=230_000), observed_at=datetime(2026, 8, 5)
        )
    by_id = {d["source_id"]: d for d in load_listings()}
    year = datetime.utcnow().year
    assert by_id["a"]["is_unfinished"] is True and by_id["b"]["is_unfinished"] is False
    assert by_id["a"]["building_age"] == year - 1965
    assert by_id["b"]["building_age"] == year - 2015  # renovation resets the clock
    assert by_id["c"]["building_age"] is None
    assert by_id["a"]["is_fresh"] and by_id["b"]["is_fresh"]
    assert by_id["c"]["is_fresh"] is False


def test_building_age_rejects_implausible_years():
    year = datetime.utcnow().year
    assert _building_age(None, None) is None
    assert _building_age(1200, None) is None
    assert _building_age(year + 3, None) is None
    assert _building_age(2000, None) == year - 2000


def test_freshness_empty_set_is_noop():
    queries._annotate_freshness([])  # no crash


def test_scoring_cuts_unfinished_and_off_plan_hard():
    from datetime import date

    from scout.config import load_strategy
    from scout.scoring import compute_market_stats, score

    from .conftest import make_listing

    strategy = load_strategy()
    base = make_listing(year_built=2012, floor=2.0)
    stats = compute_market_stats([base])
    normal = score(base, stats, strategy).score
    shell = score(base.model_copy(update={"is_unfinished": True}), stats, strategy)
    off_plan = score(base.model_copy(update={"year_built": date.today().year}), stats, strategy)
    assert shell.score <= normal * 0.3 and not shell.is_opportunity
    assert off_plan.score < normal * 0.75 and not off_plan.is_opportunity
