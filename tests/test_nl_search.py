from __future__ import annotations

from datetime import date
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
    d = {**BASE, "area_m2": None, "bedrooms": None}
    assert match(d, SearchFilters(area_min=70, bedrooms_min=2)) is not None


def test_floor_filter_drops_unstated_floor():
    # XE omits the floor label on ground/basement flats, so "from 1st floor" must hide them.
    assert match({**BASE, "floor": None}, SearchFilters(floor_min=1)) is None
    assert match({**BASE, "floor": None}, SearchFilters()) is not None


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

    d = {**BASE, "score": 50, "value_gap_pct": 0.20, "value_confident": True, "year_built": 2015}
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
        "περιοχή: Χολαργός · τιμή έως 180.000 € · υπνοδωμάτια: 1 · μόνο από ιδιώτη · ανελκυστήρας"
    )
    assert "όλες οι αγγελίες" in describe(SearchFilters())


def test_area_matches_across_greek_case_endings():
    """The parser returns nominative names ('Παπάγος'); listings say 'Παπάγου' / 'Papagou'."""
    papagou = {**BASE, "neighborhood": "Παπάγου (Υπουργείο Μεταφορών)", "search_area": "Papagou"}
    assert match(papagou, SearchFilters(areas=["Παπάγος"])) is not None
    assert match(papagou, SearchFilters(areas=["Papagos"])) is not None
    agia = {**BASE, "neighborhood": "Αγίας Παρασκευής", "search_area": "Agia Paraskevi"}
    assert match(agia, SearchFilters(areas=["Αγία Παρασκευή"])) is not None
    assert match(BASE, SearchFilters(areas=["Μαρούσι"])) is None


def test_area_uses_the_listing_location_not_the_scraped_search_area():
    """XE's 'Cholargos' search also returns Χαλάνδρι flats — those must not match Χολαργός."""
    halandri = {**BASE, "neighborhood": "Χαλάνδρι (Κάτω Χαλάνδρι)", "search_area": "Cholargos"}
    assert match(halandri, SearchFilters(areas=["Χολαργός", "Cholargos"])) is None
    no_location = {**BASE, "neighborhood": None, "address": None, "search_area": "Cholargos"}
    assert match(no_location, SearchFilters(areas=["Cholargos"])) is not None


def test_old_buildings_are_discounted_and_unfinished_score_low():
    from scout.nl_search import advise

    new = {**BASE, "score": 80, "year_built": 2018}
    old = {**BASE, "score": 80, "year_built": 1965}
    renovated = {**old, "renovated_year": 2021}
    assert advise(new)["score"] == 80
    assert advise(old)["score"] == 36 and advise(old)["age"] >= 60
    assert advise(renovated)["score"] == 80
    assert advise({**new, "is_unfinished": True})["score"] == 20  # × 0.25
    this_year = {**new, "year_built": date.today().year}  # maybe still a shell, sold off-plan
    assert advise(this_year)["score"] == 48


def test_unfinished_hidden_unless_asked_and_year_min_filters():
    unfinished = {**BASE, "is_unfinished": True}
    assert match(unfinished, SearchFilters()) is None
    assert match(unfinished, SearchFilters(include_unfinished=True)) is not None
    assert match({**BASE, "year_built": 1975}, SearchFilters(year_min=2000)) is None
    assert match({**BASE, "year_built": 2005}, SearchFilters(year_min=2000)) is not None
    assert match(BASE, SearchFilters(year_min=2000)) is None  # unknown year can't prove it


def test_candidates_hide_stale_excluded_and_suspect():
    from scout.nl_search import candidates

    rows = [
        {**BASE, "is_fresh": True},
        {**BASE, "is_fresh": False},
        {**BASE, "excluded": True},
        {**BASE, "is_suspect": True},
    ]
    assert len(candidates(rows)) == 1
    assert len(candidates(rows, include_stale=True)) == 2


