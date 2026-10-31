from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from scout import area_insights as ai

YEAR = 2026
OCT = datetime(2026, 10, 30)
JUL = datetime(2026, 7, 14)


def flat(area="Χολαργός", ppm=3000.0, m2=80.0, **kw) -> dict:
    d = {
        "neighborhood": f"{area} (Κέντρο)",
        "search_area": "Cholargos",
        "price": ppm * m2,
        "first_price": None,
        "area_m2": m2,
        "price_per_m2": ppm,
        "floor": 2.0,
        "year_built": 2015,
        "renovated_year": None,
        "first_seen": JUL,
        "last_seen": OCT,
        "is_fresh": True,
        "price_dropped": False,
        "days_on_market": 100,
        "excluded": False,
        "is_suspect": False,
        "is_unfinished": False,
        "lat": 38.0,
    }
    d.update(kw)
    return d


def many(n, **kw) -> list[dict]:
    return [flat(**kw) for _ in range(n)]


def rent(area, hood, ppm, samples=0):
    return {"area": area, "neighborhood": hood, "rent_per_m2": ppm, "samples": samples}


# ---- eligibility & thresholds ------------------------------------------------------------


def test_area_below_min_fresh_is_dropped():
    rows = many(ai.MIN_FRESH - 1) + many(5, is_fresh=False)
    assert ai.rank_areas(rows, year=YEAR) == []
    assert len(ai.rank_areas(many(ai.MIN_FRESH), year=YEAR)) == 1


def test_unusable_and_out_of_region_rows_are_ignored():
    good = many(ai.MIN_FRESH)
    junk = [
        flat(excluded=True, ppm=100),
        flat(is_suspect=True, ppm=100),
        flat(is_unfinished=True, ppm=100),
        flat(price_per_m2=None),
        flat(lat=35.3, ppm=100),  # Heraklion, Crete
    ]
    (x,) = ai.rank_areas(good + junk, year=YEAR)
    assert x.n_fresh == ai.MIN_FRESH and x.median_ppm == 3000


def test_areas_filter_uses_search_area():
    rows = many(25) + many(25, area="Γαλάτσι", search_area="Galatsi")
    assert [x.area for x in ai.rank_areas(rows, areas=["Galatsi"], year=YEAR)] == ["Γαλάτσι"]


def test_central_athens_uses_quarter_name():
    assert ai.area_name("Αθήνα (Αμπελόκηποι)") == "Αμπελόκηποι"
    assert ai.area_name("Χολαργός (Άνω Χολαργός)") == "Χολαργός"


# ---- metrics -----------------------------------------------------------------------------


def test_medians_overall_and_recent():
    rows = many(10, ppm=4000, year_built=2020) + many(15, ppm=2000, year_built=1975)
    (x,) = ai.rank_areas(rows, year=YEAR)
    assert x.n_fresh == 25
    assert x.median_ppm == 2000
    assert x.median_ppm_recent == 4000 and x.n_recent == 10
    assert x.old_share == pytest.approx(15 / 25)


def test_trend_uses_first_price_for_july_and_current_for_late_october():
    # 12 gone July listings first asked 2000; 12 live ones now at 2200 (first seen in Oct).
    early = many(12, ppm=2000, is_fresh=False, last_seen=datetime(2026, 8, 1))
    late = many(12, ppm=2200, first_seen=OCT)
    # A July listing still live, cut from 2500 to 2200: counts 2500 in July, 2200 in Oct.
    cut = many(
        10, ppm=2200, first_price=2500 * 80, price_dropped=True, first_seen=JUL, last_seen=OCT
    )
    (x,) = ai.rank_areas(early + late + cut, year=YEAR)
    assert x.trend_early_n == 22 and x.trend_late_n == 22
    assert x.trend_early_ppm == 2000 and x.trend_late_ppm == 2200
    assert x.trend_pct == pytest.approx(0.10)


def test_trend_is_none_when_a_cohort_is_small():
    rows = many(ai.MIN_TREND - 1, first_seen=JUL) + many(60, first_seen=OCT)
    rents = [rent("Cholargos", None, 15.0, 40), rent("Cholargos", "Χολαργός (Κέντρο)", 15, 40)]
    (x,) = ai.rank_areas(rows, rents, year=YEAR)
    assert x.trend_pct is None and x.trend_early_n == ai.MIN_TREND - 1
    assert x.components["momentum"] == ai.NEUTRAL
    assert any("Δεν ξέρουμε ακόμα αν οι τιμές ανεβαίνουν" in r for r in x.risks)


