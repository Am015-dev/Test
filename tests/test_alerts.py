"""Tests for the daily digest: content, the recent-drop signal, and send routing."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout import alerts
from scout.config import Settings
from scout.models import Base, PriceHistoryRow

from .conftest import make_listing


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """File-based SQLite wired into the global session factory, with a few listings."""
    engine = create_engine(f"sqlite:///{tmp_path / 'a.db'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    now = datetime.utcnow()

    # A fresh, high-scoring opportunity seen today.
    new_opp = make_listing(
        source_id="new1", price=250_000, neighborhood="Cholargos", first_seen=now, last_seen=now
    )
    # An older listing whose price was cut in the last 24h.
    dropped = make_listing(
        source_id="drop1",
        price=270_000,
        neighborhood="Papagou",
        first_seen=now - timedelta(days=10),
        last_seen=now,
    )
    with db.session_scope() as session:
        r1 = db.upsert_listing_with_history(session, new_opp, observed_at=now)
        r1.search_area, r1.score, r1.is_opportunity, r1.excluded = "Cholargos", 60.0, True, False
        r2 = db.upsert_listing_with_history(session, dropped, observed_at=now - timedelta(days=10))
        r2.search_area, r2.score, r2.excluded = "Papagou", 40.0, False
        # Seed the price history: 300k ten days ago -> 270k just now (a real cut).
        session.query(PriceHistoryRow).filter_by(listing_id=r2.id).delete()
        session.add(
            PriceHistoryRow(listing_id=r2.id, observed_at=now - timedelta(days=10), price=300_000)
        )
        session.add(PriceHistoryRow(listing_id=r2.id, observed_at=now, price=270_000))
    yield


def test_digest_includes_opportunities_new_and_cuts(seeded_db):
    text = alerts.build_digest()
    assert "TOP OPPORTUNITIES (1)" in text
    assert "NEW TODAY (1)" in text
    assert "PRICE CUTS, last 24h (1)" in text
    assert "Cholargos" in text and "Papagou" in text
    # The cut shows old -> new with a percentage.
    assert "-10%" in text and "300" in text and "270" in text


def test_digest_leads_with_hot_deals_and_net_yield(seeded_db):
    """The new fresh opportunity is a 'hot deal' and each line carries a net yield."""
    text = alerts.build_digest()
    assert "🔥 HOT DEALS TODAY (1)" in text
    # Net yield (after costs) appears on listing lines, alongside gross.
    assert "net" in text and "gross" in text
    # Hot deals lead the actionable content — before the TOP OPPORTUNITIES section.
    assert text.index("HOT DEALS") < text.index("TOP OPPORTUNITIES")


def test_opportunity_is_always_hot(seeded_db):
    from scout.config import Settings

    # Even with a punishing bar, an opportunity-flagged new listing is still hot
    # (the opportunity flag short-circuits the score/net-yield thresholds).
    settings = Settings(digest_hot_min_score=99.0, digest_hot_min_net_yield=0.5)
    text = alerts.build_digest(settings)
    assert "HOT DEALS TODAY (1)" in text


def test_hot_deal_excludes_non_opportunity_below_bar(seeded_db, monkeypatch):
    """With the opportunity flag off and a high bar, a mediocre new listing isn't hot."""
    import scout.alerts as alerts_mod

    def only_mediocre():
        return [
            {
                "score": 20.0,
                "price": 200_000,
                "price_per_m2": 2500.0,
                "area_m2": 80.0,
                "neighborhood": "Cholargos",
                "search_area": "Cholargos",
                "url": "http://x",
                "is_new": True,
                "is_opportunity": False,
                "excluded": False,
                "gross_yield": 0.03,
                "est_monthly_rent": 500,
                "is_private_seller": False,
                "is_watched": False,
            }
        ]

    monkeypatch.setattr(alerts_mod, "load_listings", only_mediocre)
    monkeypatch.setattr(alerts_mod, "load_recent_price_drops", lambda hours=24: [])
    text = alerts.build_digest()
    assert "HOT DEALS" not in text
    assert "NEW TODAY (1)" in text


def test_recent_price_drops_ignores_old_cuts(seeded_db, monkeypatch):
    from scout.ui.queries import load_recent_price_drops

    # A 1-hour window excludes the cut that we recorded "just now"? It's within 1h, so
    # it should still appear; a 0-hour window (cutoff in the future) excludes it.
    assert len(load_recent_price_drops(hours=24)) == 1
    assert load_recent_price_drops(hours=0) == []


def test_send_digest_noop_when_unconfigured(seeded_db, monkeypatch):
    sent = alerts.send_digest(Settings(telegram_bot_token="", smtp_host=""))
    assert sent is False


def test_send_digest_posts_to_telegram(seeded_db, monkeypatch):
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return _Resp()

    monkeypatch.setattr(alerts.requests, "post", fake_post)
    settings = Settings(telegram_bot_token="TOK", telegram_chat_id="123", smtp_host="")
    assert alerts.send_digest(settings) is True
    assert "botTOK/sendMessage" in captured["url"]
    assert captured["payload"]["chat_id"] == "123"
    assert "TOP OPPORTUNITIES" in captured["payload"]["text"]
