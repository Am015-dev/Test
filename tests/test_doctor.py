"""Tests for the deployment readiness self-check."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.config import Settings, Strategy
from scout.doctor import as_text, diagnose, worst_status
from scout.models import Base

from .conftest import make_listing


@pytest.fixture
def wired_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'd.db'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    yield engine


def _by_name(checks):
    return {c.name: c for c in checks}


def test_healthy_deploy_passes(wired_db):
    with db.session_scope() as s:
        db.upsert_listing_with_history(s, make_listing(source_id="d1"))
    settings = Settings(
        geocoder_user_agent="holargos/1.0 (real@contact.gr)",
        telegram_bot_token="TOK",
        telegram_chat_id="123",
    )
    checks = _by_name(diagnose(settings=settings, strategy=Strategy()))
    assert checks["database"].status == "ok"
    assert checks["schema"].status == "ok"
    assert checks["data"].status == "ok"
    assert checks["geocoder_ua"].status == "ok"
    assert checks["alerts"].status == "ok"
    assert checks["areas"].status == "ok"


def test_default_placeholders_warn(wired_db):
    # Fresh DB (no listings), default UA, no sinks -> warnings, not failures.
    checks = _by_name(diagnose(settings=Settings(), strategy=Strategy()))
    assert checks["data"].status == "warn"
    assert checks["geocoder_ua"].status == "warn"
    assert checks["alerts"].status == "warn"
    assert checks["db_backend"].status == "warn"  # SQLite fallback


def test_missing_schema_fails(tmp_path, monkeypatch):
    # An engine pointed at a DB with NO tables created -> schema check fails.
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}", future=True)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    checks = _by_name(diagnose(settings=Settings(), strategy=Strategy()))
    assert checks["database"].status == "ok"
    assert checks["schema"].status == "fail"
    assert worst_status(list(checks.values())) == "fail"


def test_no_areas_fails(wired_db):
    strategy = Strategy()
    strategy.search.municipality = ""
    strategy.search.areas = []
    checks = _by_name(diagnose(settings=Settings(), strategy=strategy))
    assert checks["areas"].status == "fail"


def test_report_never_leaks_secrets(wired_db):
    settings = Settings(
        database_url="postgresql+psycopg://user:SUPERSECRET@host/db",
        telegram_bot_token="TOPSECRETTOKEN",
        telegram_chat_id="123",
        smtp_password="SMTPSECRET",
    )
    text = as_text(diagnose(settings=settings, strategy=Strategy()))
    assert "SUPERSECRET" not in text
    assert "TOPSECRETTOKEN" not in text
    assert "SMTPSECRET" not in text