def test_price_cuts_and_days_on_market():
    cut = many(5, ppm=2700, price=216_000, first_price=240_000, price_dropped=True)
    rows = cut + many(15, days_on_market=40)
    (x,) = ai.rank_areas(rows, year=YEAR)
    assert x.cut_share == pytest.approx(5 / 20)
    assert x.median_cut_pct == pytest.approx(0.10)
    assert x.median_dom == 40


def test_gross_yield_only_with_rent():
    rows = many(25, ppm=3000)
    (no_rent,) = ai.rank_areas(rows, year=YEAR)
    assert no_rent.gross_yield is None and no_rent.components["yield"] == ai.NEUTRAL
    assert any("αγγελίες ενοικίασης" in r for r in no_rent.risks)

    rents = [rent("Cholargos", None, 12.5, 40), rent("Cholargos", "Χολαργός (Κέντρο)", 13, 5)]
    (x,) = ai.rank_areas(rows, rents, year=YEAR)
    assert x.rent_ppm == 12.5 and x.rent_samples == 40
    assert x.gross_yield == pytest.approx(12 * 12.5 / 3000)


def test_rent_mapping_owner_and_neighbourhood_fallback():
    rows = [
        rent("Cholargos", None, 12.6, 0),
        rent("Cholargos", "Χολαργός (Άνω Χολαργός)", 12.2, 0),
        rent("Cholargos", "Χολαργός (Τσακός)", 13.4, 0),
        rent("Papagou", None, 12.0, 0),
        rent("Papagou", "Παπάγου (Άλσος)", 13.5, 0),
        rent("Papagou", "Παπάγου", 11.2, 0),
        rent("Papagou", "Χολαργός (Άνω Χολαργός)", 15.4, 0),
        rent("Nea Filadelfeia", None, 9.4, 0),
        rent("Nea Filadelfeia", "Νέα Φιλαδέλφεια (Αμπέλια)", 10.7, 0),
        rent("Nea Filadelfeia", "Νέα Φιλαδέλφεια (Μάδυτος)", 9.3, 0),
        rent("Nea Filadelfeia", "Αχαρνές (Λυκότρυπα)", 8.75, 3),
    ]
    m = ai.rent_by_area(rows)
    assert m["Χολαργός"] == (12.6, None)  # samples 0 = not recorded
    assert m["Παπάγου"] == (12.0, None)
    assert m["Νέα Φιλαδέλφεια"] == (9.4, None)
    assert m["Αχαρνές"] == (8.75, 3)  # owns no search area: its neighbourhood rows


def test_value_band_and_good_stock():
    new = many(6, ppm=5000, year_built=2024)
    mid = many(6, ppm=3500, year_built=2014)  # 6–15y: 30% under new
    older = many(6, ppm=4000, year_built=2000)  # 16–30y: 20% under new
    # Under the 6–15y median (3500): one on 2nd floor counts, a ground floor and an unknown
    # floor do not; an old (46+) flat never counts.
    cheap = [
        flat(ppm=3000, year_built=2014, floor=2.0),
        flat(ppm=3000, year_built=2014, floor=0.0),
        flat(ppm=3000, year_built=2014, floor=None),
        flat(ppm=1000, year_built=1970, floor=3.0),
    ]
    (x,) = ai.rank_areas(new + mid + older + cheap, year=YEAR)
    assert x.value_band == ai.AGE_BANDS[1][2]
    assert x.value_band_discount == pytest.approx(1 - 3500 / 5000)
    assert x.good_stock == 1


def test_value_band_none_without_new_builds():
    (x,) = ai.rank_areas(many(25, year_built=2010), year=YEAR)
    assert x.value_band is None and x.value_band_discount is None


# ---- ranking & text ----------------------------------------------------------------------


def test_ranking_prefers_yield_and_affordability():
    cheap = many(30, area="Γαλάτσι", search_area="Galatsi", ppm=2500)
    dear = many(30, area="Ψυχικό", search_area="Psychiko", ppm=4500)
    rents = [
        rent("Galatsi", None, 12.0, 30),
        rent("Galatsi", "Γαλάτσι (Κέντρο)", 12.0, 30),
        rent("Psychiko", None, 12.0, 30),
        rent("Psychiko", "Ψυχικό (Κέντρο)", 12.0, 30),
    ]
    ranked = ai.rank_areas(cheap + dear, rents, year=YEAR)
    assert [x.area for x in ranked] == ["Γαλάτσι", "Ψυχικό"]
    top, bottom = ranked
    assert top.gross_yield > bottom.gross_yield
    assert top.components["affordability"] > bottom.components["affordability"]
    assert 0 <= bottom.score < top.score <= 100
    assert top.score == pytest.approx(
        100 * sum(ai.WEIGHTS[k] * v for k, v in top.components.items()), abs=0.1
    )


