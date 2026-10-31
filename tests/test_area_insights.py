from __future__ import annotations

from datetime import datetime

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
    assert any("Τάση τιμών μη διαθέσιμη" in r for r in x.risks)


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
    assert any("ενοικίων" in r for r in no_rent.risks)

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
    assert any("Μικτή απόδοση 5,8%" in r and "40 δείγματα" in r for r in x.reasons)
    assert any("Μικρό δείγμα: μόνο 40" in r for r in x.risks)
    assert all(any(ch.isdigit() for ch in r) for r in x.reasons)


def test_falling_prices_and_old_stock_are_risks():
    early = many(15, ppm=3000, is_fresh=False, year_built=1970)
    late = many(60, ppm=2700, first_seen=OCT, year_built=1970)
    (x,) = ai.rank_areas(early + late, year=YEAR)
    assert x.trend_pct == pytest.approx(-0.10)
    assert x.risks[0].startswith("Πτωτικές ζητούμενες τιμές: -10,0%")
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
    assert any("δείγματα: —" in r for r in x.reasons)
