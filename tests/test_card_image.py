"""The card's first photo (``image_url``) per portal, from saved real search pages."""

from __future__ import annotations

from pathlib import Path

import pytest
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.collectors import xe as xemod
from scout.collectors.goldenhome import GoldenHomeCollector
from scout.collectors.greenacres import GreenAcresCollector
from scout.collectors.parse_helpers import card_image_url, portal_photo_url
from scout.collectors.remax import RemaxCollector
from scout.collectors.xe import XeCollector
from scout.config import Strategy
from scout.models import Base
from scout.normalize import normalize

from .conftest import make_listing

FIXTURES = Path(__file__).parent / "fixtures"


def _images(collector, fixture: str) -> list[str | None]:
    tree = HTMLParser((FIXTURES / fixture).read_text(encoding="utf-8"))
    cards = tree.css(collector.CARD_SELECTOR)
    assert cards
    html = collector._card_html if isinstance(collector, XeCollector) else (lambda c: c.html)
    return [collector.parse_card(html(c), base_url=collector.BASE)["image_url"] for c in cards]


@pytest.mark.parametrize(
    "collector, fixture, prefix",
    [
        (XeCollector(Strategy()), "xe_search.html", "https://blob.cdn.xe.gr/live/"),
        (GoldenHomeCollector(Strategy()), "goldenhome_search.html", "https://goldenhome.gr/"),
        (RemaxCollector(Strategy()), "remax_search.html", "https://www.remax.gr/assets/media/"),
        (
            GreenAcresCollector(Strategy(), save_raw=False),
            "greenacres_card.html",
            "https://lb1.green-acres.com/",
        ),
    ],
)
def test_every_card_in_the_fixture_has_its_photo(collector, fixture, prefix):
    images = _images(collector, fixture)
    assert all(url and url.startswith(prefix) for url in images), images


def test_xe_photo_is_the_listing_photo_not_the_agency_logo():
    first = _images(XeCollector(Strategy()), "xe_search.html")[0]
    assert first == (
        "https://blob.cdn.xe.gr/live/2026/10/30/b001e5f9-3a21-4c80-be94-656275b3737e/"
        "b001e5f9-3a21-4c80-be94-656275b3737e-source.jpg?width=640&height=480&format=jpg"
    )
    # The agency logo sits in the card body; the body alone has no listing photo.
    tree = HTMLParser((FIXTURES / "xe_search.html").read_text(encoding="utf-8"))
    body = tree.css_first(XeCollector.CARD_SELECTOR)
    assert XeCollector(Strategy()).parse_card(body.html, "x")["image_url"] is None


def test_xe_whole_ad_parses_the_same_fields_as_the_body():
    c = XeCollector(Strategy())
    tree = HTMLParser((FIXTURES / "xe_search.html").read_text(encoding="utf-8"))
    for body in tree.css(c.CARD_SELECTOR):
        whole = c.parse_card(c._card_html(body), "x")
        alone = c.parse_card(body.html, "x")
        assert {**alone, "image_url": whole["image_url"]} == whole


def test_xe_collect_yields_the_card_photo(monkeypatch):
    c = XeCollector(Strategy())
    page = (FIXTURES / "xe_search.html").read_text(encoding="utf-8")
    monkeypatch.setattr(c, "search_urls", lambda strat: ["base"])
    monkeypatch.setattr(c, "_new_session", lambda: None)
    monkeypatch.setattr(
        c, "_fetch_html", lambda sess, url, max_attempts=None: page if url == "base" else None
    )
    monkeypatch.setattr(c, "_enrich_from_detail", lambda sess, raw: None)
    monkeypatch.setattr(xemod.time, "sleep", lambda *a, **k: None)
    rows = list(c.collect())
    assert len(rows) == 4
    assert all(r["image_url"].startswith("https://blob.cdn.xe.gr/") for r in rows)


def test_green_acres_takes_the_first_slide_not_the_logo():
    url = _images(GreenAcresCollector(Strategy(), save_raw=False), "greenacres_card.html")[0]
    assert url.endswith("/miniPhotos/A7b2xz1i68ximzcy_1.jpg?639138845230000000")


def _imgs(html: str):
    return HTMLParser(html).css("img")


def test_card_image_url_prefers_the_lazy_attribute_over_a_placeholder():
    html = '<img src="/img/blank.gif" data-src="https://cdn.portal.gr/p/1.jpg">'
    assert card_image_url(_imgs(html), "https://www.portal.gr", "portal.gr") == (
        "https://cdn.portal.gr/p/1.jpg"
    )


def test_card_image_url_resolves_relative_and_skips_foreign_hosts_and_data_uris():
    html = (
        '<img src="data:image/gif;base64,R0lGOD">'
        '<img src="https://ads.example.com/banner.jpg">'
        '<img src="http://www.portal.gr/plain-http.jpg">'
        '<img src="/photos/2.webp">'
    )
    assert card_image_url(_imgs(html), "https://www.portal.gr/search", "portal.gr") == (
        "https://www.portal.gr/photos/2.webp"
    )
    assert card_image_url(_imgs("<img>"), "https://www.portal.gr", "portal.gr") is None
    assert card_image_url(_imgs('<img src="https://notportal.gr/x.jpg">'), "", "portal.gr") is None


@pytest.mark.parametrize(
    "url, host",
    [
        (
            "https://rodeo.cdn.xe.gr/rodeo-static/packs/static/images/icons/"
            "placeholder_real_estate-fee8fc8f3bdb85b0a8dc.jpg",
            "xe.gr",
        ),
        ("https://goldenhome.gr/img/site/goldenhome_default.png", "goldenhome.gr"),
        (
            "https://www.remax.gr/assets-fe-old/assetsfe/css/images/icons/"
            "associate-blank-medium.png",
            "remax.gr",
        ),
    ],
)
def test_the_portals_no_photo_placeholders_are_not_photos(url, host):
    """Each was stored as a listing photo in the published DB (Oct 2026)."""
    assert portal_photo_url(url, "", host) is None


def test_normalize_keeps_image_url():
    raw = {
        "source": "xe",
        "source_id": "1",
        "url": "https://www.xe.gr/property/d/x/1",
        "price": 200_000,
        "area_m2": 80.0,
        "image_url": "https://blob.cdn.xe.gr/live/a.jpg",
    }
    assert normalize(raw).image_url == "https://blob.cdn.xe.gr/live/a.jpg"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, future=True)() as s:
        yield s


def test_upsert_refreshes_the_photo_on_every_sighting(session):
    db.upsert_listing_with_history(session, make_listing(image_url="https://cdn.x.gr/1.jpg"))
    row = db.upsert_listing_with_history(session, make_listing(image_url="https://cdn.x.gr/2.jpg"))
    assert row.image_url == "https://cdn.x.gr/2.jpg"  # a newer card photo replaces it
    # The card now shows no photo (or only the portal's placeholder): the card is the truth.
    row = db.upsert_listing_with_history(session, make_listing(image_url=None))
    assert row.image_url is None