def test_reasons_and_risks_are_factual_greek():
    rows = many(25, ppm=2500) + many(5, ppm=2500, price_dropped=True, first_price=220_000)
    rows += many(10, ppm=2600, first_seen=OCT)
    rents = [rent("Cholargos", None, 12.0, 40), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 40)]
    (x,) = ai.rank_areas(rows, rents, year=YEAR)
    assert 2 <= len(x.reasons) <= 4 and 1 <= len(x.risks) <= 2
    assert any("Μικτή απόδοση 5,8 %" in r and "(40 αγγελίες)" in r for r in x.reasons)
    assert any("Μόνο 40 αγγελίες σήμερα" in r for r in x.risks)
    assert all(any(ch.isdigit() for ch in r) for r in x.reasons)


def test_falling_prices_and_old_stock_are_risks():
    early = many(15, ppm=3000, is_fresh=False, year_built=1970)
    late = many(60, ppm=2700, first_seen=OCT, year_built=1970)
    (x,) = ai.rank_areas(early + late, year=YEAR)
    assert x.trend_pct == pytest.approx(-0.10)
    assert x.risks[0].startswith("Οι τιμές έπεσαν 10,0 % από τον Ιούλιο")
    assert len(x.risks) == 2  # capped
    assert not any("πάνω από τον Ιούλιο" in r for r in x.reasons)


def test_heraklion_crete_never_appears():
    """XE's "Irakleio" search returns Heraklion, Crete, geocoded onto the Attica centroid
    (so the latitude band passes it): bare "Ηράκλειο" and Cretan villages are dropped, and
    so is that search's (Cretan) rent. Attica-Heraklion quarters in brackets still count."""
    crete = many(30, neighborhood="Ηράκλειο", search_area="Irakleio", lat=38.05)
    crete += many(25, neighborhood="Σκαλάνι", search_area="Irakleio", lat=38.05)
    attica = many(ai.MIN_FRESH, neighborhood="Ηράκλειο (Ηπειρώτικα)", search_area="Pefki", ppm=2800)
    rents = [rent("Irakleio", None, 11.0, 40), rent("Irakleio", "Ηράκλειο", 11.0, 40)]
    (x,) = ai.rank_areas(crete + attica, rents, year=YEAR)
    assert x.area == "Ηράκλειο" and x.n_fresh == ai.MIN_FRESH and x.median_ppm == 2800
    assert x.rent_ppm is None
    assert ai.rank_areas(crete, rents, year=YEAR) == []


def test_unrecorded_rent_samples_read_as_dash():
    rows = many(25, ppm=3000)
    rents = [rent("Cholargos", None, 12.0, 0), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 0)]
    (x,) = ai.rank_areas(rows, rents, year=YEAR)
    assert x.rent_samples is None
    assert any("δεν ξέρουμε από πόσες αγγελίες" in r for r in x.reasons)


# ---- per-area facts, explained why, decision sentences -----------------------------------


def _stock(n_new=6, n_old=6, **kw):
    """Fresh flats: ≤5-year at 4000 €/m², 16+-year at 2500 €/m², padded to MIN_FRESH."""
    rows = many(n_new, ppm=4000, year_built=2024, **kw) + many(
        n_old, ppm=2500, year_built=1990, **kw
    )
    return rows + many(max(0, 25 - len(rows)), ppm=3000, year_built=2015, **kw)


def test_new_build_premium_vs_old_stock():
    (x,) = ai.rank_areas(_stock(), year=YEAR)
    assert (x.n_new, x.ppm_new, x.n_old, x.ppm_old) == (6, 4000, 6, 2500)
    assert x.new_premium == pytest.approx(0.6)
    (y,) = ai.rank_areas(_stock(n_new=4), year=YEAR)  # < MIN_BAND new → no premium
    assert y.ppm_new is None and y.new_premium is None and y.n_new == 4


def test_only_upper_floor_flats_count():
    rows = _stock() + many(10, floor=0.0) + many(10, floor=None) + many(10, title="Μονοκατοικία")
    (x,) = ai.rank_areas(rows, year=YEAR)
    assert x.n_fresh == 25


