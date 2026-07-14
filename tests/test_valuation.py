"""Unit tests for the hedonic valuation model — pure NumPy, no DB, no network."""

from __future__ import annotations

from scout.valuation import apply_valuations, fit_and_apply_by_area, fit_valuation_model

from .conftest import make_listing

# €/m² the synthetic "fair" market is priced at; every fair listing sits exactly on it.
_FAIR_PPM2 = 3000.0
# Shared attributes so the only thing that varies across fair comps is size — the model
# then learns price ≈ _FAIR_PPM2 · area and any price off that line is a real mispricing.
_ATTRS = dict(
    floor=2.0,
    year_built=2000,
    energy_class="C",
    bedrooms=2,
    metro_distance_m=400,
    search_area="Cholargos",
    neighborhood="Cholargos",
)


def _fair_listing(i: int, area: float) -> object:
    price = int(_FAIR_PPM2 * area)
    return make_listing(
        source_id=f"fair{i}", area_m2=area, price=price, price_per_m2=_FAIR_PPM2, **_ATTRS
    )


def _fair_market(n: int) -> list:
    # Spread sizes 50..89 m² so log(area) actually varies for the regression to key on.
    return [_fair_listing(i, 50.0 + (i % 40)) for i in range(n)]


def test_too_few_comps_returns_none():
    assert fit_valuation_model(_fair_market(10)) is None


def test_significance_gate_drops_within_band_gaps():
    """Anti-inflation: a gap smaller than the model's own ±band is noise, not a bargain, and
    must be dropped to None; only a gap that clears the band survives to drive the badge."""
    listings = []
    for i in range(60):
        area = 50.0 + (i % 40)
        wobble = 1.0 + (((i * 37) % 21) - 10) / 100.0  # ±10% deterministic scatter → real band
        listings.append(
            make_listing(source_id=f"s{i}", area_m2=area, price=int(3000 * area * wobble), **_ATTRS)
        )
    bargain = make_listing(  # 45% below the fair line — beyond any reasonable band
        source_id="bargain", area_m2=70.0, price=int(3000 * 70 * 0.55), **_ATTRS
    )
    near_fair = make_listing(  # 3% below fair — within the noise
        source_id="nearfair", area_m2=70.0, price=int(3000 * 70 * 0.97), **_ATTRS
    )
    fit_and_apply_by_area(listings + [bargain, near_fair])
    assert bargain.value_gap_pct is not None and bargain.value_gap_pct > 0.2
    assert near_fair.value_gap_pct is None  # within band → not badged a bargain


def test_apply_valuations_is_noop_when_model_is_none():
    lst = make_listing()
    apply_valuations([lst], None)
    assert lst.predicted_price is None
    assert lst.value_gap_pct is None


def test_flags_undervalued_and_overvalued_against_fair_market():
    listings = _fair_market(30)
    area = 70.0
    under = make_listing(
        source_id="under", area_m2=area, price=int(_FAIR_PPM2 * area * 0.6), **_ATTRS
    )
    over = make_listing(
        source_id="over", area_m2=area, price=int(_FAIR_PPM2 * area * 1.4), **_ATTRS
    )
    listings += [under, over]

    model = fit_valuation_model(listings)
    assert model is not None
    apply_valuations(listings, model)

    # A flat priced 40% below what its attributes justify reads as strongly undervalued;
    # one priced 40% above reads as overvalued. (value_gap is clamped to ±0.6.)
    assert under.value_gap_pct is not None and under.value_gap_pct > 0.2
    assert over.value_gap_pct is not None and over.value_gap_pct < -0.2
    # Predicted fair price sits near the true fair line and above/below the asking price.
    assert under.predicted_price and under.predicted_price > under.price
    assert over.predicted_price and over.predicted_price < over.price


def test_fair_priced_listing_has_near_zero_gap():
    listings = _fair_market(40)
    model = fit_valuation_model(listings)
    assert model is not None
    apply_valuations(listings, model)
    # Every comp is exactly on the fair line, so no listing is a real bargain: the gap is
    # either within the model's ±band (dropped to None by the significance gate) or tiny.
    assert all(lst.value_gap_pct is None or abs(lst.value_gap_pct) < 0.05 for lst in listings)
    assert model.r2 > 0.95  # a clean size→price relationship fits almost perfectly


