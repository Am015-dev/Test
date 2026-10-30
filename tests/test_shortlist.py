from __future__ import annotations

from scout.nl_search import SearchFilters
from scout.shortlist import Mandate, digest, pick


def L(i, price, score=50, **kw):
    return {
        "id": i,
        "price": price,
        "score": score,
        "neighborhood": "Χολαργός",
        "url": f"u{i}",
        "excluded": False,
        **kw,
    }


def test_pick_ranks_filters_and_skips():
    ls = [L(1, 100_000, 40), L(2, 120_000, 70), L(3, 300_000, 99), L(4, 90_000, 80, excluded=True)]
    f = SearchFilters(price_max=200_000)
    assert [d["id"] for d, _, _ in pick(f, ls, set())] == [2, 1]
    assert [d["id"] for d, _, _ in pick(f, ls, {2})] == [1]
    assert len(pick(f, ls, set(), n=1)) == 1


def test_digest_lists_picks():
    f = SearchFilters()
    txt = digest(Mandate(1, "δυάρι", f), pick(f, [L(1, 100_000)], set()))
    assert "δυάρι" in txt and "100,000" in txt and "u1" in txt


def test_seen_covers_sent_approved_rejected():
    assert Mandate(1, "x", SearchFilters(), {1}, {2}, {3}).seen == {1, 2, 3}


class FakeGist:
    """In-memory stand-in for the GitHub gists API (one gist)."""

    def __init__(self):
        self.gists = {}

    def request(self, method, url, headers=None, json=None, timeout=None):
        class R:
            def __init__(s, data):
                s.data = data

            def raise_for_status(s):
                pass

            def json(s):
                return s.data

        path = url.removeprefix("https://api.github.com")
        if method == "GET" and path.startswith("/gists?"):
            return R([{"id": k, **v} for k, v in self.gists.items()])
        if method == "POST":
            self.gists["g1"] = json
            return R({"id": "g1"})
        gid = path.rsplit("/", 1)[1]
        if method == "PATCH":
            self.gists[gid]["files"].update(json["files"])
        return R({"id": gid, "files": self.gists[gid]["files"]})


def test_mandates_round_trip_through_gist(monkeypatch):
    import requests

    import scout.shortlist as sl

    fake = FakeGist()
    monkeypatch.setattr(requests, "request", fake.request)
    monkeypatch.setattr(sl, "_gist_id", None)
    monkeypatch.setattr(sl, "_recent", None)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    assert sl.list_mandates() == []
    a = sl.save_mandate("δυάρι", SearchFilters(price_max=180_000, wants=["parking"]))
    b = sl.save_mandate("τριάρι", SearchFilters())
    sl._add_ids(a, "sent", {5})
    sl._add_ids(a, "sent", {7})
    sl._add_ids(a, "rejected", {9})
    m = {x.id: x for x in sl.list_mandates()}
    assert m[a].filters.price_max == 180_000 and m[a].filters.wants == ["parking"]
    assert m[a].sent == {5, 7} and m[a].rejected == {9} and m[b].seen == set()
    assert list(fake.gists) == ["g1"] and fake.gists["g1"]["public"] is False
    sl.delete_mandate(a)
    assert [x.id for x in sl.list_mandates()] == [b]


def test_no_token_is_a_clear_error_and_daily_step_is_a_noop(monkeypatch):
    import pytest

    import scout.shortlist as sl

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(sl.StorageNotConfigured):
        sl.list_mandates()
    assert sl.run_shortlists() == 0


def test_reads_right_after_a_write_use_the_written_state(monkeypatch):
    # GitHub may serve the pre-write gist for a moment: two quick reviews must both persist.
    import requests

    import scout.shortlist as sl

    fake = FakeGist()
    monkeypatch.setattr(sl, "_gist_id", None)
    monkeypatch.setattr(sl, "_recent", None)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setattr(requests, "request", fake.request)
    a = sl.save_mandate("δυάρι", SearchFilters())
    stale = {"mandates.json": dict(fake.gists["g1"]["files"]["mandates.json"])}
    real_request = fake.request

    def stale_get(method, url, **kw):
        r = real_request(method, url, **kw)
        if method == "GET" and "/gists/g1" in url:
            r.json = lambda: {"id": "g1", "files": stale}
        return r

    monkeypatch.setattr(requests, "request", stale_get)
    sl._add_ids(a, "approved", {1})
    sl._add_ids(a, "rejected", {2})
    m = sl.list_mandates()[0]
    assert m.approved == {1} and m.rejected == {2}