def test_under_construction_share_counts_only_checked_pages():
    rows = _stock()
    rows += many(2, year_built=2026, is_unfinished=True, page_checked=True)
    rows += many(3, year_built=2024, page_checked=True)  # finished, checked
    rows += many(4, year_built=2026, is_unfinished=True, page_checked=False)  # not read: ignored
    rows += many(5, year_built=2024, page_checked=False)  # not read: ignored
    (x,) = ai.rank_areas(rows, year=YEAR)
    assert (x.uc_unfinished, x.uc_checked) == (2, 5)
    assert x.n_fresh == 25 + 3 + 5  # flagged ones never enter the medians


def test_stations_come_from_neighbourhoods():
    rows = _stock() + many(3, neighborhood="Χολαργός (Περισσός)")
    # the Περισσός key lives in picks.STATIONS
    (x,) = ai.rank_areas(rows, year=YEAR)
    assert x.stations == ["ΗΣΑΠ Περισσός"]
    (y,) = ai.rank_areas(_stock(), year=YEAR)
    assert y.stations == []


def test_why_is_a_filled_template_without_adjectives():
    rows = _stock(neighborhood="Χολαργός (Περισσός)")
    rents = [rent("Cholargos", None, 11.2, 38), rent("Cholargos", "Χολαργός (Περισσός)", 11.2, 38)]
    (x,) = ai.rank_areas(rows, rents, year=YEAR)
    assert x.why == (
        "Μικτή απόδοση 4,5 % (1η από 1 περιοχή). Ενοίκιο (εκτίμηση) 11,2 €/τ.μ. τον μήνα από 38 "
        "αγγελίες ενοικίασης· για νεόδμητο ζητούν 60 % περισσότερα από ένα παλιό (6 και 6 "
        "αγγελίες)· ΗΣΑΠ Περισσός"
    )


def test_why_leaves_out_missing_parts():
    (x,) = ai.rank_areas(many(25), year=YEAR)
    assert x.why.startswith("25 αγγελίες, ζητούν συνήθως 3.000")


def test_decision_sentences_have_numbers_and_budget():
    cheap_rent = [rent("Cholargos", None, 9.0, 30), rent("Cholargos", "Χολαργός (Κέντρο)", 9, 30)]
    a = many(61, ppm=3000)
    b = many(55, area="Παπάγου", search_area="Papagou", ppm=2500, price=200_000)
    b += many(
        5,
        area="Παπάγου",
        search_area="Papagou",
        ppm=2500,
        year_built=2024,
        neighborhood="Παπάγου (Κέντρο)",
    )
    c = many(
        30,
        area="Μαρούσι",
        search_area="Marousi",
        ppm=3500,
        year_built=2024,
        neighborhood="Μαρούσι (Κέντρο)",
        price=250_000,
        page_checked=True,
    )
    rents = cheap_rent + [
        rent("Papagou", None, 12.0, 20),
        rent("Papagou", "Παπάγου (Κέντρο)", 12, 20),
    ]
    ranked = ai.rank_areas(a + b + c, rents, year=YEAR)
    s = ai.decision(ranked, 300_000)
    assert (
        s[0].startswith("Για απόδοση: Παπάγου. Μικτή απόδοση ")
        and "ενοίκιο (εκτίμηση) 12,0 €/τ.μ." in s[0]
    )
    assert s[1].startswith("Για εύκολη μεταπώληση: Χολαργός. 61 σπίτια προς πώληση")
    assert s[2].startswith("Για ανατίμηση:")
    assert s[3].startswith("Για νεόδμητο κοντά σε σταθμό έως 300.000 €: Μαρούσι (ΗΣΑΠ Μαρούσι).")
    assert "30 αγγελίες, από αυτές 30 με ελεγμένη περιγραφή" in s[3]
    assert all(any(ch.isdigit() for ch in line) for line in s)


def test_decision_says_when_nothing_is_in_budget():
    ranked = ai.rank_areas(many(60), year=YEAR)
    assert ai.decision(ranked, 300_000)[-1] == (
        "Νεόδμητο έως 300.000 € σε γειτονιά με σταθμό: δεν υπάρχει σήμερα καμία αγγελία."
    )


