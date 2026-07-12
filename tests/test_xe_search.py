"""Tests for XE search-URL building (geo_place_id resolution + fallback).

Network is mocked — these never hit XE.
"""

from __future__ import annotations

from scout.collectors import xe as xemod
from scout.collectors.xe import XeCollector
from scout.config import Strategy


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_urls_use_geo_place_id(monkeypatch):
    """When autocomplete resolves the municipality, one geo_place_id URL is built."""
    monkeypatch.setattr(
        xemod.requests,
        "get",
        lambda *a, **k: _FakeResp([{"place_id": "PID123", "name": "Cholargos"}]),
    )
    urls = XeCollector(Strategy()).search_urls(Strategy())
    assert len(urls) == 1
    assert "geo_place_id=PID123" in urls[0]
    assert "geo_place_name" not in urls[0]


def test_search_urls_fall_back_to_geo_place_name(monkeypatch):
    """If autocomplete errors, degrade to the unfiltered per-neighborhood search."""

    def boom(*a, **k):
        raise xemod.requests.RequestException("network down")

    monkeypatch.setattr(xemod.requests, "get", boom)
    strategy = Strategy()
    strategy.search.neighborhoods = ["Faneromeni", "Ano Cholargos"]
    urls = XeCollector(strategy).search_urls(strategy)
    assert len(urls) == 2
    assert all("geo_place_name=" in u and "geo_place_id" not in u for u in urls)


def test_search_urls_fall_back_when_no_candidates(monkeypatch):
    """An empty autocomplete result also triggers the fallback."""
    monkeypatch.setattr(xemod.requests, "get", lambda *a, **k: _FakeResp([]))
    urls = XeCollector(Strategy()).search_urls(Strategy())
    assert urls and all("geo_place_id" not in u for u in urls)


def _card(uuid: str) -> str:
    return f'<div class="common-ad-body"><a href="/property/d/cat/{uuid}/area">x</a></div>'


def test_collect_paginates_dedups_and_stops(monkeypatch):
    """collect() walks pages, de-duplicates source_ids across them, and stops when a
    page returns nothing (end of results)."""
    pages = {
        "base": _card("A") + _card("B"),
        "base&page=2": _card("B") + _card("C"),  # B repeats -> deduped
        "base&page=3": None,  # end of results -> stop
    }
    c = XeCollector(Strategy())
    monkeypatch.setattr(c, "search_urls", lambda strat: ["base"])
    monkeypatch.setattr(c, "_new_session", lambda: None)
    monkeypatch.setattr(c, "_fetch_html", lambda sess, url, max_attempts=None: pages.get(url))
    monkeypatch.setattr(c, "_enrich_from_detail", lambda sess, raw: None)
    monkeypatch.setattr(xemod.time, "sleep", lambda *a, **k: None)

    ids = [r["source_id"] for r in c.collect()]
    assert ids == ["A", "B", "C"]
