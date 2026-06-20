"""Tests for the FlareSolverr fetch path and WAF-portal collector wiring."""

from __future__ import annotations

import scout.collectors as collectors_pkg
from scout.collectors import default_collectors
from scout.collectors.spitogatos import SpitogatosCollector
from scout.config import Settings, Strategy

# A minimal Spitogatos results page (2 cards) in the rendered shape FlareSolverr
# returns — JS-hydrated data-testid attributes present.
PAGE_HTML = """
<html><body>
<div data-testid="property-card" data-id="111">
  <a href="/en/property/111">x</a>
  <div data-testid="title">Apartment A</div>
  <div data-testid="price">200.000 €</div>
  <div data-testid="area">85 m&sup2;</div>
  <div data-testid="location">Cholargos</div>
</div>
<div data-testid="property-card" data-id="222">
  <a href="/en/property/222">x</a>
  <div data-testid="title">Apartment B</div>
  <div data-testid="price">320.000 €</div>
  <div data-testid="area">120 m&sup2;</div>
  <div data-testid="location">Papagou</div>
</div>
</body></html>
"""

FLARE_OK = {"status": "ok", "solution": {"response": PAGE_HTML, "status": 200}}


def test_fetch_via_flaresolverr_returns_html(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return FLARE_OK

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["cmd"] = json["cmd"]
        captured["target"] = json["url"]
        return _Resp()

    monkeypatch.setattr("scout.collectors.base.requests.post", fake_post)
    c = SpitogatosCollector(Strategy(), save_raw=False)
    html = c._fetch_via_flaresolverr("https://www.spitogatos.gr/x", "http://flare:8191/v1")
    assert "property-card" in html
    assert captured["url"] == "http://flare:8191/v1"
    assert captured["cmd"] == "request.get"
    assert captured["target"] == "https://www.spitogatos.gr/x"


def test_fetch_via_flaresolverr_handles_non_ok(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "error", "message": "challenge failed"}

    monkeypatch.setattr("scout.collectors.base.requests.post", lambda *a, **k: _Resp())
    c = SpitogatosCollector(Strategy(), save_raw=False)
    assert c._fetch_via_flaresolverr("https://x", "http://flare:8191/v1") is None


def test_collect_via_flaresolverr_parses_cards(monkeypatch):
    strategy = Strategy()
    strategy.search.neighborhoods = ["Cholargos"]
    c = SpitogatosCollector(strategy, save_raw=False)

    # Route collect() through FlareSolverr and stub the network fetch.
    monkeypatch.setattr(
        "scout.collectors.spitogatos.get_settings",
        lambda: Settings(flaresolverr_url="http://flare:8191/v1"),
    )
    monkeypatch.setattr(c, "_fetch_via_flaresolverr", lambda url, endpoint: PAGE_HTML)
    monkeypatch.setattr(c, "polite_delay", lambda: None)

    raws = list(c.collect())
    assert len(raws) == 2
    assert {r["source_id"] for r in raws} == {"111", "222"}
    first = next(r for r in raws if r["source_id"] == "111")
    assert first["price"] == 200_000 and first["area_m2"] == 85.0
    assert first["url"] == "https://www.spitogatos.gr/en/property/111"


def test_default_collectors_adds_waf_portals_only_when_configured(monkeypatch):
    monkeypatch.setattr(collectors_pkg, "get_settings", lambda: Settings(flaresolverr_url=""))
    assert [type(c).__name__ for c in default_collectors(Strategy())] == ["XeCollector"]

    monkeypatch.setattr(
        collectors_pkg, "get_settings", lambda: Settings(flaresolverr_url="http://flare:8191/v1")
    )
    names = [type(c).__name__ for c in default_collectors(Strategy())]
    assert names == ["XeCollector", "SpitogatosCollector", "IndomioCollector"]
