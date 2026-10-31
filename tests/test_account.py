"""Profiles: PIN hashing and lockout in the gist, per-user namespacing, anonymous fallback."""

from __future__ import annotations

import json

import pytest

from scout.nl_search import SearchFilters

from .test_shortlist import FakeGist

pytest.importorskip("streamlit")


@pytest.fixture
def gist(monkeypatch):
    import requests

    import scout.shortlist as sl
    import scout.ui.account as acc

    fake = FakeGist()
    monkeypatch.setattr(requests, "request", fake.request)
    monkeypatch.setattr(sl, "_gist_id", None)
    monkeypatch.setattr(sl, "_recent", None)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    who = {"user": None}
    monkeypatch.setattr(sl, "profile_hook", lambda: who["user"])
    monkeypatch.setattr(acc.st, "session_state", {})
    fake.who = who
    return fake


def _doc(fake) -> dict:
    return json.loads(fake.gists["g1"]["files"]["mandates.json"]["content"])


def test_pin_is_stored_salted_and_hashed_never_plain(gist):
    from scout.ui import account as acc

    a = acc.create_profile("  Μαρία ", "1234")
    b = acc.create_profile("Γιώργος", "1234")
    doc = _doc(gist)
    pa, pb = doc["profiles"][a], doc["profiles"][b]
    assert a == acc.profile_key("μαρια") and pa["name"] == "Μαρία"
    assert pa["hash"] == acc.hash_pin(pa["salt"], "1234")
    assert pa["salt"] != pb["salt"] and pa["hash"] != pb["hash"]  # per-profile salt
    assert "1234" not in json.dumps(doc)
    assert acc.check_pin("ΜΑΡΙΑ", "1234") == a  # names match case-insensitively


def test_bad_inputs_and_duplicates_are_refused(gist):
    from scout.ui import account as acc

    for name, pin in (("", "1234"), ("x", "12"), ("x", "abcd"), ("x", "12345")):
        with pytest.raises(acc.ProfileError):
            acc.create_profile(name, pin)
    acc.create_profile("Άννα", "0000")
    with pytest.raises(acc.ProfileError, match="Υπάρχει ήδη"):
        acc.create_profile("άννα", "1111")
    with pytest.raises(acc.ProfileError, match="Δεν υπάρχει"):
        acc.check_pin("Κανείς", "0000")


def test_five_wrong_pins_lock_the_name_for_ten_minutes_in_the_gist(gist):
    from scout.ui import account as acc

    key = acc.create_profile("Νίκος", "4321")
    t = 1_000_000.0
    for _ in range(4):
        with pytest.raises(acc.ProfileError, match="Λάθος PIN") as e:
            acc.check_pin("Νίκος", "0000", now=t)
        assert "0000" not in str(e.value)
    assert _doc(gist)["profiles"][key]["fails"] == 4
    with pytest.raises(acc.ProfileError, match="κλείδωσε"):
        acc.check_pin("Νίκος", "0000", now=t)
    assert _doc(gist)["profiles"][key]["locked_until"] == t + acc.LOCK_S
    # even the right PIN waits — and the lock is in the stored document, not this session
    with pytest.raises(acc.ProfileError, match="10 λεπτά"):
        acc.check_pin("Νίκος", "4321", now=t + 1)
    with pytest.raises(acc.ProfileError, match="5 λεπτά"):
        acc.check_pin("Νίκος", "4321", now=t + acc.LOCK_S - 290)
    assert acc.check_pin("Νίκος", "4321", now=t + acc.LOCK_S + 1) == key
    p = _doc(gist)["profiles"][key]
    assert p["fails"] == 0 and p["locked_until"] == 0


def test_two_users_favourites_verdicts_and_searches_do_not_mix(gist):
    import scout.shortlist as sl
    from scout.ui import account as acc

    a = acc.create_profile("Α", "1111")
    b = acc.create_profile("Β", "2222")
    gist.who["user"] = a
    sl.set_watch("xe:1", True)
    sl.set_review("xe:9", "no")
    sl.save_mandate("δυάρι", SearchFilters())
    gist.who["user"] = b
    sl.set_watch("xe:2", True)
    assert sl.watch_set() == {"xe:2"} and sl.review_map() == {} and sl.list_mandates() == []
    gist.who["user"] = a
    assert sl.watch_set() == {"xe:1"} and sl.review_map() == {"xe:9": "no"}
    assert [m.text for m in sl.list_mandates()] == ["δυάρι"]
    gist.who["user"] = None
    assert sl.watch_set() == set()  # anonymous untouched


