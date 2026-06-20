"""Tests for the Apify-backed XE collector (mapping + collect), HTTP mocked."""

from __future__ import annotations

from scout.collectors import apify_xe as mod
from scout.collectors.apify_xe import ApifyXeCollector
from scout.config import Strategy
from scout.normalize import normalize

# A representative actor result (field names per the actor's documented output schema).
SAMPLE_ITEM = {
    "adId": "584648",
    "detailUrl": "https://www.xe.gr/property/d/poliseis-katoikion/uuid-1/cholargos-82",
    "title": "Διαμέρισμα 82 τ.μ.",
    "price": 320000,
    "pricePerSqm": 3902,
    "sqMeters": 82,
    "floors": "3ος",
    "bedrooms": 2,
    "yearBuilt": 2005,
    "area": "Χολαργός (Τσακός)",
    "location": "Χολαργός (Τσακός)",
}


def test_map_item_to_raw():
    raw = ApifyXeCollector.map_item(SAMPLE_ITEM)
    assert raw["source"] == "xe"
    assert raw["source_id"] == "584648"
    assert raw["price"] == 320000
    assert raw["area_m2"] == 82.0
    assert raw["floor"] == 3.0
    assert raw["bedrooms"] == 2
    assert raw["year_built"] == 2005
    assert raw["neighborhood"] == "Χολαργός (Τσακός)"
    # And the raw maps cleanly onto the canonical Listing.
    listing = normalize(raw)
    assert listing is not None
    assert listing.price == 320000
    assert listing.area_m2 == 82.0


def test_map_item_without_id_is_dropped():
    assert ApifyXeCollector.map_item({"price": 1, "sqMeters": 1}) is None


def test_collect_posts_to_actor_and_yields(monkeypatch):
    """collect() calls Apify's run-sync endpoint and maps each dataset item."""
    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                SAMPLE_ITEM,
                {"adId": "x2", "price": 200000, "sqMeters": 60, "area": "Χολαργός"},
            ]

    def fake_post(url, params=None, json=None, timeout=None, verify=None):
        captured["url"] = url
        captured["token"] = params.get("token")
        captured["input"] = json
        return _Resp()

    monkeypatch.setattr(mod.requests, "post", fake_post)
    # Token present -> collector runs; stub the geo-id resolution (no network).
    monkeypatch.setattr(mod.get_settings(), "apify_token", "TEST", raising=False)
    monkeypatch.setattr(
        "scout.collectors.xe.XeCollector._resolve_place_id", lambda self, q: "ChIJ-test"
    )

    raws = list(ApifyXeCollector(Strategy()).collect())
    assert len(raws) == 2
    assert captured["token"] == "TEST"
    assert "run-sync-get-dataset-items" in captured["url"]
    assert captured["input"]["geoPlaceIds"] == ["ChIJ-test"]
    assert captured["input"]["proxyConfiguration"]["apifyProxyCountry"] == "GR"