def test_decision_still_answers_on_small_samples_and_says_so():
    rents = [rent("Cholargos", None, 12.0, 30), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 30)]
    ranked = ai.rank_areas(many(25), rents, year=YEAR)
    s = ai.decision(ranked, 300_000)
    assert s[0].startswith("Για απόδοση: Χολαργός") and s[0].endswith(
        "Λίγες αγγελίες ακόμα, κρατάμε επιφύλαξη."
    )


def test_gross_yield_new_uses_the_new_build_median():
    rents = [rent("Cholargos", None, 12.0, 38), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 38)]
    (x,) = ai.rank_areas(_stock(), rents, year=YEAR)
    assert x.gross_yield_new == pytest.approx(12 * 12 / 4000)  # 3,6 %
    assert x.gross_yield == pytest.approx(12 * 12 / x.median_ppm)
    (y,) = ai.rank_areas(_stock(n_new=4), rents, year=YEAR)  # < MIN_BAND new builds
    assert y.gross_yield_new is None
    (z,) = ai.rank_areas(_stock(), year=YEAR)  # no rent
    assert z.gross_yield_new is None


def test_decision_yield_sentence_splits_old_and_new():
    rents = [rent("Cholargos", None, 12.0, 38), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 38)]
    ranked = ai.rank_areas(_stock() + many(30, ppm=3000, year_built=2015), rents, year=YEAR)
    first = ai.decision(ranked, 300_000)[0]
    assert first == (
        "Για απόδοση: Χολαργός. Μικτή απόδοση 4,8 % στα παλιά και 3,6 % στα νεόδμητα, "
        "με ενοίκιο (εκτίμηση) 12,0 €/τ.μ. τον μήνα, όσο ζητούν στη γειτονιά. "
        "55 σπίτια προς πώληση."
    )


def test_why_names_the_rent_sample_as_rent_listings():
    rents = [rent("Cholargos", None, 12.0, 38), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 38)]
    (x,) = ai.rank_areas(_stock(), rents, year=YEAR)
    assert "από 38 αγγελίες ενοικίασης" in x.why


# ---- round 3: investor insights ----------------------------------------------------------


def _cohort(month: int, n: int, ppm: float, **kw) -> list[dict]:
    return many(n, ppm=ppm, first_seen=datetime(2026, month, 10), **kw)


def test_price_series_is_median_by_first_seen_month_with_n():
    rows = _cohort(4, 15, 2000) + _cohort(10, 15, 2100) + _cohort(10, 5, 9000)
    s = ai.price_series(rows, date(2026, 10, 30))
    assert s == [("2026-04", 2000.0, 15), ("2026-10", 2100.0, 20)]


def test_price_series_ignores_months_older_than_twelve():
    rows = _cohort(10, 3, 2000) + many(3, first_seen=datetime(2025, 9, 1))
    assert [k for k, _, _ in ai.price_series(rows, date(2026, 10, 30))] == ["2026-10"]


def test_trend_6m_needs_both_months_with_enough_listings():
    end = date(2026, 10, 30)
    ok = [("2026-04", 2000.0, 15), ("2026-10", 2082.0, 15)]
    pct, n = ai.trend_6m(ok, end)
    assert pct == pytest.approx(0.041) and n == (15, 15)
    assert ai.trend_6m([("2026-04", 2000.0, 14), ("2026-10", 2082.0, 40)], end)[0] is None
    assert ai.trend_6m([("2026-10", 2082.0, 40)], end) == (None, (0, 40))


def test_area_trend_6m_flows_into_the_insight():
    rows = _cohort(4, 15, 2000) + _cohort(10, 15, 2082)
    x = ai.rank_areas(rows, year=YEAR)[0]
    assert x.trend_pct_6m == pytest.approx(0.041) and x.trend_6m_n == (15, 15)
    assert [n for _, _, n in x.trend_series] == [15, 15]
    # ...and the decision sentence quotes it with its basis
    s = [t for t in ai.decision([x], 300_000) if t.startswith("Για ανατίμηση")][0]
    assert "Η τιμή ανά τ.μ. άλλαξε +4,1 % σε 6 μήνες (15 και 15 αγγελίες)" in s


def test_trend_6m_is_none_without_history():
    x = ai.rank_areas(many(25), year=YEAR)[0]
    assert x.trend_pct_6m is None
    assert x.trend_series[0][2] == 25  # only July: no month 6 earlier