def test_advise_breakdown_follows_the_score_components():
    from scout.nl_search import advise

    d = {**BASE, "score": 60, "year_built": 2018, "gross_yield": 0.06}
    parts = dict(advise(d, comp_pct=-0.2)["parts"])
    assert parts == {"τιμή vs παρόμοια": 1, "ηλικία": 1, "απόδοση": 1}
    old = {**d, "year_built": 1960, "gross_yield": 0.03}
    parts = dict(advise(old, comp_pct=0.2)["parts"])
    assert parts == {"τιμή vs παρόμοια": -1, "ηλικία": -1, "απόδοση": -1}
    unknown = dict(advise({**BASE, "score": 60, "year_built": None})["parts"])
    assert unknown == {"ηλικία": None}  # no comps / no yield: not shown, not guessed
    shell = advise({**d, "is_unfinished": True}, comp_pct=-0.2)
    assert ("ημιτελές", -1) in shell["parts"] and shell["score"] < advise(d, -0.2)["score"] / 3


# ---- why a listing is hidden (the search page's "Κρύβονται N" line) ------------------------


def test_year_filter_is_the_build_year_not_the_renovation():
    from scout.nl_search import why_hidden

    old_renovated = {**BASE, "year_built": 1975, "renovated_year": 2021}
    assert why_hidden(old_renovated, SearchFilters(year_min=2015)) == "year"
    assert why_hidden({**BASE, "year_built": 2016}, SearchFilters(year_min=2015)) is None


def test_undeclared_floor_or_year_is_its_own_reason_and_can_be_included():
    from scout.nl_search import why_hidden

    f = SearchFilters(floor_min=2, year_min=2015)
    no_floor = {**BASE, "floor": None, "year_built": 2018}
    no_year = {**BASE, "year_built": None}
    assert why_hidden(no_floor, f) == why_hidden(no_year, f) == "undeclared"
    inc = f.model_copy(update={"include_undeclared": True})
    assert why_hidden(no_floor, inc) is None and why_hidden(no_year, inc) is None
    # a KNOWN wrong year is not "undeclared", even if the floor is missing
    assert why_hidden({**no_floor, "year_built": 1990}, inc) == "year"
    # without a floor/year filter nothing is hidden for not stating them
    assert why_hidden(no_floor, SearchFilters()) is None


def test_first_failing_reason_is_reported_in_order():
    from scout.nl_search import HIDE_ORDER, why_hidden

    d = {**BASE, "price": 900_000, "floor": 0.0, "year_built": 1960, "is_unfinished": True}
    f = SearchFilters(areas=["Παπάγου"], price_max=300_000, floor_min=1, year_min=2000)
    assert why_hidden(d, f) == "area"
    assert why_hidden(d, f.model_copy(update={"areas": []})) == "price"
    f2 = f.model_copy(update={"areas": [], "price_max": None})
    assert why_hidden(d, f2) == "unfinished"
    assert why_hidden(d, f2.model_copy(update={"include_unfinished": True})) == "floor"
    assert HIDE_ORDER.index("floor") < HIDE_ORDER.index("year") < HIDE_ORDER.index("undeclared")


def test_match_agrees_with_why_hidden():
    from scout.nl_search import why_hidden

    f = SearchFilters(floor_min=2, year_min=2010, price_max=200_000)
    for d in (BASE, {**BASE, "year_built": 2012}, {**BASE, "year_built": 2012, "floor": 1.0}):
        assert (match(d, f) is None) == (why_hidden(d, f) is not None)


def test_describe_mentions_undeclared_only_with_a_floor_or_year_filter():
    from scout.nl_search import describe

    assert "δεν γράφουν όροφο" not in describe(SearchFilters(include_undeclared=True))
    assert "όσα δεν γράφουν όροφο ή έτος" in describe(
        SearchFilters(floor_min=2, include_undeclared=True)
    )
