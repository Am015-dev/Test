# ruff: noqa: F811  (the imported `env` fixture is re-declared as a test argument)
"""C8: every list opens in the guide's trust order — page read first, real photos next, then
the chosen «Σειρά»; a flat more than 30 % under its comparables sorts after the rest of its
tier. Driven through the real «Αναζήτηση» page on the seeded gauntlet DB, read off the cards.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from .test_ui_gauntlet import APP, SEARCH, env, goto  # noqa: F401  (env is a fixture)

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
READ_AT = datetime(2026, 11, 1)  # after xe.UNFINISHED_CHECK_SINCE: counts as page read


def _tier(d: dict, adv: dict) -> tuple:
    from scout.ui import buyer

    return buyer.trust_key(d, adv)[:3]  # (not read, bad photos, few photos)


def _mark(env_db_ids: dict[str, dict]) -> None:
    """Write page-read / photo-check facts onto seeded rows by source_id."""
    from scout.db import session_scope
    from scout.models import ListingRow

    with session_scope() as s:
        for row in s.query(ListingRow).filter(ListingRow.source_id.in_(list(env_db_ids))):
            for k, v in env_db_ids[row.source_id].items():
                setattr(row, k, v)


def _listings() -> list[dict]:
    import streamlit as st

    from scout.ui import queries

    st.cache_data.clear()
    return queries.load_listings(include_excluded=True, only_active=True)


def _seed_trust(monkeypatch) -> str:
    """Read a third of the Galatsi/Chalandri flats, class some photos as renders, and turn
    one read, real-photo flat into bait: 33 % under its like-for-like median."""
    from scout import market_intel

    marks: dict[str, dict] = {}
    for j in range(50):
        if j % 3 == 0:
            marks[f"q-{j}"] = {
                "detail_checked_at": READ_AT,
                "photo_kind": "photo",
                "photo_count": 9,
            }
        if j % 9 == 0:
            marks[f"q-{j}"]["photo_kind"] = "render"  # read, but the photos are drawings
    _mark(marks)
    rows = _listings()
    intel = market_intel.build(rows)
    by_sid = {d["source_id"]: d for d in rows}
    bait = next(
        sid
        for sid, m in marks.items()
        if m["photo_kind"] == "photo" and (c := intel.comps(by_sid[sid])) and c["n"] >= 5
    )
    d = by_sid[bait]
    ppm = intel.comps(d)["ppm"] * 0.67
    _mark({bait: {"price": int(ppm * d["area_m2"]), "price_per_m2": ppm}})
    return bait


def _cards(monkeypatch, sort: str | None = None) -> list[tuple[dict, dict]]:
    from scout.ui import buyer

    seen: list[tuple[dict, dict]] = []
    real = buyer.result_card

    def record(d, adv, prefix, *a, **k):
        if prefix == "s":
            seen.append((d, adv))
        return real(d, adv, prefix, *a, **k)

    monkeypatch.setattr(buyer, "result_card", record)
    monkeypatch.setattr(buyer, "PAGE_SIZE", 1_000)  # every card, not just the first screen
    at = AppTest.from_file(APP, default_timeout=120).run()
    goto(at, SEARCH)
    if sort:
        seen.clear()
        at.selectbox(key="sort").set_value(sort).run()
    assert not at.exception, [e.value for e in at.exception]
    return seen


@pytest.mark.parametrize("sort", [None, "Χαμηλότερη τιμή", "Υψηλότερη απόδοση"])
def test_search_opens_page_read_then_real_photos_and_bait_is_not_first(env, monkeypatch, sort):
    bait = _seed_trust(monkeypatch)
    cards = _cards(monkeypatch, sort)
    assert len(cards) > 20, "the seeded DB should give a long list"
    tiers = [_tier(d, adv) for d, adv in cards]
    assert tiers == sorted(tiers), "tiers out of order: page read, then real photos"
    first, adv = cards[0]
    assert first.get("page_checked") and first.get("photo_kind") == "photo"
    assert first["source_id"] != bait

    # The bait is in the top tier and, by the default sort, would lead it (cheapest vs
    # comparables) — yet it comes after every other flat of that tier.
    pos = next(i for i, (d, _) in enumerate(cards) if d["source_id"] == bait)
    bd, badv = cards[pos]
    assert badv["cmp"] and badv["cmp"]["pct"] < -0.30
    top = [i for i, t in enumerate(tiers) if t == tiers[pos]]
    assert top[0] == 0 and pos == top[-1], (pos, top)
    if sort is None:
        others = [cards[i][1]["cmp"]["pct"] for i in top[:-1] if cards[i][1].get("cmp")]
        assert others and min(others) > badv["cmp"]["pct"]

    # Inside the top tier the user's «Σειρά» still decides.
    if sort == "Χαμηλότερη τιμή":
        prices = [cards[i][0]["price"] for i in top[:-1]]
        assert prices == sorted(prices)


def test_trust_order_helper_matches_the_sorts():
    from scout.ui import buyer

    def flat(i, **kw):
        return {"id": i, "price": 100_000 + i, "price_per_m2": 2000, **kw}

    views = [
        (flat(1), {"cmp": {"pct": -0.20}}),  # not read
        (flat(2, page_checked=True, photo_kind="render"), {"cmp": {"pct": -0.10}}),
        (flat(3, page_checked=True), {"cmp": {"pct": -0.33}}),  # read, bait
        (flat(4, page_checked=True), {"cmp": {"pct": -0.05}}),
        (flat(5, page_checked=True, few_photos=True), {"cmp": {"pct": -0.25}}),
    ]
    assert [d["id"] for d, _ in buyer.trust_order(views)] == [4, 3, 5, 2, 1]
    assert [d["id"] for d, _ in buyer.trust_order(views, "Χαμηλότερη τιμή")] == [4, 3, 5, 2, 1]
