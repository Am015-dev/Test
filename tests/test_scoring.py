"""Unit tests for the scoring brain — pure, no DB, no network."""

from __future__ import annotations

from scout.scoring import MarketStats, NeighborhoodStats, compute_market_stats, score

from .conftest import make_listing


def _stats(median_ppm2: float = 2800.0) -> MarketStats:
    # price_sample_count must clear the ≥3 threshold or the median is treated as too thin
    # to trust (and the undervaluation/opportunity signal is dropped as unknown).
    return MarketStats(
        by_neighborhood={
            "Ano Cholargos": NeighborhoodStats(
                median_price_per_m2=median_ppm2, price_sample_count=8
            )
        },
        overall_median_price_per_m2=median_ppm2,
    )


def test_non_dwelling_types_are_excluded(strategy):
    for title in ("Αέρας κατοικίας 220 τ.μ.", "Οικόπεδο 300 τ.μ.", "Κατάστημα 60 τ.μ."):
        result = score(make_listing(title=title), _stats(), strategy)
        assert result.excluded, f"{title!r} should be excluded"
        assert "dwelling" in result.exclusion_reason


def test_apartment_is_not_excluded_as_non_dwelling(strategy):
    result = score(make_listing(title="Διαμέρισμα 75 τ.μ."), _stats(), strategy)
    assert not result.excluded


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


def test_far_from_metro_is_not_excluded_but_scores_lower(strategy):
    """Metro distance is a SIGNAL now, not a cutoff (all-Athens coverage): a far listing
    is kept and ranked, just with a lower metro-proximity contribution."""
    near = score(make_listing(metro_distance_m=100), _stats(), strategy)
    far = score(make_listing(metro_distance_m=3000), _stats(), strategy)
    assert not near.excluded and not far.excluded
    assert near.signals["metro_proximity"] > far.signals["metro_proximity"]
    assert far.signals["metro_proximity"] == 0.0  # beyond the ceiling
    assert near.score > far.score


def test_missing_metro_distance_is_not_excluded(strategy):
    """Unknown metro distance must not exclude; it simply earns no proximity bonus."""
    result = score(make_listing(metro_distance_m=None), _stats(), strategy)
    assert not result.excluded
    assert result.signals["metro_proximity"] == 0.0


def test_passing_listing_scores_in_range(strategy):
    result = score(make_listing(), _stats(), strategy)
    assert not result.excluded
    assert 0.0 <= result.score <= 100.0


def test_higher_yield_scores_higher(strategy):
    low = score(make_listing(gross_yield=0.03), _stats(), strategy)
    high = score(make_listing(gross_yield=0.07), _stats(), strategy)
    assert high.score > low.score


def test_net_yield_preferred_over_gross(strategy):
    """When a net yield is present it drives the yield signal (against its own band), not
    the gross figure — the honest after-cost return."""
    higher_net = score(make_listing(gross_yield=0.07, net_yield=0.05), _stats(), strategy)
    lower_net = score(make_listing(gross_yield=0.07, net_yield=0.02), _stats(), strategy)
    # Same gross, different net → the one with the better NET yield scores higher.
    assert higher_net.signals["gross_yield"] > lower_net.signals["gross_yield"]
    assert higher_net.score > lower_net.score


def test_net_yield_falls_back_to_gross_when_absent(strategy):
    """No net yield → the signal uses gross (backward compatible)."""
    s = score(make_listing(gross_yield=0.08, net_yield=None), _stats(), strategy)
    assert s.signals["gross_yield"] > 0.9  # gross at the ceiling → near-full signal


def test_yield_signal_recentred_on_local_median(strategy):
    """A flat national net-yield band treats 3.5% as identical everywhere. With enough
    local (real-rent) peers, the SAME-WIDTH band recentres on the local median instead —
    so 3.5% is a top score in a low-yield prime area and the worst possible score in a
    high-yield peripheral one, mirroring relative_value.relative_yield's UI signal."""
    prime = MarketStats(
        by_neighborhood={
            "Kolonaki": NeighborhoodStats(median_net_yield=0.01, net_yield_sample_count=5)
        }
    )
    peripheral = MarketStats(
        by_neighborhood={
            "Nikaia": NeighborhoodStats(median_net_yield=0.06, net_yield_sample_count=5)
        }
    )
    in_prime = score(make_listing(neighborhood="Kolonaki", net_yield=0.035), prime, strategy)
    in_peripheral = score(
        make_listing(neighborhood="Nikaia", net_yield=0.035), peripheral, strategy
    )
    assert in_prime.signals["gross_yield"] == 1.0  # at/above the local ceiling
    assert in_peripheral.signals["gross_yield"] == 0.0  # at/below the local floor
    assert in_prime.signals["gross_yield"] > in_peripheral.signals["gross_yield"]


def test_yield_signal_falls_back_to_flat_band_without_enough_local_samples(strategy):
    """Below the neighbourhood sample floor, the flat national band still applies — a thin
    local sample must never silently reward or penalize a listing."""
    thin = MarketStats(
        by_neighborhood={
            "Ano Cholargos": NeighborhoodStats(median_net_yield=0.06, net_yield_sample_count=2)
        }
    )
    result = score(make_listing(net_yield=0.035), thin, strategy)
    # Flat band: (0.035 - net_yield_floor 0.015) / (0.055 - 0.015) span = 0.5.
    assert round(result.signals["gross_yield"], 4) == 0.5


