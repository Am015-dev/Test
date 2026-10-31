"""C11: one photo per card — a fixed 4:3 thumbnail left of line 1, full width on the listing
page, and a quiet «Χωρίς φωτογραφία» box when there is none."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("streamlit.testing.v1")

from scout.ui import buyer  # noqa: E402
from scout.ui.theme import _CSS  # noqa: E402

from .test_ui_gauntlet import APP, AppTest, env, goto, ok  # noqa: E402,F401

IMG = "https://blob.cdn.xe.gr/live/2026/10/30/b001e5f9/b001e5f9-source.jpg?width=640&height=480"


def test_photo_box_with_and_without_a_photo():
    with_photo = buyer.photo_html({"image_url": IMG})
    assert with_photo.startswith('<figure class="hg-thumb">')
    assert f'src="{IMG.replace("&", "&amp;")}"' in with_photo
    assert 'loading="lazy"' in with_photo
    assert 'alt="Φωτογραφία της αγγελίας"' in with_photo
    # The «Χωρίς φωτογραφία» label is there but hidden until the image fails to load.
    assert "hg-thumb-empty" not in with_photo.split("onerror")[0]

    for d in ({}, {"image_url": None}, {"image_url": "javascript:alert(1)"}):
        assert buyer.photo_html(d) == ""  # C17: no empty box without a photo

    assert buyer.photo_html({"image_url": IMG}, hero=True).startswith(
        '<figure class="hg-thumb hg-thumb-hero">'
    )


def test_the_photo_sits_before_line_1_on_every_card():
    d = {"id": 1, "price": 200_000, "area_m2": 80.0, "image_url": IMG}
    for compact in (True, False):
        card = buyer.card_html(d, {}, compact=compact)
        assert re.search(r'data-lid="1"><figure class="hg-thumb"><img [^>]+>', card)
        assert card.index("hg-thumb") < card.index('class="hg-l1"')


def test_the_box_has_a_fixed_size_from_the_tokens():
    """Fixed width from a token and a 4:3 ratio: the box never resizes when the photo loads."""
    assert "--hg-thumb-w:" in _CSS
    rule = re.search(r"\.hg-thumb \{([^}]+)\}", _CSS).group(1)
    assert "width: var(--hg-thumb-w)" in rule and "aspect-ratio: 4 / 3" in rule
    assert "border-radius: var(--hg-r-control)" in rule
    assert "object-fit: cover" in _CSS


def _cards(at) -> list[str]:
    return [m.value for m in at.markdown if 'class="hg-card' in m.value]


def _give_every_other_listing_a_photo() -> None:
    """A real XE card photo URL (tests/fixtures/xe_search.html) on every other listing."""
    import streamlit as st
    from sqlalchemy import select

    from scout.db import session_scope
    from scout.models import ListingRow

    with session_scope() as session:
        for row in session.scalars(select(ListingRow).order_by(ListingRow.id)):
            row.image_url = IMG if row.id % 2 else None
    st.cache_data.clear()
    st.cache_resource.clear()


def test_search_and_listing_page_show_the_thumbnail_markup(env):  # noqa: F811
    _give_every_other_listing_a_photo()
    at = AppTest.from_file(APP, default_timeout=60).run()
    goto(at, "Αναζήτηση")
    ok(at, "search")
    cards = _cards(at)
    assert cards
    photos = [c for c in cards if "<img " in c]
    assert photos
    for c in photos:
        assert re.search(
            r'<img src="https://[^"]+" loading="lazy" alt="Φωτογραφία της αγγελίας"', c
        )
    # C17: a card without a photo has no box at all
    assert any("hg-thumb" not in c for c in cards)
    assert not any('class="hg-thumb hg-thumb-empty"' in c for c in cards)

    idx = cards.index(photos[0])  # open the first card that has a photo
    [b for b in at.button if b.label == "Λεπτομέρειες"][idx].click().run()
    ok(at, "listing page")
    assert at.session_state["page"] == "Αγγελία"
    assert any('<figure class="hg-thumb">' in c for c in _cards(at))  # the same card, its thumb