def _weekly_life(n_per_week=40, gone_after=None):
    """Weekly scrapes from 1 Jan; listings first seen on week 1; the first ``gone_after``
    fraction vanish after 3 weeks (21 days)."""
    rows = []
    start = datetime(2026, 1, 1)
    for i in range(n_per_week):
        gone = gone_after is not None and i < gone_after * n_per_week
        last = start + timedelta(days=7 * (3 if gone else 12))
        rows.append(
            flat(
                first_seen=start + timedelta(days=7),
                last_seen=last,
                status="gone" if gone else "active",
            )
        )
    # a baseline listing seen on every scrape keeps all weekly scrape days in the record
    for w in range(13):
        rows.append(flat(first_seen=start, last_seen=start + timedelta(days=7 * w), status="gone"))
    return rows


def test_liquidity_share_gone_within_windows_and_label():
    life = _weekly_life(40, gone_after=0.5)
    days, start = ai.scrape_context(life)
    stats = ai.liquidity_stats(life, days, start)
    assert stats[30] == (0.5, 40) and stats[60] == (0.5, 40)
    assert ai.liquidity_label(0.5) == "γρήγορη"
    assert ai.liquidity_label(0.2) == "μέτρια"
    assert ai.liquidity_label(0.1) == "αργή"
    assert ai.liquidity_label(None) is None


def test_liquidity_needs_min_cohort_and_regular_scrapes():
    life = _weekly_life(ai.MIN_LIQ - 1, gone_after=0.5)
    days, start = ai.scrape_context(life)
    assert ai.liquidity_stats(life, days, start)[60][0] is None  # cohort too small
    # an 80-day hole in the scrape record restarts the regular run after it
    hole = _weekly_life(40, 0.5) + [flat(first_seen=datetime(2026, 7, 1), last_seen=OCT)]
    _, s2 = ai.scrape_context(hole)
    assert s2 == date(2026, 7, 1) or s2 == date(2026, 10, 30)
    assert s2 > date(2026, 3, 1)


def test_unconfirmed_disappearances_do_not_count():
    # listings last seen just before an 80-day hole: we do not know when they went
    life = [
        flat(first_seen=datetime(2026, 8, 1), last_seen=datetime(2026, 8, 5), status="gone")
        for _ in range(40)
    ] + [flat(first_seen=datetime(2026, 7, 20), last_seen=OCT) for _ in range(5)]
    days, start = ai.scrape_context(life)
    assert ai.liquidity_stats(life, days, start)[30] == (None, 0)


def test_rank_areas_attaches_liquidity_from_lifecycle():
    life = _weekly_life(40, gone_after=0.5)
    x = ai.rank_areas(many(25), year=YEAR, lifecycle=life)[0]
    assert x.liquidity == "γρήγορη" and x.gone_60 == 0.5 and x.gone_n_60 == 40
    text = ai.liquidity_text(x)
    assert text.startswith("γρήγορη: το 50 % κατέβηκε μέσα σε 60 μέρες (από 40 αγγελίες)")
    assert "τουλάχιστον 35 %" in ai.LIQUIDITY_THRESHOLDS
    assert "κάτω από 15 %" in ai.LIQUIDITY_THRESHOLDS


def test_liquidity_unknown_says_why():
    x = ai.rank_areas(many(25), year=YEAR)[0]  # active-only input: no history
    assert x.liquidity is None
    assert ai.liquidity_text(x).startswith("δεν το ξέρουμε ακόμα")


def test_supply_per_rent_listing_and_relative_to_median():
    a = many(60, ppm=2500)
    b = many(60, area="Παπάγου", search_area="Papagou", ppm=2500)
    c = many(60, area="Μαρούσι", search_area="Marousi", ppm=2500)
    rents = [
        rent("Cholargos", None, 12, 30),
        rent("Cholargos", "Χολαργός (Κέντρο)", 12, 30),
        rent("Papagou", None, 12, 60),
        rent("Papagou", "Παπάγου (Κέντρο)", 12, 60),
        rent("Marousi", None, 12, 10),
        rent("Marousi", "Μαρούσι (Κέντρο)", 12, 10),
    ]
    got = {x.area: x for x in ai.rank_areas(a + b + c, rents, year=YEAR)}
    assert got["Χολαργός"].supply_per_rent == pytest.approx(2.0)
    assert got["Παπάγου"].supply_per_rent == pytest.approx(1.0)
    assert got["Μαρούσι"].supply_per_rent == pytest.approx(6.0)
    assert got["Χολαργός"].supply_rel == pytest.approx(1.0)  # the median
    assert got["Μαρούσι"].supply_rel == pytest.approx(3.0)


