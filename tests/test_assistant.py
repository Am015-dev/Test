from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scout import market_intel
from scout.area_insights import AreaInsight
from scout.ui import assistant

SECRET = "sk-ant-test-SECRET-should-never-leak"


def _d(sid: str, **kw) -> dict:
    d = {
        "id": int(sid) if sid.isdigit() else 0,
        "source": "xe",
        "source_id": sid,
        "url": f"https://xe.gr/{sid}",
        "price": 300_000,
        "first_price": 320_000,
        "area_m2": 80.0,
        "price_per_m2": 3750.0,
        "floor": 2.0,
        "year_built": 2021,
        "renovated_year": None,
        "bedrooms": 2,
        "neighborhood": "Νέα Ιωνία (Περισσός)",
        "page_checked": True,
        "page_checked_at": datetime(2026, 10, 20),
        "photo_count": 14,
        "energy_class": "Β+",
        "is_private_seller": False,
        "est_monthly_rent": 1000.0,
        "gross_yield": 0.04,
        "net_yield": 0.028,
        "rent_estimated": True,
        "days_on_market": 120,
        "dom_basis": "listed",
        "description": "Διαμέρισμα " + "πολύ φωτεινό " * 60,
    }
    return {**d, **kw}


@pytest.fixture
def facts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    rows = [
        _d("1"),
        _d("2", price=280_000, gross_yield=0.045, is_private_seller=True, days_on_market=30),
        _d("3", energy_class=None, page_checked=False, photo_count=2),
    ]
    intel = market_intel.build(rows)
    return assistant.facts_for(rows, intel, answers={"budget": 300_000, "goal": "απόδοση"})


# ---- facts_for ----------------------------------------------------------------------------


def test_facts_shape_and_basis(facts):
    assert set(facts) >= {"today", "buyer", "listings", "areas"}
    first = facts["listings"][0]
    assert first["price_eur"] == 300_000 and first["eur_per_m2"] == 3750
    assert first["status"] == "Ελέγχθηκε η περιγραφή στις 2026-10-20"
    assert first["rent"]["eur_month"] == 1000 and "ζητούμενα" in first["rent"]["kind"]
    assert first["gross_yield_pct"] == 4.0 and first["net_yield_pct"] == 2.8
    assert first["days_on_market"] == {"days": 120, "basis": "από την ημερομηνία ανάρτησης"}
    assert first["price_history"] == {
        "first_price_eur": 320_000,
        "drop_eur": 20_000,
        "drop_pct": 6.2,
    }
    assert facts["buyer"] == {"budget": 300_000, "goal": "απόδοση"}
    json.dumps(facts, ensure_ascii=False)  # JSON-able as is


def test_opening_offer_rule(facts):
    one, two, three = facts["listings"]
    assert one["opening_offer"]["eur"] == 282_000 and one["opening_offer"]["cut_pct"] == 6.0
    assert two["opening_offer"]["cut_pct"] == 5.0  # −3 % base, −2 % private, DOM 30
    assert any("ιδιώτης" in w for w in two["opening_offer"]["why"])
    assert three["opening_offer"]["eur"] == 282_000


def test_status_missing_and_compare(facts):
    one, two, three = facts["listings"]
    assert three["status"] == "Δεν έχει ελεγχθεί ακόμα"
    assert "ενεργειακή κλάση" in three["missing"]
    assert two["vs_first"] == {"price_diff_eur": -20_000, "gross_yield_diff_pts": 0.5}
    assert facts["top3_compare"]["gross_yield_pct"]["highest"] == "#2"
    assert facts["top3_compare"]["price_eur"]["lowest"] == "#2"


def test_under_construction_says_so():
    f = assistant.facts_for([_d("9", is_unfinished=True)], None)
    assert f["listings"][0]["status"] == "Υπό κατασκευή"


def test_truncation_and_only_seller_text(facts):
    assert len(assistant.facts_for([_d(str(i)) for i in range(15)], None)["listings"]) == 10
    text = facts["listings"][0]["seller_text"]
    assert len(text) <= assistant.SELLER_TEXT_CHARS + 1 and text.endswith("…")
    blob = json.dumps(facts, ensure_ascii=False)
    assert "xe.gr/" not in blob  # no URLs or other listing free text


def test_no_key_leakage(facts):
    blob = json.dumps(facts, ensure_ascii=False)
    assert SECRET not in blob
    for req in (assistant.brief_request(facts), assistant.chat_request(facts, "Γιατί;")):
        assert SECRET not in json.dumps(req, ensure_ascii=False)