def test_unknown_attributes_are_not_penalised_by_renormalization(strategy):
    """A listing missing energy/year must not be scored like the worst-energy/oldest flat.

    With renormalization, unknown signals drop out of the denominator, so a fully-unknown
    listing scores on ONLY what's known — never capped low just for missing scraped data."""
    known = make_listing(energy_class="A", year_built=2020, value_gap_pct=0.20)
    # Same listing but energy/year unknown and no hedonic gap (a card-only listing).
    unknown = make_listing(energy_class=None, year_built=None, value_gap_pct=None)
    s_known = score(known, _stats(), strategy)
    s_unknown = score(unknown, _stats(), strategy)
    # The unknown one isn't floored at "worst": it still scores on yield + area €/m² etc.
    assert s_unknown.score > 20
    # And a listing that is genuinely excellent on KNOWN attributes still outranks it.
    assert s_known.score > s_unknown.score


def test_imputed_rent_does_not_count_as_yield_signal(strategy):
    """When rent is the flat baseline (rent_estimated=True), yield must be excluded so it
    doesn't double-count €/m² — two listings differing only in a baseline yield tie."""
    a = score(
        make_listing(rent_estimated=True, gross_yield=0.03, net_yield=None), _stats(), strategy
    )
    b = score(
        make_listing(rent_estimated=True, gross_yield=0.07, net_yield=None), _stats(), strategy
    )
    assert a.score == b.score  # yield ignored → identical


def test_centroid_location_not_scored_as_precise_metro(strategy):
    """An approx (centroid) location must not earn the metro-proximity bonus."""
    exact = make_listing(metro_distance_m=150, location_precision="exact")
    approx = make_listing(metro_distance_m=150, location_precision="approx")
    s_exact = score(exact, _stats(), strategy)
    s_approx = score(approx, _stats(), strategy)
    assert s_exact.score > s_approx.score  # only the exact one banks the metro bonus


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


def test_quality_asset_outranks_high_yield_energy_liability(strategy):
    """The core fix: a new, efficient flat must outrank an old energy-H flat even when the
    old one has a higher yield and looks 'cheap'. Otherwise the picks look amateurish."""
    new_efficient = score(
        make_listing(year_built=2024, energy_class="A", gross_yield=0.035), _stats(), strategy
    )
    old_liability = score(
        make_listing(year_built=1978, energy_class="H", gross_yield=0.075), _stats(), strategy
    )
    assert new_efficient.score > old_liability.score


def test_energy_liability_demotes_final_score(strategy):
    """An energy-H flat's final score is scaled down vs the same flat with a good class."""
    good = score(make_listing(energy_class="B", year_built=2000), _stats(), strategy)
    liability = score(make_listing(energy_class="H", year_built=2000), _stats(), strategy)
    assert liability.score < good.score


def test_energy_liability_not_flagged_as_opportunity(strategy):
    """A cheap energy-H flat must NOT be sold as an 'opportunity' — it's a renovation
    liability, not a bargain."""
    cheap_liability = score(
        make_listing(price_per_m2=2500.0, energy_class="H"), _stats(median_ppm2=3500.0), strategy
    )
    assert not cheap_liability.is_opportunity


def test_archetype_labels():
    from scout.scoring import investment_archetype

    assert investment_archetype(2024, None, "A") == "New build"
    assert investment_archetype(1970, 2022, "B") == "Renovated"
    assert investment_archetype(2008, None, "C") == "Modern"
    assert investment_archetype(1978, None, "H") == "Energy liability"
    assert investment_archetype(1985, None, "C") == "Dated"
    assert investment_archetype(None, None, None) == "Standard"


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


def test_compute_market_stats_net_yield_median_excludes_estimated_rent():
    """An imputed baseline rent makes net_yield a deterministic inverse of €/m² — including
    those listings would make the local yield median self-referential, the same trap the
    codebase already guards against for the rent-per-m² median."""
    listings = [
        make_listing(source_id="a", net_yield=0.03, rent_estimated=False),
        make_listing(source_id="b", net_yield=0.05, rent_estimated=False),
        make_listing(source_id="c", net_yield=0.07, rent_estimated=False),
        make_listing(source_id="d", net_yield=0.99, rent_estimated=True),  # must be excluded
    ]
    stats = compute_market_stats(listings)
    assert stats.by_neighborhood["Ano Cholargos"].median_net_yield == 0.05
    assert stats.by_neighborhood["Ano Cholargos"].net_yield_sample_count == 3
    assert stats.net_yield_median_for("Ano Cholargos") == 0.05


def test_net_yield_median_for_below_sample_floor_returns_none():
    stats = MarketStats(
        by_neighborhood={"Rare": NeighborhoodStats(median_net_yield=0.05, net_yield_sample_count=2)}
    )
    assert stats.net_yield_median_for("Rare") is None
