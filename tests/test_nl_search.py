from __future__ import annotations

from types import SimpleNamespace

import pytest

from scout.nl_search import MAX_CHARS, SearchFilters, SearchParseError, match, parse_query

BASE = {
    "price": 170_000,
    "area_m2": 65.0,
    "bedrooms": 1,
    "floor": 3.0,
    "neighborhood": "Χολαργός",
    "address": None,
    "search_area": "Cholargos",
    "title": "Δυάρι με ανελκυστήρα",
    "is_private_seller": True,
    "renovated_year": None,
}


def test_empty_filters_match_everything_at_100():
    assert match(BASE, SearchFilters()) == (100, [])


def test_area_matches_accent_and_latin_insensitively():
    assert match(BASE, SearchFilters(areas=["Χολαργος"])) is not None
    assert match(BASE, SearchFilters(areas=["cholargos"])) is not None
    assert match(BASE, SearchFilters(areas=["Παπάγου"])) is None


def test_hard_bounds_exclude():
    assert match(BASE, SearchFilters(price_max=150_000)) is None
    assert match(BASE, SearchFilters(area_min=70)) is None
    assert match(BASE, SearchFilters(bedrooms_min=2)) is None
    assert match(BASE, SearchFilters(floor_min=4)) is None
    assert match(BASE, SearchFilters(private_only=True, price_max=180_000)) is not None
    assert match({**BASE, "is_private_seller": False}, SearchFilters(private_only=True)) is None


def test_unknown_fields_do_not_exclude():
    d = {**BASE, "area_m2": None, "bedrooms": None, "floor": None}
    assert match(d, SearchFilters(area_min=70, bedrooms_min=2, floor_min=4)) is not None


def test_wants_raise_score_and_report_reasons():
    pct, reasons = match(BASE, SearchFilters(wants=["elevator"]))
    assert pct == 100 and any("ανελκυστήρα" in r for r in reasons)
    pct, _ = match(BASE, SearchFilters(wants=["elevator", "parking"]))
    assert pct == 80  # 60 + 40 * 1/2
    pct, _ = match(BASE, SearchFilters(wants=["parking"]))
    assert pct == 60  # unconfirmed is neutral-low, never an exclusion


def test_renovated_via_renovated_year():
    pct, _ = match({**BASE, "renovated_year": 2020}, SearchFilters(wants=["renovated"]))
    assert pct == 100


def _client(content=None, boom=None):
    calls = []

    def create(**kw):
        calls.append(kw)
        if boom:
            raise boom
        return SimpleNamespace(content=content)

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def test_parse_query_returns_filters_and_forces_tool():
    block = SimpleNamespace(type="tool_use", input={"areas": ["Χολαργός"], "price_max": 180000})
    client, calls = _client([block])
    f = parse_query("δυάρι στον Χολαργό έως 180Χ", client=client)
    assert f.areas == ["Χολαργός"] and f.price_max == 180_000
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "set_filters"}


def test_parse_query_truncates_text():
    client, calls = _client([SimpleNamespace(type="tool_use", input={})])
    parse_query("α" * 900, client=client)
    assert len(calls[0]["messages"][0]["content"]) == MAX_CHARS


@pytest.mark.parametrize(
    "content,boom",
    [
        ([SimpleNamespace(type="text", text="no tool")], None),
        ([SimpleNamespace(type="tool_use", input={"price_max": "lots"})], None),
        (None, RuntimeError("api down")),
    ],
)
def test_parse_query_failures_raise(content, boom):
    client, _ = _client(content, boom)
    with pytest.raises(SearchParseError):
        parse_query("κάτι", client=client)


def test_parse_query_empty_or_missing_key(monkeypatch):
    with pytest.raises(SearchParseError):
        parse_query("   ", client=object())
    monkeypatch.setattr(
        "scout.nl_search.get_settings", lambda: SimpleNamespace(anthropic_api_key="")
    )
    with pytest.raises(SearchParseError):
        parse_query("δυάρι")


def test_budget_is_total_cash_including_buying_costs():
    # 170k + ~7.15% private-seller costs ≈ 182k
    assert match(BASE, SearchFilters(budget=185_000)) is not None
    assert match(BASE, SearchFilters(budget=175_000)) is None


def test_advise_rewards_discount_to_model_value():
    from scout.nl_search import advise

    d = {**BASE, "score": 50, "value_gap_pct": 0.20, "value_confident": True}
    assert advise(d)["score"] == 58  # 0.6*50 + 0.4*70
    assert advise({**d, "value_confident": False})["score"] == 50
    assert advise({**d, "price_dropped": True})["score"] == 62


def test_describe_is_plain_greek():
    from scout.nl_search import describe

    f = SearchFilters(
        areas=["Χολαργός"],
        price_max=180_000,
        bedrooms_min=1,
        bedrooms_max=1,
        private_only=True,
        wants=["elevator"],
    )
    assert describe(f) == (
        "περιοχή: Χολαργός · τιμή 0–180,000 € · υπνοδωμάτια: 1 · μόνο ιδιώτης · ανελκυστήρας"
    )
    assert "τα πάντα" in describe(SearchFilters())


def test_area_matches_across_greek_case_endings():
    """The parser returns nominative names ('Παπάγος'); listings say 'Παπάγου' / 'Papagou'."""
    papagou = {**BASE, "neighborhood": "Παπάγου (Υπουργείο Μεταφορών)", "search_area": "Papagou"}
    assert match(papagou, SearchFilters(areas=["Παπάγος"])) is not None
    assert match(papagou, SearchFilters(areas=["Papagos"])) is not None
    agia = {**BASE, "neighborhood": "Αγίας Παρασκευής", "search_area": "Agia Paraskevi"}
    assert match(agia, SearchFilters(areas=["Αγία Παρασκευή"])) is not None
    assert match(BASE, SearchFilters(areas=["Μαρούσι"])) is None
