from __future__ import annotations

import os
import time
from types import SimpleNamespace

import scout.remote_db as rd


def _settings(tmp_path, database_url=""):
    return SimpleNamespace(database_url=database_url, db_path=str(tmp_path / "l.db"))


class Resp:
    content = b"SQLITE"

    def raise_for_status(self):
        pass


def test_downloads_when_missing_and_skips_when_fresh(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(rd, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(rd.requests, "get", lambda *a, **k: calls.append(1) or Resp())
    assert rd.ensure_local_db() is True and (tmp_path / "l.db").read_bytes() == b"SQLITE"
    assert rd.ensure_local_db() is False and len(calls) == 1  # fresh: no second download


def test_redownloads_when_stale(tmp_path, monkeypatch):
    (tmp_path / "l.db").write_bytes(b"old")
    old = time.time() - 10 * 3600
    os.utime(tmp_path / "l.db", (old, old))
    monkeypatch.setattr(rd, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(rd.requests, "get", lambda *a, **k: Resp())
    assert rd.ensure_local_db() is True and (tmp_path / "l.db").read_bytes() == b"SQLITE"


def test_noop_with_external_database_and_failsoft_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "get_settings", lambda: _settings(tmp_path, "postgresql://x"))
    assert rd.ensure_local_db() is False
    monkeypatch.setattr(rd, "get_settings", lambda: _settings(tmp_path))

    def boom(*a, **k):
        raise OSError("offline")

    monkeypatch.setattr(rd.requests, "get", boom)
    (tmp_path / "l.db").write_bytes(b"keep")
    os.utime(tmp_path / "l.db", (1, 1))
    assert rd.ensure_local_db() is False and (tmp_path / "l.db").read_bytes() == b"keep"
