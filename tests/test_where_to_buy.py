"""Pure helpers of the «Πού να αγοράσω» page (ui/areas.py)."""

from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("streamlit")

from scout import area_insights as ai  # noqa: E402
from scout.ui import areas  # noqa: E402

from .test_area_insights import YEAR, flat, many, rent  # noqa: E402


def _insight(**kw) -> ai.AreaInsight:
    base = dict(
        area="Χαλάνδρι",
        n_fresh=120,
        median_ppm=3057.0,
        median_ppm_recent=3400.0,
        n_recent=60,
        trend_early_ppm=3000.0,
        trend_early_n=40,
        trend_late_ppm=3030.0,
        trend_late_n=120,
        trend_pct=0.01,
        cut_share=0.05,
        median_cut_pct=0.08,
        median_dom=40.0,
        rent_ppm=13.08,
        rent_samples=30,
        gross_yield=0.0513,
        value_band=None,
        value_band_discount=None,
        good_stock=12,
        old_share=0.5,
        unknown_age_share=0.1,
        score=53.9,
    )
    base.update(kw)
    return ai.AreaInsight(**base)


@pytest.mark.parametrize(
    "name",
    ["Χολαργός", "Νέα Φιλαδέλφεια Αττικής", "Νέο Ψυχικό", "Αμπελόκηποι", "Ηράκλειο", "Μαρούσι"],
)
def test_ne_areas_match_by_municipality_name(name):
    assert areas.is_ne(name)


@pytest.mark.parametrize("name", ["Αχαρνές", "Γέρακας", "Νέα Ιωνία", "Κυψέλη", "Μελίσσια"])
def test_spillover_areas_are_not_ne(name):
    assert not areas.is_ne(name)


def test_confidence_levels():
    assert areas.confidence(_insight(n_fresh=150, rent_samples=40)) == areas.CONF_HIGH
    # unrecorded rent samples can never be high
    assert areas.confidence(_insight(n_fresh=500, rent_samples=None)) == areas.CONF_MID
    assert areas.confidence(_insight(n_fresh=80, rent_samples=40)) == areas.CONF_MID
    assert areas.confidence(_insight(n_fresh=40, rent_samples=40)) == areas.CONF_LOW
    assert areas.confidence(_insight(rent_samples=3)) == areas.CONF_LOW
    assert areas.confidence(_insight(gross_yield=None, rent_ppm=None)) == areas.CONF_LOW


def test_greek_number_formats():
    assert areas.gr_ppm(2922.4) == "2.922 €/τ.μ."
    assert areas.gr_pct(0.0543) == "5,4 %"
    assert areas.gr_pct(0.054, sign=True) == "+5,4 %"
    assert areas.gr_pct(-0.017, sign=True) == "-1,7 %"
    assert areas.gr_rent(13.08) == "13,1 €/τ.μ."
    assert areas.gr_num(12345.67, 1) == "12.345,7"
    assert areas.gr_ppm(None) == areas.gr_pct(float("nan")) == "—"


def test_trend_and_samples_text_show_n_and_dash():
    assert areas.trend_text(_insight()) == "+1,0 % (40 και 120 αγγελίες)"
    assert areas.trend_text(_insight(trend_pct=None, trend_early_n=4)) == "— (4 και 120 αγγελίες)"
    assert areas.samples_text(_insight(rent_samples=None)) == "—"


def test_table_frame_is_numeric_and_sortable():
    df = areas.table_frame([_insight(), _insight(area="Γαλάτσι", rent_samples=None)])
    assert df["Μικτή απόδοση"].iloc[0] == pytest.approx(5.13)
    assert df["€/τ.μ. (όλα)"].dtype.kind == "f"
    assert df["Δείγματα ενοικίου"].isna().iloc[1]
    assert areas._TABLE_FORMAT["Δείγματα ενοικίου"](df["Δείγματα ενοικίου"].iloc[1]) == "—"


def test_coverage_line():
    rows = [flat(last_seen=datetime(2026, 10, 30, 23))]
    line = areas.coverage_line([_insight()] * 23, rows)
    assert (
        line
        == "Ζητούμενες τιμές XE.gr έως 30/10 · 23 περιοχές με τουλάχιστον 20 πρόσφατες αγγελίες"
    )


def test_area_points_prefer_exact_then_own_centroid():
    exact = many(3, lat=38.03, lng=23.80, location_precision="exact")
    approx = many(5, lat=37.0, lng=23.0, location_precision="approx")
    gal = many(4, area="Γαλάτσι", lat=38.0003, lng=23.795, location_precision="approx")
    pts = areas.area_points(exact + approx + gal, {"Χολαργός", "Γαλάτσι"})
    assert pts["Χολαργός"] == (38.03, 23.80, False)
    assert pts["Γαλάτσι"] == (38.0180, 23.7480, True)  # enrich.MUNICIPALITY_CENTROIDS