def test_supply_unknown_when_rent_samples_not_recorded():
    rents = [rent("Cholargos", None, 12, 0), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 0)]
    x = ai.rank_areas(many(25), rents, year=YEAR)[0]
    assert x.supply_per_rent is None and x.supply_rel is None


def test_area_carries_line4_and_regulatory_flags():
    g = ai.rank_areas(many(25, area="Γαλάτσι", search_area="Galatsi"), year=YEAR)[0]
    assert g.line4 == ["Άλσος Βεΐκου", "Γαλάτσι", "Ελικώνος"]
    k = ai.rank_areas(many(25, neighborhood="Αθήνα (Κουκάκι)", search_area="Koukaki"), year=YEAR)[0]
    assert k.area == "Κουκάκι" and "δεν εκδίδεται νέο ΑΜΑ" in k.reg_flags[0]


def test_decision_appreciation_names_line4_and_trend_basis():
    rows = many(60, area="Γαλάτσι", search_area="Galatsi", ppm=3000)
    x = ai.rank_areas(rows, year=YEAR)[0]
    s = [t for t in ai.decision([x], 300_000) if t.startswith("Για ανατίμηση")][0]
    assert (
        "Γαλάτσι. Εκεί φτιάχνεται η Γραμμή 4 του μετρό (Άλσος Βεΐκου, Γαλάτσι, Ελικώνος, για το 2032)"
        in s
    )
    assert "από τον Ιούλιο" in s and "60 και 60 αγγελίες" in s


def test_decision_liquidity_uses_gone_share_when_known():
    life = _weekly_life(40, gone_after=0.4)
    active = [d for d in life if d["status"] == "active"]
    x = ai.rank_areas(active, year=YEAR, lifecycle=life)[0]
    s = next(t for t in ai.decision([x], 300_000) if t.startswith("Για εύκολη μεταπώληση"))
    assert s.startswith(
        "Για εύκολη μεταπώληση: Χολαργός. Η αγορά είναι γρήγορη: το 40 % κατέβηκε μέσα σε 60 μέρες (από 40 αγγελίες)"
    )


# ---- the six checks ----------------------------------------------------------------------


def _checks(d, rows, insight):
    from scout import market_intel

    return {
        c[0].split(" (")[0]: c for c in ai.investor_checks(d, market_intel.build(rows), insight)
    }


def _subject(**kw):
    return flat(
        id=1,
        ppm=2400.0,
        price=192_000,
        gross_yield=0.056,
        est_monthly_rent=896,
        rent_estimated=True,
        **kw,
    )


def test_six_checks_have_labels_values_with_basis_and_a_known_verdict():
    from scout import market_intel

    rows = many(30, ppm=3000)
    for i, r in enumerate(rows):
        r["id"] = 100 + i
    x = ai.rank_areas(rows, year=YEAR, lifecycle=rows + _weekly_life(40, 0.5))[0]
    checks = ai.investor_checks(_subject(), market_intel.build(rows), x)
    assert [c[0].split(" (")[0] for c in checks] == [
        "Τιμή έναντι παρόμοιων",
        "Μικτή απόδοση",
        "Ρευστότητα περιοχής",
        "Ζήτηση ενοικίου",
        "Νομικά / κανονιστικά",
        "Έξοδος",
    ]
    assert all(v in (ai.GOOD, ai.MID, ai.WARN, ai.UNKNOWN) for _, _, v in checks)
    assert all(val for _, val, _ in checks)
    # the numeric checks carry their numbers
    assert all(any(ch.isdigit() for ch in checks[i][1]) for i in (0, 1, 2))


def test_price_check_good_when_below_comps_and_warns_when_too_cheap_or_dear():
    rows = many(30, ppm=3000)
    for i, r in enumerate(rows):
        r["id"] = 100 + i
    c = _checks(_subject(), rows, None)["Τιμή έναντι παρόμοιων"]
    assert (
        c[2] == ai.GOOD
        and "2.400 €/τ.μ. (−20,0 %). Τα άλλα σπίτια της γειτονιάς ζητούν συνήθως 3.000 €/τ.μ."
        in c[1]
    )
    assert "Παρόμοια (30)" in c[1]
    cheap = _checks(_subject() | {"price_per_m2": 1500.0}, rows, None)["Τιμή έναντι παρόμοιων"]
    assert cheap[2] == ai.WARN and "πολύ φθηνό" in cheap[1]
    dear = _checks(_subject() | {"price_per_m2": 3300.0}, rows, None)["Τιμή έναντι παρόμοιων"]
    assert dear[2] == ai.WARN
    fair = _checks(_subject() | {"price_per_m2": 3000.0}, rows, None)["Τιμή έναντι παρόμοιων"]
    assert fair[2] == ai.MID