def test_store_namespaces_by_user_and_reads_back(gist):
    from scout.ui import account as acc

    acc.Store("p1").set("guide", {"budget": 300_000})
    acc.Store(None).set("guide", {"budget": 150_000})
    acc.st.session_state.clear()  # a new session: values come from the gist
    assert acc.Store("p1").get("guide") == {"budget": 300_000}
    assert acc.Store("p2").get("guide", "none") == "none"
    assert acc.Store(None).get("guide") == {"budget": 150_000}
    doc = _doc(gist)
    assert doc["guide"] == {"budget": 150_000}  # anonymous = the top level
    assert doc["profiles"]["p1"]["data"]["guide"] == {"budget": 300_000}


def test_existing_top_level_data_stays_anonymous_and_seeds_the_first_profile(gist):
    import scout.shortlist as sl
    from scout.ui import account as acc

    sl.set_watch("xe:old", True)  # saved before accounts existed
    sl.set_review("xe:old", "ok")
    owner = acc.create_profile("Ιδιοκτήτης", "1357")
    other = acc.create_profile("Φίλος", "2468")
    gist.who["user"] = owner
    assert sl.watch_set() == {"xe:old"} and sl.review_map() == {"xe:old": "ok"}
    gist.who["user"] = other
    assert sl.watch_set() == set()
    gist.who["user"] = None
    assert sl.watch_set() == {"xe:old"}  # nothing lost


def test_without_token_the_store_is_session_only(monkeypatch):
    import scout.ui.account as acc

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(acc.st, "session_state", {})
    s = acc.Store(None)
    assert s.persistent is False
    assert s.set("watch", ["xe:1"]) is False
    assert acc.Store(None).get("watch") == ["xe:1"]  # still there for this session


def test_daily_digests_cover_every_profile(gist, monkeypatch):
    import scout.alerts as alerts
    import scout.shortlist as sl
    import scout.ui.queries as q
    from scout.ui import account as acc

    a = acc.create_profile("Α", "1111")
    gist.who["user"] = a
    sl.save_mandate("δικό μου", SearchFilters())
    gist.who["user"] = None
    sl.save_mandate("ανώνυμο", SearchFilters())
    listing = {"id": 1, "source": "xe", "source_id": "1", "price": 100_000, "score": 50}
    listing |= {"neighborhood": "Χολαργός", "url": "u", "excluded": False}
    monkeypatch.setattr(q, "load_listings", lambda: [listing])
    sent = []
    monkeypatch.setattr(alerts, "send_alert", lambda text, **k: sent.append(text) or True)
    assert sl.run_shortlists() == 2
    assert any("δικό μου" in t for t in sent) and any("ανώνυμο" in t for t in sent)
    gist.who["user"] = a
    assert sl.list_mandates()[0].sent == {"xe:1"}


def test_google_sign_in_is_used_when_auth_secrets_exist(gist, monkeypatch):
    import scout.ui.account as acc

    monkeypatch.setattr(acc.st, "secrets", {"auth": {"client_id": "x"}})
    monkeypatch.setattr(acc.st, "user", {"is_logged_in": False})
    assert acc.oidc_enabled() and acc.current_user() is None
    monkeypatch.setattr(
        acc.st, "user", {"is_logged_in": True, "email": "Maria@Example.gr", "name": "Μαρία"}
    )
    assert acc.current_user() == "google:maria@example.gr"
    assert acc.display_name() == "Μαρία"
    acc.st.session_state[acc.SESSION_KEY] = "κάποιος"  # a PIN session never overrides Google
    assert acc.current_user() == "google:maria@example.gr"
    monkeypatch.setattr(acc.st, "secrets", {})
    assert acc.current_user() == "κάποιος"  # no [auth] → PIN profiles