def test_clean_fit_is_confident_with_tight_band():
    listings = _fair_market(40)
    model = fit_valuation_model(listings)
    assert model.is_confident  # R² well above the confidence floor
    band = model.price_band(listings[0])
    assert band is not None
    lo, hi = band
    # A clean fit → a tight band around the point estimate (near-degenerate here since
    # residual noise ≈ 0, so lo ≈ point ≈ hi to within rounding).
    point = model.predict_price(listings[0])
    assert lo <= round(point) <= hi + 1
    assert (hi - lo) / point < 0.2  # residual noise is tiny here


def test_fit_by_area_fits_each_submarket_separately():
    # Two areas priced at very different €/m²; a pooled model would blur them, per-area
    # models price each correctly and flag a within-area bargain.
    # 60 comps/area so each per-area model is genuinely CONFIDENT under 5-fold CV (train
    # folds of ~48 clear the 25-sample floor) — otherwise the confidence gate correctly
    # withholds value_gap_pct and this accuracy check would have nothing to read.
    listings = []
    for i in range(60):
        area = 50.0 + (i % 40)
        listings.append(
            make_listing(
                source_id=f"a{i}",
                area_m2=area,
                price=int(2000 * area),
                search_area="Cheap",
                neighborhood="Cheap",
                floor=2.0,
                year_built=2000,
                energy_class="B",
            )
        )
    for i in range(60):
        area = 50.0 + (i % 40)
        listings.append(
            make_listing(
                source_id=f"b{i}",
                area_m2=area,
                price=int(5000 * area),
                search_area="Pricey",
                neighborhood="Pricey",
                floor=2.0,
                year_built=2000,
                energy_class="B",
            )
        )
    models = fit_and_apply_by_area(listings)
    assert set(models) == {"Cheap", "Pricey"}
    # Both models are confident and each learned its own price level, so a listing priced
    # on-line is NOT a bargain: its gap is within the ±band (None) or small — never a false
    # large discount from pooling the two markets together.
    assert all(m.is_confident for m in models.values())
    assert all(x.value_gap_pct is None or abs(x.value_gap_pct) < 0.1 for x in listings)
    # Each model is priced near its own market, not the pooled ~3500 €/m² average.
    cheap_fair = models["Cheap"].predict_price(
        make_listing(area_m2=70.0, price=1, search_area="Cheap", floor=2.0, year_built=2000)
    )
    assert 2000 * 70 * 0.9 < cheap_fair < 2000 * 70 * 1.1


def test_noisy_fit_is_not_confident():
    # Same-size flats priced randomly-ish → no attribute explains price → weak R².
    listings = []
    for i in range(40):
        price = 150_000 + (i * 9973 % 200_000)  # deterministic scatter, no size signal
        listings.append(
            make_listing(
                source_id=f"n{i}", area_m2=75.0, price=price, price_per_m2=price / 75.0, **_ATTRS
            )
        )
    model = fit_valuation_model(listings)
    assert model is not None
    assert not model.is_confident  # honestly refuses to claim precision
    lo, hi = model.price_band(listings[0])
    assert (hi - lo) / model.predict_price(listings[0]) > 0.2  # wide band signals low trust


def test_value_gap_gated_on_real_attributes():
    """value_gap_pct (the undervalued-badge driver) must stay None when a listing's own
    energy/year were imputed — even in a confident area — so an old inefficient flat with no
    scraped attributes can't be re-badged a bargain from median imputations."""
    from scout.valuation import fit_and_apply_by_area

    # 60 comps with real attributes → a confident model.
    listings = []
    for i in range(60):
        area = 50.0 + (i % 40)
        listings.append(
            make_listing(
                source_id=f"c{i}",
                area_m2=area,
                price=int(2500 * area),
                search_area="Area",
                neighborhood="Area",
                floor=2.0,
                year_built=2000,
                energy_class="B",
            )
        )
    # One extra listing with NO energy/year (card-only) in the same area.
    cardonly = make_listing(
        source_id="card1",
        area_m2=70.0,
        price=int(2500 * 70),
        search_area="Area",
        neighborhood="Area",
        floor=2.0,
        year_built=None,
        energy_class=None,
    )
    listings.append(cardonly)
    models = fit_and_apply_by_area(listings)
    assert models["Area"].is_confident
    # The fully-attributed comps get a value gap; the card-only one does not.
    assert listings[0].value_gap_pct is not None
    assert cardonly.value_gap_pct is None
    assert cardonly.predicted_price is not None  # still shown as a rough estimate