def test_loan_adds_instalment(monkeypatch):
    f = assistant.facts_for([_d("1")], None, answers={"loan": True, "budget": 300_000})
    loan = f["listings"][0]["loan"]
    assert loan["amount_eur"] == 210_000
    assert loan["monthly_eur"] == 1108  # 210k, 4 %, 25 years
    assert loan["rent_minus_instalment_eur"] == 1000 - 1108
    assert f["buyer"]["loan_terms"] == {"share_pct": 70.0, "rate_pct": 4.0, "years": 25}


def test_area_facts_are_named_and_extras_pass_through():
    x = AreaInsight(
        area="Νέα Ιωνία",
        n_fresh=300,
        median_ppm=2921.3,
        median_ppm_recent=None,
        n_recent=0,
        trend_early_ppm=None,
        trend_early_n=0,
        trend_late_ppm=None,
        trend_late_n=0,
        trend_pct=-0.028,
        cut_share=0.05,
        median_cut_pct=None,
        median_dom=40,
        rent_ppm=10.14,
        rent_samples=None,
        gross_yield=0.042,
        value_band=None,
        value_band_discount=None,
        good_stock=1,
        old_share=None,
        unknown_age_share=0.1,
        uc_unfinished=9,
        uc_checked=12,
        new_premium=0.642,
        why="πρόζα",
    )
    out = assistant._area(x)
    assert out["median_eur_per_m2"] == 2921 and out["eur_per_m2_trend_pct"] == -2.8
    assert out["new_build_premium_pct"] == 64.2 and out["under_construction_share_pct"] == 75.0
    assert "why" not in out and "score" not in out
    # a dict with a future (W12) field keeps it
    extra = assistant._area({"area": "Γαλάτσι", "line4_station": "Γαλάτσι", "gone_30d": 0.2})
    assert extra["line4_station"] == "Γαλάτσι" and extra["gone_30d"] == 0.2
    f = assistant.facts_for([_d("1")], None, area_rank=[x, {"area": "Αλλού"}])
    assert [a["area"] for a in f["areas"]] == ["Νέα Ιωνία"]  # only areas in the list


# ---- prompt assembly ----------------------------------------------------------------------


