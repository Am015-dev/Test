"""Unit tests for the hedonic valuation model — pure NumPy, no DB, no network."""

from __future__ import annotations

from scout.valuation import apply_valuations, fit_valuation_model

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
    # Every comp is exactly on the fair line, so gaps cluster tightly around zero.
    assert all(abs(lst.value_gap_pct) < 0.05 for lst in listings)
    assert model.r2 > 0.95  # a clean size→price relationship fits almost perfectly
