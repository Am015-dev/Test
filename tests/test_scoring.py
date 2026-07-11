"""Unit tests for the scoring brain — pure, no DB, no network."""

from __future__ import annotations

from scout.scoring import MarketStats, NeighborhoodStats, compute_market_stats, score

from .conftest import make_listing


def _stats(median_ppm2: float = 2800.0) -> MarketStats:
    return MarketStats(
        by_neighborhood={"Ano Cholargos": NeighborhoodStats(median_price_per_m2=median_ppm2)},
        overall_median_price_per_m2=median_ppm2,
    )


def test_ground_floor_is_excluded(strategy):
    lst = make_listing(floor=0.0)
    result = score(lst, _stats(), strategy)
    assert result.excluded
    assert result.exclusion_reason == "ground/low floor"
    assert result.score == 0.0


def test_semi_basement_is_excluded(strategy):
    result = score(make_listing(floor=-1.0), _stats(), strategy)
    assert result.excluded


def test_mezzanine_is_excluded(strategy):
    # mezzanine = 0.5, below min_floor of 1
    result = score(make_listing(floor=0.5), _stats(), strategy)
    assert result.excluded


def test_missing_floor_is_not_excluded(strategy):
    """Unknown floor must not hard-exclude — a portal that never reports floor would
    otherwise have every listing wrongly dropped as 'ground/low floor'. Mirrors the
    unknown-metro-distance handling; only a KNOWN low floor excludes."""
    result = score(make_listing(floor=None), _stats(), strategy)
    assert not result.excluded


def test_too_far_from_metro_is_excluded(strategy):
    result = score(make_listing(metro_distance_m=900), _stats(), strategy)
    assert result.excluded
    assert result.exclusion_reason == "too far from metro"


def test_missing_metro_distance_is_not_excluded(strategy):
    """Unknown metro distance must not hard-exclude (would blank the dashboard on a
    geocoding outage). It's kept and scored; the UI flags the distance as unknown."""
    result = score(make_listing(metro_distance_m=None), _stats(), strategy)
    assert not result.excluded


def test_passing_listing_scores_in_range(strategy):
    result = score(make_listing(), _stats(), strategy)
    assert not result.excluded
    assert 0.0 <= result.score <= 100.0


def test_higher_yield_scores_higher(strategy):
    low = score(make_listing(gross_yield=0.03), _stats(), strategy)
    high = score(make_listing(gross_yield=0.07), _stats(), strategy)
    assert high.score > low.score


def test_price_drop_increases_score(strategy):
    no_drop = score(make_listing(price=200_000), _stats(), strategy, first_price=200_000)
    dropped = score(make_listing(price=180_000), _stats(), strategy, first_price=200_000)
    assert dropped.signals["price_drop"] > 0
    assert dropped.score > no_drop.score


def test_newness_signal_favours_new_builds(strategy):
    old = score(make_listing(year_built=1975), _stats(), strategy)
    new = score(make_listing(year_built=2020), _stats(), strategy)
    assert new.signals["newness"] > old.signals["newness"]
    assert new.score > old.score


def test_renovation_counts_as_newness(strategy):
    # A 1970 flat renovated in 2022 should score as effectively new.
    r = score(make_listing(year_built=1970, renovated_year=2022), _stats(), strategy)
    assert r.signals["newness"] > 0.5


def test_energy_class_signal_greek_and_latin(strategy):
    good = score(make_listing(energy_class="A"), _stats(), strategy)
    poor = score(make_listing(energy_class="Ε"), _stats(), strategy)  # Greek Epsilon
    assert good.signals["energy_class"] > poor.signals["energy_class"]
    assert good.score > poor.score
    # Unknown / exempt energy class contributes nothing rather than crashing.
    assert (
        score(make_listing(energy_class="Εξαιρείται"), _stats(), strategy).signals["energy_class"]
        == 0.0
    )


def test_rented_and_private_add_signal(strategy):
    plain = score(
        make_listing(is_currently_rented=False, is_private_seller=False), _stats(), strategy
    )
    flagged = score(
        make_listing(is_currently_rented=True, is_private_seller=True), _stats(), strategy
    )
    assert flagged.score > plain.score
    assert flagged.signals["is_currently_rented"] == 1.0
    assert flagged.signals["is_private_seller"] == 1.0


def test_undervaluation_signal_from_value_gap(strategy):
    """When the hedonic model priced a listing, the undervaluation signal tracks its gap:
    a listing at the target discount (20% below fair value) earns the full signal."""
    fair = score(make_listing(value_gap_pct=0.0), _stats(), strategy)
    under = score(make_listing(value_gap_pct=0.20), _stats(), strategy)
    over = score(make_listing(value_gap_pct=-0.20), _stats(), strategy)
    assert under.signals["undervaluation"] == 1.0
    assert fair.signals["undervaluation"] == 0.0
    assert over.signals["undervaluation"] == 0.0
    assert under.score > fair.score >= over.score


def test_undervaluation_falls_back_to_price_vs_median(strategy):
    """With no hedonic gap (model couldn't price it), the signal falls back to raw €/m²
    vs the neighborhood median, so cheaper-per-m² still scores higher."""
    cheap = score(
        make_listing(value_gap_pct=None, price_per_m2=2100.0), _stats(median_ppm2=3000.0), strategy
    )
    dear = score(
        make_listing(value_gap_pct=None, price_per_m2=3000.0), _stats(median_ppm2=3000.0), strategy
    )
    assert cheap.signals["undervaluation"] > dear.signals["undervaluation"]


def test_opportunity_flag_set_when_cheap(strategy):
    # ppm2 = 2500 vs median 3500 -> 2500 < 0.85*3500=2975 -> opportunity
    result = score(make_listing(price_per_m2=2500.0), _stats(median_ppm2=3500.0), strategy)
    assert result.is_opportunity


def test_opportunity_flag_not_set_when_pricey(strategy):
    result = score(make_listing(price_per_m2=3400.0), _stats(median_ppm2=3500.0), strategy)
    assert not result.is_opportunity


def test_compute_market_stats_medians():
    listings = [
        make_listing(source_id="a", price=200_000, area_m2=100, price_per_m2=2000),
        make_listing(source_id="b", price=300_000, area_m2=100, price_per_m2=3000),
        make_listing(source_id="c", price=400_000, area_m2=100, price_per_m2=4000),
    ]
    stats = compute_market_stats(listings)
    assert stats.by_neighborhood["Ano Cholargos"].median_price_per_m2 == 3000
    assert stats.overall_median_price_per_m2 == 3000