def test_brief_request(facts, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    req = assistant.brief_request(facts)
    assert req["model"] == "claude-test" and req["max_tokens"] == assistant.BRIEF_MAX_TOKENS
    assert "temperature" not in req  # the API rejects it for this model family
    assert "ΜΟΝΟ αριθμούς" in req["system"] and assistant.UNKNOWN in req["system"]
    assert "ιδανικό" in req["system"]  # the banned-adjective rule
    content = req["messages"][0]["content"]
    assert json.dumps(facts, ensure_ascii=False, default=str) in content
    assert "opening_offer" in content and "Σημείωμα επενδυτή" in content


def test_chat_request_keeps_last_six_turns(facts):
    history = []
    for i in range(10):
        history += [
            {"role": "user", "content": f"q{i}"},
            {"role": "assistant", "content": f"a{i}"},
        ]
    req = assistant.chat_request(facts, "Πόσο θα νοικιάσει;", history)
    assert req["max_tokens"] == 400
    assert len(req["messages"]) == 2 * assistant.HISTORY_TURNS + 1
    assert req["messages"][0]["content"] == "q4"
    assert req["messages"][-1] == {"role": "user", "content": "Πόσο θα νοικιάσει;"}
    assert '"listings"' in req["system"]


# ---- grounding ----------------------------------------------------------------------------


def test_grounding_accepts_numbers_from_facts(facts):
    ok = (
        "Το #2 έχει μικτή απόδοση 4,5 % έναντι 4 % του #1 και κοστίζει 20.000 € λιγότερο. "
        "Ξεκίνα από 282.000 € (−6 %): 120 μέρες στην αγορά. Ενοίκιο ~1.000 €/μήνα, "
        "3.750 €/τ.μ., κτίριο 2021, 300 χιλ. προϋπολογισμός, ελέγχθηκε 20/10."
    )
    assert assistant.ungrounded_numbers(ok, facts) == []


def test_grounding_flags_invented_numbers(facts):
    bad = "Απόδοση 6,3 % και τιμή 255.000 €, ενοίκιο 1.450 €, 3 φωτογραφίες, Γραμμή 1."
    assert assistant.ungrounded_numbers(bad, facts) == ["6,3 %", "255.000 €", "1.450 €"]


def test_grounding_tolerance_is_one_percent(facts):
    assert assistant.ungrounded_numbers("περίπου 302.500 €", facts) == []  # 300k +0,8 %
    assert assistant.ungrounded_numbers("περίπου 304.000 €", facts) == ["304.000 €"]


def test_checked_appends_note(facts):
    assert assistant.checked("Τιμή 300.000 €.", facts) == "Τιμή 300.000 €."
    assert assistant.checked("Τιμή 999.000 €.", facts).endswith("(έλεγξε: 999.000 €)")


# ---- brief with a stub client -------------------------------------------------------------


def _stub(text: str, stop: str = "end_turn"):
    calls = []

    def create(**kw):
        calls.append(kw)
        block = SimpleNamespace(type="text", text=text)
        return SimpleNamespace(content=[block], stop_reason=stop)

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def test_brief_uses_cache_and_flags_slips(facts):
    assistant._LOCAL_CACHE.clear()
    client, calls = _stub("Το #2: 4,5 % έναντι 4 %. Προσφορά 266.000 € (−5 %). Ενοίκιο 1.300 €.")
    out = assistant.brief(facts, client=client)
    assert out.endswith("(έλεγξε: 1.300 €)")
    assert assistant.brief(facts, client=client) == out and len(calls) == 1  # cached by hash


def test_brief_trims_cut_off_reply(facts):
    assistant._LOCAL_CACHE.clear()
    client, _ = _stub("Πρώτη γραμμή.\nΔεύτερη μισή γρα", stop="max_tokens")
    assert assistant.brief(facts, client=client) == "Πρώτη γραμμή."


def test_brief_none_without_key_or_listings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(assistant, "_api_key", lambda: "")
    assert assistant.brief({"listings": [{"price_eur": 1}]}) is None
    assert assistant.brief({"listings": []}, client=object()) is None


def test_brief_none_on_api_error(facts):
    assistant._LOCAL_CACHE.clear()

    def boom(**kw):
        raise RuntimeError("down")

    client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    assert assistant.brief(facts, client=client) is None


def test_docstring_is_greek_and_says_what_it_wont_do():
    doc = " ".join(assistant.__doc__.split())
    assert "Τι δεν θα σου πει" in doc and assistant.UNKNOWN in doc


# ---- live (needs ANTHROPIC_API_KEY and data/listings.db) ----------------------------------

DB = Path(__file__).resolve().parents[1] / "data" / "listings.db"


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.skipif(not DB.exists(), reason="needs data/listings.db (see docs/COORDINATION.md)")
def test_live_brief_is_grounded(monkeypatch):
    import scout.db as dbmod
    from scout.config import get_settings

    def reset():
        get_settings.cache_clear()
        dbmod._engine = dbmod._SessionFactory = None

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{DB}")
    reset()
    try:
        _live_brief()
    finally:
        monkeypatch.undo()
        reset()


def _live_brief():
    from scout import picks
    from scout.area_insights import rank_areas
    from scout.ui import queries

    listings = queries.load_listings()
    rents = queries.load_rent_comp_rows()
    intel = market_intel.build(listings)
    top = picks.find(listings, intel, rents, 300_000, top=3)
    assert len(top) == 3
    facts = assistant.facts_for(
        top, intel, rank_areas(listings, rents), {"budget": 300_000}, rent_rows=rents
    )
    assistant._LOCAL_CACHE.clear()
    text = assistant.brief(facts)
    assert text, "the API gave no brief"
    print("\n" + text)
    assert assistant.ungrounded_numbers(text, facts) == []
    Path(os.environ.get("ASSISTANT_BRIEF_OUT", "/dev/null")).write_text(text, encoding="utf-8")


# ---- panel --------------------------------------------------------------------------------


def _panel_app():
    from scout.ui import assistant

    facts = {"listings": [{"id": "xe:1", "price_eur": 300000}]}
    assistant.panel(facts, "t")


def test_panel_hidden_without_key(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setattr("scout.config.get_settings", lambda: SimpleNamespace(anthropic_api_key=""))
    at = AppTest.from_function(_panel_app).run()
    assert not at.exception
    assert not at.markdown and not at.chat_input


def test_panel_shows_chips_with_key(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    at = AppTest.from_function(_panel_app).run()
    assert not at.exception
    assert [m.value for m in at.markdown][0] == "**Ρώτα με**"
    assert len(at.chat_input) == 1
    assert SECRET not in str([m.value for m in at.markdown])
