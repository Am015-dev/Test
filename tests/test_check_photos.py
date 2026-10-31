"""Photo check: pre-filters (no network), stub-client classification with the majority rule,
the picks sort/status text, the migration on a DB without the columns."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout import market_intel, picks
from scout.collectors.xe import UNFINISHED_CHECK_SINCE, parse_photo_urls
from scout.models import Base, ListingRow
from scripts import check_photos as cp

from .conftest import make_listing
from .test_picks import RENTS, YEAR, flat
from .test_trust_data import OFFPLAN

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 20


def page(n: int) -> str:
    imgs = [
        f"https://blob.cdn.xe.gr/live/{i:02d}/{'0' * 8}-0000-0000-0000-{i:012d}-source.jpg?w=1"
        for i in range(n)
    ]
    ld = json.dumps({"@type": "RealEstateListing", "image": imgs})
    return f'<script type="application/ld+json">{ld}</script>'


class StubClient:
    def __init__(self, *answers: str):
        self.answers, self.calls = list(answers), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(text=self.answers.pop(0))])


# --- pre-filters / parsing: no network ------------------------------------------------------


def test_parse_photo_urls_gives_one_url_per_file_in_page_order():
    urls = parse_photo_urls(OFFPLAN)
    assert len(urls) == 2 and urls[0].endswith("format=jpg") and "5b0f4c1e" in urls[0]
    assert parse_photo_urls("<html></html>") == []


def test_majority_and_tie_rule():
    assert cp.majority(["photo", "render", "render"]) == "render"
    assert cp.majority(["photo", "photo", "plan"]) == "photo"
    assert cp.majority(["photo", "plan", "site"]) == "plan"  # no majority: least flattering
    assert cp.majority(["nonsense"]) is None and cp.majority([]) is None


def test_identical_files_across_listings_are_stock():
    assert cp.stock_hashes({1: ["a", "b", "c"], 2: ["x", "b", "y"], 3: ["p", "q", "r"]}) == {"b"}
    assert cp.stock_hashes({1: ["a", "a", "a"]}) == set()  # repeated inside ONE listing: no


def test_vision_model_default_and_env_override(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL_VISION", raising=False)
    assert cp.vision_model() == "claude-haiku-5-5"
    monkeypatch.setenv("ANTHROPIC_MODEL_VISION", "claude-sonnet-5-5")
    assert cp.vision_model() == "claude-sonnet-5-5"


# --- classifier call, stubbed -----------------------------------------------------------------


def test_classify_sends_three_images_and_applies_the_majority(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL_VISION", raising=False)
    client = StubClient('Ορίστε: {"labels": ["Render", "render", "photo"]}')
    assert cp.classify(client, [("image/jpeg", JPEG)] * 3) == "render"
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5" and "temperature" not in call
    assert call["max_tokens"] >= 300 and call["thinking"] == cp.THINKING_OFF
    blocks = call["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["image", "image", "image", "text"]
    assert blocks[0]["source"]["media_type"] == "image/jpeg"


def test_classify_unreadable_answer_is_none():
    assert cp.classify(StubClient("δεν ξέρω"), [("image/jpeg", JPEG)] * 3) is None
    assert cp.classify(StubClient('{"labels": 5}'), [("image/jpeg", JPEG)] * 3) is None


@pytest.fixture
def mem_db(monkeypatch):
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://", future=True, poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(engine, future=True))
    return engine


def _seed(ids):
    with db.session_scope() as s:
        for sid in ids:
            row = db.upsert_listing_with_history(
                s,
                make_listing(
                    source="xe",
                    source_id=sid,
                    url=f"https://www.xe.gr/{sid}",
                    year_built=datetime.utcnow().year - 1,
                    search_area="Cholargos",
                    last_seen=datetime.utcnow(),
                ),
            )
            row.detail_checked_at = UNFINISHED_CHECK_SINCE
            row.excluded = False


def test_check_end_to_end_with_stubs(mem_db, monkeypatch):
    _seed(["few", "shared1", "shared2", "real"])
    pages = {
        "https://www.xe.gr/few": page(2),
        "https://www.xe.gr/shared1": page(3),
        "https://www.xe.gr/shared2": page(3),
        "https://www.xe.gr/real": page(3).replace("0000-0000-0000-", "1111-0000-0000-"),
    }

    # shared1/shared2 serve the same bytes for every image URL; "real" serves distinct bytes
    def fake_download(http, url):
        return ("image/jpeg", JPEG + url.encode())

    monkeypatch.setattr(cp, "download", lambda http, url: fake_download(http, url))
    monkeypatch.setattr(cp.time, "sleep", lambda s: None)
    # make the shared pages byte-identical: same URLs → same bytes
    pages["https://www.xe.gr/shared2"] = pages["https://www.xe.gr/shared1"]
    client = StubClient('{"labels": ["photo", "photo", "site"]}')
    out = cp.check(
        limit=10,
        areas=["Cholargos"],
        client=client,
        http=object(),
        page_fetcher=lambda url: pages[url],
    )
    assert out["few_images"] == 1 and out["stock"] == 2 and out["classified"] == 1
    assert len(client.calls) == 1  # pre-filters spared the other three
    with db.session_scope() as s:
        kinds = {r.source_id: (r.photo_kind, r.photo_checked_at) for r in s.query(ListingRow)}
    assert kinds["few"][0] is None and kinds["few"][1] is not None
    assert kinds["shared1"][0] == kinds["shared2"][0] == "stock"
    assert kinds["real"][0] == "photo" and kinds["real"][1] is not None
    # a second run finds nothing left to check
    out = cp.check(client=client, http=object(), page_fetcher=lambda url: pages[url])
    assert out["rows"] == 0


def test_transient_page_failure_stays_in_the_queue(mem_db, monkeypatch):
    _seed(["t"])
    out = cp.check(client=StubClient(), http=object(), page_fetcher=lambda url: None)
    assert out["rows"] == 1
    with db.session_scope() as s:
        assert s.query(ListingRow).one().photo_checked_at is None


# --- picks: status text + sort -----------------------------------------------------------------


def test_status_line_carries_the_photo_line():
    assert picks.status_line({}).endswith("Φωτογραφίες: δεν ελέγχθηκαν")
    assert "Φωτογραφίες: πραγματικές" in picks.status_line({"photo_kind": "photo"})
    assert "σχέδια ή ψηφιακή απεικόνιση" in picks.status_line({"photo_kind": "render"})
    assert "σχέδια ή ψηφιακή απεικόνιση" in picks.status_line({"photo_kind": "plan"})
    assert "εργοτάξιο" in picks.status_line({"photo_kind": "site"})


def test_render_plan_site_sort_below_real_photos_after_the_checked_rule():
    rows = [
        flat(1, 265_000, m2=95, page_checked=True, photo_count=12, photo_kind="render"),
        flat(2, 300_000, page_checked=True, photo_count=12, photo_kind="photo"),
        flat(3, 290_000, m2=85, page_checked=True, photo_count=12, photo_kind="site"),
        flat(4, 280_000, m2=90, page_checked=True, photo_count=12),  # not classified
        flat(5, 270_000, m2=99, page_checked=False, photo_count=12, photo_kind="photo"),
    ]
    out = picks.find(rows, market_intel.build(rows, YEAR), RENTS, 300_000, year=YEAR, top=10)
    order = [p.listing["id"] for p in out]
    good = {2, 4}
    assert set(order[:2]) == good  # real / unchecked photos first
    assert set(order[2:4]) == {1, 3}  # then render and site, still page-checked
    assert order[4] == 5  # the unchecked page stays last: page-checked rule outranks photos


# --- migration ---------------------------------------------------------------------------------


def test_init_db_adds_photo_columns_to_a_db_lacking_them_twice_safely(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE listing DROP COLUMN photo_kind"))
        conn.execute(text("ALTER TABLE listing DROP COLUMN photo_checked_at"))
    monkeypatch.setattr(db, "_engine", engine)
    db.init_db()
    db.init_db()
    names = {c["name"] for c in inspect(engine).get_columns("listing")}
    assert {"photo_kind", "photo_checked_at"} <= names