def test_ranking_feeds_the_page_helpers():
    rows = many(60, ppm=2500) + many(30, area="Αχαρνές", search_area="Cholargos", ppm=2000)
    rents = [rent("Cholargos", None, 12.0, 40), rent("Cholargos", "Χολαργός (Κέντρο)", 12, 40)]
    ranked = ai.rank_areas(rows, rents, areas=ai.NE_ATHENS_AREAS, year=YEAR)
    assert {x.area for x in ranked} == {"Χολαργός", "Αχαρνές"}
    assert [x.area for x in ranked if areas.is_ne(x.area)] == ["Χολαργός"]


def test_card_texts_show_n_over_m_and_unchecked():
    assert areas.uc_text(_insight(uc_unfinished=33, uc_checked=51)) == "33/51 με ελεγμένη περιγραφή"
    assert "δεν έχει ελεγχθεί" in areas.uc_text(_insight())
    assert areas.confidence_text(_insight(n_fresh=150, rent_samples=40)) == ("Υψηλή (150 αγγελίες)")
    assert areas.confidence_text(_insight(rent_samples=None)) == "Μέτρια (δείγμα ενοικίου άγνωστο)"


def test_new_vs_old_text():
    x = _insight(n_new=51, ppm_new=4000.0, n_old=275, ppm_old=2500.0, new_premium=0.6)
    assert (
        areas.new_old_text(x)
        == "4.000 €/τ.μ. (51 αγγελίες) έναντι 2.500 €/τ.μ. (275 αγγελίες), +60 %"
    )
    assert "3 και 275 αγγελίες" in areas.new_old_text(_insight(n_new=3, n_old=275))


def test_phone_table_has_at_most_four_columns():
    assert len(areas.PHONE_COLUMNS) <= 4
    assert set(areas.PHONE_COLUMNS) <= set(areas.table_frame([_insight()]).columns)


def test_percent_has_a_space_in_greek_style():
    assert areas.gr_pct(0.049) == "4,9 %"


def test_yield_text_shows_old_and_new():
    assert areas.yield_text(_insight(gross_yield=0.055)) == "5,5 %"
    x = _insight(gross_yield=0.055, gross_yield_new=0.036)
    assert areas.yield_text(x) == "5,5 % στα παλιά · 3,6 % στα νεόδμητα"


# ---- round 3: insight lines on the card ---------------------------------------------------


def test_trend_line_prefers_six_months_then_july_and_says_when_missing():
    six = _insight(trend_pct_6m=0.041, trend_6m_n=(15, 22))
    assert areas.trend_line(six).startswith("+4,1 % σε 6 μήνες")
    assert "15 και 22 αγγελίες" in areas.trend_line(six)
    assert areas.trend_line(_insight()).startswith("+1,0 % από τον Ιούλιο")
    none = areas.trend_line(_insight(trend_pct=None, trend_early_n=4))
    assert none.startswith("δεν υπάρχει αρκετό ιστορικό") and "4 και 120 αγγελίες" in none


def test_supply_line_shows_both_counts_or_says_unknown():
    x = _insight(n_fresh=120, rent_samples=30, supply_per_rent=4.0)
    assert areas.supply_line(x) == "4,0 (120 πώλησης / 30 ενοικίασης)"
    assert areas.supply_line(_insight()).startswith("άγνωστη")


def test_render_checks_prints_label_verdict_and_value(monkeypatch):
    seen = []
    monkeypatch.setattr(areas.st, "markdown", lambda s, **kw: seen.append(s))
    areas.render_checks(
        [("Απόδοση", "Μικτή 5,6 %", "καλό"), ("Ζήτηση ενοικίου", "δεν έχουμε", "άγνωστο")]
    )
    assert seen[0] == "**Απόδοση:** :green[**καλό**]  \nΜικτή 5,6 %"
    assert ":gray[**άγνωστο**]" in seen[1]


def test_page_pipeline_attaches_all_insight_fields():
    rows = many(60, area="Γαλάτσι", search_area="Galatsi", ppm=2500)
    x = ai.rank_areas(rows, year=YEAR, areas=ai.NE_ATHENS_AREAS)[0]
    assert x.line4 and x.trend_series and x.liquidity is None
    assert areas.is_ne(x.area)


def test_sparkline_and_series_text():
    assert areas.sparkline([1.0, 2.0, 3.0]) == "▁▅█"
    assert areas.sparkline([5.0, 5.0]) == "▄▄"
    x = _insight(trend_series=[("2026-07", 2589.0, 178), ("2026-10", 2778.0, 123)])
    assert areas.series_text(x) == "Ιουλ 2.589 (178 αγγελίες) · Οκτ 2.778 (123 αγγελίες)"