def test_price_check_unknown_without_comps():
    c = ai.investor_checks(_subject(), None, None)[0]
    assert c[2] == ai.UNKNOWN and "λιγότερα από 5 παρόμοια" in c[1]


def test_yield_check_shows_rent_and_price_and_verdict_bands():
    base = _subject()
    good = ai.investor_checks(base, None, None)[1]
    assert good[2] == ai.GOOD
    assert "5,6 %" in good[1] and "12 × 896 €/μήνα" in good[1] and "192.000 €" in good[1]
    assert ai.investor_checks(base | {"gross_yield": 0.045}, None, None)[1][2] == ai.MID
    assert ai.investor_checks(base | {"gross_yield": 0.035}, None, None)[1][2] == ai.WARN
    none = ai.investor_checks(base | {"gross_yield": None}, None, None)[1]
    assert none[2] == ai.UNKNOWN


def test_liquidity_and_rent_demand_checks_follow_the_insight():
    x = ai.rank_areas(many(25), year=YEAR, lifecycle=_weekly_life(40, 0.5))[0]
    liq = ai.investor_checks(_subject(), None, x)[2]
    assert liq[2] == ai.GOOD and "γρήγορη" in liq[1] and "τουλάχιστον 35 %" in liq[1]
    x.liquidity = "αργή"
    assert ai.investor_checks(_subject(), None, x)[2][2] == ai.WARN
    assert ai.investor_checks(_subject(), None, None)[2][2] == ai.UNKNOWN
    demand = ai.investor_checks(_subject(), None, x)[3]
    assert demand[2] == ai.UNKNOWN  # no rent sample count in this fixture
    x.supply_per_rent, x.supply_rel, x.rent_samples = 2.5, 0.5, 10
    good = ai.investor_checks(_subject(), None, x)[3]
    assert good[2] == ai.GOOD and "2,5 σπίτια προς πώληση για κάθε ένα που νοικιάζεται" in good[1]
    x.supply_rel = 2.0
    assert ai.investor_checks(_subject(), None, x)[3][2] == ai.WARN
    x.supply_rel = 1.0
    assert ai.investor_checks(_subject(), None, x)[3][2] == ai.MID


def test_regulatory_check_uses_flags():
    frozen = _subject(neighborhood="Αθήνα (Κουκάκι)", search_area="Koukaki")
    c = ai.investor_checks(frozen, None, None)[4]
    assert c[2] == ai.WARN and "δεν εκδίδεται νέο ΑΜΑ" in c[1]
    watch = _subject(neighborhood="Αθήνα (Αμπελόκηποι)", search_area="Ampelokipoi")
    assert ai.investor_checks(watch, None, None)[4][2] == ai.MID
    assert ai.investor_checks(_subject(), None, None)[4][2] == ai.GOOD
    assert ai.investor_checks(_subject(neighborhood=None, search_area=None), None, None)[4][2] == (
        ai.UNKNOWN
    )


def test_exit_check_uses_trend_and_line4():
    x = ai.rank_areas(
        _cohort(4, 15, 2000, area="Γαλάτσι", search_area="Galatsi")
        + _cohort(10, 15, 2082, area="Γαλάτσι", search_area="Galatsi"),
        year=YEAR,
    )[0]
    d = _subject(neighborhood="Γαλάτσι (Άλσος Βεΐκου)")
    c = ai.investor_checks(d, None, x)[5]
    assert c[2] == ai.GOOD
    assert "+4,1 % σε 6 μήνες" in c[1] and "15 και 15 αγγελίες" in c[1]
    assert "σταθμός της Γραμμής 4 του μετρό: Άλσος Βεΐκου, για το 2032" in c[1]
    # a sub-area without a station name only gets the area-level stations
    other = _subject(neighborhood="Γαλάτσι (Λαμπρινή)")
    assert "Άλσος Βεΐκου, Γαλάτσι, Ελικώνος" in ai.investor_checks(other, None, x)[5][1]
    x.trend_pct_6m, x.trend_pct = None, None
    unk = ai.investor_checks(d, None, x)[5]
    assert unk[2] == ai.UNKNOWN and "δεν ξέρουμε ακόμα πώς κινούνται οι τιμές" in unk[1]
