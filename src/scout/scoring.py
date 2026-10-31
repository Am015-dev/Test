"""Scoring engine — the brain.

Pure and fully unit-tested. It NEVER reaches into the DB: ``market_stats`` is
computed elsewhere and passed in. Driven entirely by ``strategy.yaml`` so the
investor can tune weights and thresholds without touching code.

Flow (spec §7):
1. Hard filters -> excluded listings get score 0 and a reason.
2. Each signal normalized to 0..1, multiplied by its weight, summed to 0..100.
3. Opportunity flag set when EUR/m2 < pct * neighborhood median.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from .config import Strategy
from .models import Listing, ScoredListing

# Below this many price samples a neighborhood median is statistically meaningless
# (with 1 sample it equals the listing's own €/m², so the signal is always ~0).
_MIN_NEIGHBORHOOD_SAMPLES = 3


@dataclass
class NeighborhoodStats:
    median_price_per_m2: float | None = None
    median_rent_per_m2: float | None = None
    price_sample_count: int = 0
    median_net_yield: float | None = None
    net_yield_sample_count: int = 0


@dataclass
class MarketStats:
    """Per-neighborhood and per-municipality medians, computed each run and passed in."""

    by_neighborhood: dict[str, NeighborhoodStats] = field(default_factory=dict)
    by_area: dict[str, NeighborhoodStats] = field(default_factory=dict)
    overall_median_price_per_m2: float | None = None

    def price_per_m2_median_for(
        self, neighborhood: str | None, search_area: str | None = None
    ) -> float | None:
        """The €/m² benchmark to judge a listing against: its own neighbourhood (if that
        bucket has enough samples), else its MUNICIPALITY. Deliberately does NOT fall back
        to the all-Athens median — comparing a Peristeri flat to a pooled Kolonaki-included
        average would flag entire cheap municipalities as "undervalued". Returns None when
        neither local bucket qualifies, so the undervaluation signal is treated as unknown
        rather than computed against a misleading pool."""
        if neighborhood and neighborhood in self.by_neighborhood:
            ns = self.by_neighborhood[neighborhood]
            if ns.median_price_per_m2 is not None and (
                ns.price_sample_count >= _MIN_NEIGHBORHOOD_SAMPLES
            ):
                return ns.median_price_per_m2
        if search_area and search_area in self.by_area:
            a = self.by_area[search_area]
            if (
                a.median_price_per_m2 is not None
                and a.price_sample_count >= _MIN_NEIGHBORHOOD_SAMPLES
            ):
                return a.median_price_per_m2
        return None

    def net_yield_median_for(
        self, neighborhood: str | None, search_area: str | None = None
    ) -> float | None:
        """Local (neighbourhood, else municipality) median NET yield — mirrors
        ``price_per_m2_median_for``'s two-tier fallback and honesty gate, so yield scoring
        can be judged against local peers instead of one flat national band. A flat 5.5% net
        yield reads as identical everywhere, when it's exceptional in a prime low-yield area
        and mediocre in a peripheral high-yield one. Returns None below the sample floor —
        ``_yield_signal`` then falls back to the flat national band, never disqualifying a
        listing for lack of local data."""
        if neighborhood and neighborhood in self.by_neighborhood:
            ns = self.by_neighborhood[neighborhood]
            if ns.median_net_yield is not None and (
                ns.net_yield_sample_count >= _MIN_NEIGHBORHOOD_SAMPLES
            ):
                return ns.median_net_yield
        if search_area and search_area in self.by_area:
            a = self.by_area[search_area]
            if (
                a.median_net_yield is not None
                and a.net_yield_sample_count >= _MIN_NEIGHBORHOOD_SAMPLES
            ):
                return a.median_net_yield
        return None


UNFINISHED_FACTOR = 0.25  # ημιτελές / υπό κατασκευή
OFF_PLAN_FACTOR = 0.6  # build year this year or later: often still a shell


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_market_stats(listings: Iterable[Listing]) -> MarketStats:
    """Compute per-neighborhood AND per-municipality median EUR/m2 (+ median rent EUR/m2).

    The municipality (``search_area``) tier is what the undervaluation/opportunity signals
    compare against when a neighbourhood bucket is too thin — an honest local benchmark
    instead of the all-Athens pool.
    """
    buckets: dict[str, list[float]] = {}
    area_buckets: dict[str, list[float]] = {}
    rent_buckets: dict[str, list[float]] = {}
    yield_buckets: dict[str, list[float]] = {}
    yield_area_buckets: dict[str, list[float]] = {}
    all_ppm2: list[float] = []

    for lst in listings:
        ppm2 = lst.price_per_m2
        if ppm2 is None and lst.area_m2:
            ppm2 = lst.price / lst.area_m2
        if ppm2 and ppm2 > 0:
            all_ppm2.append(ppm2)
            if lst.neighborhood:
                buckets.setdefault(lst.neighborhood, []).append(ppm2)
            if lst.search_area:
                area_buckets.setdefault(lst.search_area, []).append(ppm2)

        # Rent comps: only listings with a REAL rent (a stated listed_rent) contribute — an
        # imputed baseline rent must never seed the rent median it was derived from.
        rent = lst.listed_rent
        if rent and lst.area_m2 and lst.neighborhood:
            rent_buckets.setdefault(lst.neighborhood, []).append(rent / lst.area_m2)

        # Yield comps: same rule — a net_yield derived from the imputed baseline rent is a
        # deterministic inverse of €/m², not a genuine local data point, and would make the
        # local median self-referential. Only rent-estimated=False listings contribute.
        if not lst.rent_estimated and lst.net_yield is not None:
            if lst.neighborhood:
                yield_buckets.setdefault(lst.neighborhood, []).append(lst.net_yield)
            if lst.search_area:
                yield_area_buckets.setdefault(lst.search_area, []).append(lst.net_yield)

    by_n: dict[str, NeighborhoodStats] = {}
    for n, vals in buckets.items():
        by_n[n] = NeighborhoodStats(
            median_price_per_m2=statistics.median(vals), price_sample_count=len(vals)
        )
    for n, vals in rent_buckets.items():
        by_n.setdefault(n, NeighborhoodStats()).median_rent_per_m2 = statistics.median(vals)
    for n, vals in yield_buckets.items():
        ns = by_n.setdefault(n, NeighborhoodStats())
        ns.median_net_yield = statistics.median(vals)
        ns.net_yield_sample_count = len(vals)

    by_a: dict[str, NeighborhoodStats] = {
        a: NeighborhoodStats(
            median_price_per_m2=statistics.median(vals), price_sample_count=len(vals)
        )
        for a, vals in area_buckets.items()
    }
    for a, vals in yield_area_buckets.items():
        na = by_a.setdefault(a, NeighborhoodStats())
        na.median_net_yield = statistics.median(vals)
        na.net_yield_sample_count = len(vals)

    overall = statistics.median(all_ppm2) if all_ppm2 else None
    return MarketStats(by_neighborhood=by_n, by_area=by_a, overall_median_price_per_m2=overall)


def _excluded(listing: Listing, reason: str) -> ScoredListing:
    return ScoredListing(listing=listing, score=0.0, excluded=True, exclusion_reason=reason)


# Non-dwelling listing types for which €/m² and rental yield are undefined — they have no
# livable/rentable floor area (air rights, bare land) or aren't residential (shops, offices,
# storage, parking). These pollute the €/m² stats and the valuation comps, so they're hard-
# excluded. Houses, maisonettes and whole apartment buildings ARE dwellings and are kept.
_NON_DWELLING_TOKENS = (
    "αέρας",  # air rights — the right to build extra floors, not a property
    "οικόπεδο",  # building plot / land
    "αγροτεμάχ",  # rural land parcel
    "κατάστημα",  # shop
    "γραφεί",  # office
    "επαγγελματ",  # commercial/professional space
    "αποθήκ",  # storage
    "στάθμευσ",  # parking space
    "γκαράζ",  # garage
    "βιοτεχν",  # workshop/industrial
    "ξενοδοχ",  # hotel
)


def _non_dwelling_reason(listing: Listing) -> str | None:
    """A reason string if the listing's title marks it as a non-residential/no-floor-area
    type (so €/m² and yield are meaningless), else None."""
    title = (listing.title or "").lower()
    if not title:
        return None
    for tok in _NON_DWELLING_TOKENS:
        if tok in title:
            return "not a dwelling (no comparable €/m²)"
    return None


def _yield_signal(listing: Listing, strategy: Strategy, market: MarketStats) -> float:
    """Reward realistic rental return. Prefers NET yield (after Greek acquisition/holding
    costs and vacancy — what the investor actually keeps) scored against its own,
    lower net band; falls back to gross yield only when net couldn't be computed. Scoring
    on gross overstates returns, which is exactly the "unreliable core claim" a buyer
    would call out — net is the honest headline.

    The net-yield band is area-relative when there's a local median to judge against: the
    SAME-WIDTH band is recentred on the local (neighbourhood, else municipality) median net
    yield instead of the flat national floor/ceiling — a flat band treats 5.5% as identical
    everywhere, when it's the ceiling in a prime low-yield area and the floor in a peripheral
    high-yield one. Falls back to the flat national band when local samples are too thin
    (mirrors ``_undervaluation_signal``'s median-or-flat-fallback pattern)."""
    ref = strategy.scoring_reference
    if listing.net_yield is not None:
        span = max(ref.net_yield_ceiling - ref.net_yield_floor, 1e-9)
        local_median = market.net_yield_median_for(listing.neighborhood, listing.search_area)
        floor = local_median - span / 2 if local_median is not None else ref.net_yield_floor
        return _clamp01((listing.net_yield - floor) / span)
    if not listing.gross_yield:
        return 0.0
    span = max(ref.yield_ceiling - ref.yield_floor, 1e-9)
    return _clamp01((listing.gross_yield - ref.yield_floor) / span)


def _price_vs_median_signal(listing: Listing, median_ppm2: float | None) -> float:
    """1.0 when much cheaper than the neighborhood median, 0 when at/above it."""
    ppm2 = listing.price_per_m2
    if ppm2 is None and listing.area_m2:
        ppm2 = listing.price / listing.area_m2
    if not ppm2 or not median_ppm2:
        return 0.0
    # ratio < 1 means cheaper; map [0.7 .. 1.0] -> [1 .. 0].
    ratio = ppm2 / median_ppm2
    return _clamp01((1.0 - ratio) / 0.3)


def _undervaluation_signal(
    listing: Listing, median_ppm2: float | None, strategy: Strategy
) -> tuple[float, bool]:
    """How far below fair value the asking price sits, as ``(value 0..1, is_known)``.

    Prefers the hedonic model's ``value_gap_pct`` — which controls for the property's own
    size/floor/age/energy/metro (and is only populated when the model priced this listing
    from REAL, non-imputed attributes), so it separates *mispriced* from merely *cheap
    because inferior*. Falls back to the raw €/m²-vs-local-median signal when the model
    couldn't price it. ``is_known`` is False only when neither a hedonic gap nor a local
    median exists — in which case the signal is dropped from the (renormalized) score
    rather than computed against a misleading benchmark."""
    gap = listing.value_gap_pct
    if gap is not None:
        target = max(strategy.scoring_reference.target_undervaluation, 1e-9)
        return _clamp01(gap / target), True
    if median_ppm2:
        return _price_vs_median_signal(listing, median_ppm2), True
    return 0.0, False


def _metro_proximity_signal(listing: Listing, strategy: Strategy) -> float:
    """Walk-to-metro bonus, 0..1: at the station → 1.0, at/beyond the ceiling → 0 (linear).

    Unknown distance → 0 (neutral, no bonus) rather than a penalty — a listing we couldn't
    locate simply doesn't earn the proximity points; it isn't punished for missing data.
    Replaces the old hard metro cutoff now that coverage spans all of Athens."""
    metro = listing.metro_distance_m
    if metro is None:
        return 0.0
    ceiling = max(strategy.scoring_reference.metro_distance_ceiling_m, 1)
    return _clamp01(1.0 - metro / ceiling)


def _price_drop_signal(listing: Listing, first_price: int | None, strategy: Strategy) -> float:
    if not first_price or first_price <= 0 or listing.price >= first_price:
        return 0.0
    drop_pct = (first_price - listing.price) / first_price
    return _clamp01(drop_pct / max(strategy.scoring_reference.max_price_drop_pct, 1e-9))


def newness_score(year_built: int | None, renovated_year: int | None, ref) -> float:
    """Newness 0..1 from the later of build / renovation year. Unknown -> 0. Public so
    the UI can show the same value it scores on without re-deriving the logic."""
    years = [y for y in (year_built, renovated_year) if y]
    if not years:
        return 0.0
    span = max(ref.build_year_ceiling - ref.build_year_floor, 1e-9)
    return _clamp01((max(years) - ref.build_year_floor) / span)


def _newness_signal(listing: Listing, strategy: Strategy) -> float:
    """Newer stock scores higher. Uses the later of build year / renovation year, so a
    fully renovated older flat counts as effectively new. Unknown year -> 0 (no bonus).
    """
    return newness_score(listing.year_built, listing.renovated_year, strategy.scoring_reference)


# Greek (and Latin) energy-performance certificate classes -> 0..1. A+/A rent higher and
# are future-proof against tightening EU efficiency rules; Ε/Ζ/Η are a holding liability.
_ENERGY_SCORE = {
    "A+": 1.0,
    "Α+": 1.0,
    "A": 0.92,
    "Α": 0.92,
    "B+": 0.84,
    "Β+": 0.84,
    "B": 0.78,
    "Β": 0.78,
    "C": 0.6,
    "Γ": 0.6,
    "D": 0.42,
    "Δ": 0.42,
    "E": 0.26,
    "Ε": 0.26,
    "F": 0.12,
    "Ζ": 0.12,
    "G": 0.0,
    "Η": 0.0,  # Greek eta — the worst class in Greece's A+..Η scale
    "H": 0.0,  # Latin alias for Η, in case a source transliterates it
}


def energy_class_score(energy_class: str | None) -> float:
    """Energy class -> 0..1. Unknown / exempt / pending -> 0. Public so the UI can show
    the same value it scores on."""
    return _ENERGY_SCORE.get((energy_class or "").strip().upper(), 0.0)


def _energy_signal(listing: Listing) -> float:
    """Map the energy class to 0..1. Unknown / exempt / pending -> 0 (no bonus)."""
    return energy_class_score(listing.energy_class)


def energy_liability_multiplier(energy_class: str | None, ref) -> float:
    """A 0.x..1.0 multiplier that DEMOTES energy-inefficient stock in the final score.

    Energy class E/F/G (Greek Ε/Ζ/Η) is not merely "lower quality" — under the EU EPBD
    the worst-performing buildings face mandatory renovation and tightening rental
    restrictions this decade, so a cheap energy-H flat carries a real capital-expense and
    legal liability that a naive score would ignore. This scales the whole score down for
    poor classes (worst class → ``energy_liability_floor``, best → 1.0), so an efficient
    flat can't be beaten to the top by a high-yield liability.

    Unknown/exempt energy → 1.0 (no penalty): never punish a listing for missing data.
    """
    ec = (energy_class or "").strip().upper()
    if ec not in _ENERGY_SCORE:
        return 1.0
    floor = ref.energy_liability_floor
    return floor + (1.0 - floor) * _ENERGY_SCORE[ec]


def investment_archetype(
    year_built: int | None,
    renovated_year: int | None,
    energy_class: str | None,
    new_build_year: int = 2015,
) -> str:
    """A plain-language asset class so old/inefficient stock is characterised honestly
    instead of being sold as a turnkey 'opportunity'. Takes primitives so the UI can call
    it per row without building a Listing.

    - New build        : built in the last ~decade
    - Renovated        : recently renovated (effectively modern)
    - Modern           : 2000s stock
    - Energy liability : E/F/G class — EU renovation mandate / high capex risk
    - Dated            : older stock without a redeeming energy class
    - Standard         : everything else / unknown
    """
    yr = renovated_year or year_built
    energy = _ENERGY_SCORE.get((energy_class or "").strip().upper())
    if renovated_year and renovated_year >= new_build_year - 5:
        return "Renovated"
    if yr and yr >= new_build_year:
        return "New build"
    if yr and yr >= 2005:
        return "Modern"
    if energy is not None and energy <= 0.12:  # E/F/G (Ε/Ζ/Η)
        return "Energy liability"
    if yr and yr < 1990:
        return "Dated"
    return "Standard"


def score(
    listing: Listing,
    market_stats: MarketStats,
    strategy: Strategy,
    first_price: int | None = None,
) -> ScoredListing:
    """Score a single listing. ``first_price`` enables the price-drop signal."""
    # 1. Hard filters.
    # Non-dwelling types (air rights, land, shops, parking…) have no comparable €/m² or
    # rentable value — exclude before anything else so they never reach stats/comps.
    nd = _non_dwelling_reason(listing)
    if nd is not None:
        return _excluded(listing, nd)
    # Only exclude when the floor is KNOWN to be too low. An unknown floor (the portal
    # didn't report one) must not be treated as a basement and silently dropped — same
    # reasoning as the unknown-metro-distance case below; otherwise a portal that never
    # reports floor has every one of its listings wrongly excluded.
    if listing.floor is not None and listing.floor < strategy.hard_filters.min_floor:
        return _excluded(listing, "ground/low floor")
    # Metro distance is NO LONGER a hard cutoff: coverage now spans all of Athens and metro
    # proximity is a weighted SIGNAL (below) plus an optional UI filter, so a great flat
    # that happens to be far from Line 2/3 is ranked lower, not thrown away.

    # 2. Weighted, normalized signals — RENORMALIZED over the signals we can actually
    # evaluate for this listing. An unknown attribute (no scraped energy/year, an imputed
    # rent, a centroid-only location) is EXCLUDED from both the numerator and the weight
    # denominator, rather than scored 0 — otherwise a listing would be punished for missing
    # data (scored like the worst energy / oldest build), which with ~90% card-only
    # inventory would bury every un-enriched listing regardless of its merits.
    median_ppm2 = market_stats.price_per_m2_median_for(listing.neighborhood, listing.search_area)
    uv_value, uv_known = _undervaluation_signal(listing, median_ppm2, strategy)

    # Yield counts as a REAL signal only when rent is a genuine comp (not the flat baseline);
    # otherwise gross_yield is a deterministic inverse of €/m² and would double-count the
    # undervaluation signal.
    yield_known = not listing.rent_estimated and (
        listing.net_yield is not None or bool(listing.gross_yield)
    )
    year_known = bool(listing.year_built or listing.renovated_year)
    energy_known = bool((listing.energy_class or "").strip())
    # A centroid-only location gives one identical distance for a whole municipality, so it
    # must not be scored as a precise per-listing signal.
    metro_known = listing.metro_distance_m is not None and listing.location_precision == "exact"

    w = strategy.weights
    # (value, weight, is_known) per signal. price_drop / rented / private are always
    # evaluable (absence = 0), so they stay in the denominator.
    contributions = {
        "undervaluation": (uv_value, w.undervaluation, uv_known),
        "gross_yield": (_yield_signal(listing, strategy, market_stats), w.gross_yield, yield_known),
        "newness": (_newness_signal(listing, strategy), w.newness, year_known),
        "energy_class": (_energy_signal(listing), w.energy_class, energy_known),
        "metro_proximity": (
            _metro_proximity_signal(listing, strategy),
            w.metro_proximity,
            metro_known,
        ),
        "price_drop": (_price_drop_signal(listing, first_price, strategy), w.price_drop, True),
        "is_currently_rented": (
            1.0 if listing.is_currently_rented else 0.0,
            w.is_currently_rented,
            True,
        ),
        "is_private_seller": (1.0 if listing.is_private_seller else 0.0, w.is_private_seller, True),
    }
    signals = {k: v for k, (v, _, _) in contributions.items()}
    signal_known = {k: known for k, (_, _, known) in contributions.items()}
    total_weight = sum(wt for (_, wt, known) in contributions.values() if known)
    if total_weight <= 0:
        final = 0.0
    else:
        raw = sum(v * wt for (v, wt, known) in contributions.values() if known)
        final = raw / total_weight * 100.0

    # 2b. Energy-liability demotion: scale the whole score down for inefficient stock so a
    # cheap, high-yield energy-H flat (an EU-EPBD renovation liability) can't outrank an
    # efficient, well-built one. See energy_liability_multiplier.
    ref = strategy.scoring_reference
    final *= energy_liability_multiplier(listing.energy_class, ref)

    # 2c. Unfinished / under-construction stock needs more money and months of work before it
    # can be lived in or rented: cut it hard. A build year of this year or later usually means
    # an off-plan sale (still a shell), so it is cut too, less.
    off_plan = bool(listing.year_built and listing.year_built >= date.today().year)
    if listing.is_unfinished:
        final *= UNFINISHED_FACTOR
    elif off_plan:
        final *= OFF_PLAN_FACTOR

    # 3. Opportunity flag. A genuine opportunity must clear the €/m² bar AND not be an
    # energy liability — flagging a renovation-mandated energy-H flat as an "opportunity"
    # is exactly the mistake that made the results look amateurish.
    is_opp = False
    ppm2 = listing.price_per_m2 or (listing.price / listing.area_m2 if listing.area_m2 else None)
    if ppm2 and median_ppm2:
        threshold = strategy.opportunity_flag.price_per_m2_below_median_pct * median_ppm2
        energy = energy_class_score(listing.energy_class)
        energy_in_scale = (listing.energy_class or "").strip().upper() in _ENERGY_SCORE
        is_opp = ppm2 < threshold and (not energy_in_scale or energy > 0.12)
        is_opp = is_opp and not (listing.is_unfinished or off_plan)

    return ScoredListing(
        listing=listing,
        score=round(final, 2),
        excluded=False,
        is_opportunity=is_opp,
        signals=signals,
        signal_known=signal_known,
    )
