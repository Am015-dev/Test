"""Streamlit app — reads the DB the pipeline populated and surfaces opportunities.

Pages: Opportunities (home), Today, Map, Listing detail, Watchlist, Strategy, Debug.
The app NEVER scrapes in the request cycle; scraping is the scheduled pipeline's
job. A "Refresh now" button runs the pipeline explicitly in the foreground.

Design goals: answer "what should I look at today?" at a glance (KPI header + top
picks + a ranked, readable table), and NEVER render a blank screen when there is
real data — if nothing passes the hard filters, show everything with the reason.

Run:  streamlit run src/scout/ui/app.py
"""

from __future__ import annotations

import statistics
import sys
from datetime import datetime
from pathlib import Path

# Allow running via `streamlit run src/scout/ui/app.py` without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from scout import analytics, comps, finance  # noqa: E402
from scout.config import Strategy, load_strategy, save_strategy  # noqa: E402
from scout.regions import REGIONS  # noqa: E402
from scout.scoring import (
    energy_class_score,
    energy_liability_multiplier,
    newness_score,
)  # noqa: E402
from scout.ui import (
    components,  # noqa: E402
    queries,  # noqa: E402
)
from scout.ui import format as fmt  # noqa: E402
from scout.ui.theme import inject_css  # noqa: E402

st.set_page_config(page_title="Holargos Property Scout", page_icon="🏠", layout="wide")
inject_css()


@st.cache_data(ttl=60)
def get_listings() -> list[dict]:
    return queries.load_listings(include_excluded=True, only_active=True)


@st.cache_data(ttl=300)
def get_strategy() -> Strategy:
    return load_strategy()


@st.cache_data(ttl=60)
def get_all_listings_debug() -> list[dict]:
    """Everything, including excluded and inactive (gone) listings — for the Debug page."""
    return queries.load_listings(include_excluded=True, only_active=False)


@st.cache_data(ttl=60)
def get_history(listing_id: int):
    return queries.load_price_history(listing_id)


@st.cache_data(ttl=300)
def get_all_price_history() -> list[dict]:
    return queries.load_all_price_history()


@st.cache_data(ttl=120)
def get_recent_health() -> list[dict]:
    return queries.load_recent_health(10)


@st.cache_data(ttl=120)
def get_valuation_summary() -> dict:
    return queries.load_valuation_summary()


def _valuation_banner() -> dict:
    """Show — honestly — how much to trust the fair-value numbers, and return the summary
    so callers can render ± bands. Never implies more precision than the fit supports."""
    v = get_valuation_summary()
    if not v.get("fitted"):
        st.info(
            "**Fair-value model:** not enough comparable listings yet to price properties "
            "against their attributes — showing raw €/m² signals only."
        )
        return v
    o = v["overall"]
    r2, n, n_areas = o["r2"], o["n"], o.get("n_areas", 1)
    band = f"±{(pow(2.718281828, o['residual_std']) - 1) * 100:.0f}%"
    scope = f"{n_areas} area-specific models over {n} comparables"
    basis = (
        "Values are **relative to ASKING prices** in each submarket (Greek sold prices "
        "aren't public), so read them as *priced-vs-comparable-listings*, not vs. what "
        "flats actually sell for."
    )
    if o["is_confident"]:
        st.success(
            f"**Relative-value model:** {scope}, out-of-sample R²={r2:.2f}. Each estimate is "
            f"shown with its area's ± range (typ. {band}). {basis}"
        )
    else:
        st.warning(
            f"**Relative-value model:** {scope}, out-of-sample R²={r2:.2f} — some submarkets "
            f"don't predict held-out listings reliably, so their figures are *indicative* "
            f"(typ. range {band}). Rank to shortlist, then verify each listing. {basis}"
        )
    return v


def _last_updated(listings: list[dict]) -> datetime | None:
    """Most recent time any listing was seen by the pipeline."""
    seens = [d["last_seen"] for d in listings if d["last_seen"]]
    return max(seens) if seens else None


def _eligible(listings: list[dict]) -> list[dict]:
    """Listings that pass the hard filters (not excluded)."""
    return [d for d in listings if not d["excluded"]]


# ---- shared rendering helpers ---------------------------------------------


def _metro_label(d: dict) -> str:
    m = d["metro_distance_m"]
    return f"{m} m" if m is not None else "unknown"


def _floor_label(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}"


def _table(rows: list[dict], show_reason: bool = False) -> None:
    """Render listings as a sortable, readable table (sorted by score, desc)."""
    records = []
    for d in rows:
        rec = {
            "Score": round(d["score"], 0),
            "Asset": d.get("archetype", ""),
            "Price": d["price"],
            # Only show a "Fair value" figure the model could actually stand behind (its
            # value_gap survived the confidence + real-attributes gate); blank otherwise so
            # an imputed prediction isn't read as a precise valuation.
            "Fair value": (
                d.get("predicted_price") if d.get("value_gap_pct") is not None else None
            ),
            "Value gap": (
                (d.get("value_gap_pct") * 100) if d.get("value_gap_pct") is not None else None
            ),
            "€/m²": d["price_per_m2"],
            "Area": d["area_m2"],
            "Floor": d["floor"],
            "Built": d.get("renovated_year") or d.get("year_built"),
            "Energy": d.get("energy_class") or "",
            "Yield": (d["gross_yield"] * 100) if d["gross_yield"] is not None else None,
            "Metro": d["metro_distance_m"],
            "Neighborhood": d["neighborhood"] or "—",
            "Flags": " ".join(fmt.badges(d)) or "",
            "Link": d["url"],
        }
        if show_reason:
            rec["Filtered out"] = d["exclusion_reason"] or ""
        records.append(rec)
    df = pd.DataFrame(records)
    column_config = {
        "Score": st.column_config.ProgressColumn(
            "Score", help="0–100 fit vs strategy", min_value=0, max_value=100, format="%.0f"
        ),
        "Asset": st.column_config.TextColumn(
            "Asset", help="asset class — New build / Renovated / Modern / Dated / Energy liability"
        ),
        "Price": st.column_config.NumberColumn("Price", format="€%d"),
        "Fair value": st.column_config.NumberColumn(
            "Fair value", help="hedonic model's fair price for this flat's attributes", format="€%d"
        ),
        "Value gap": st.column_config.NumberColumn(
            "Value gap", help="+ = priced below fair value (undervalued)", format="%+.0f%%"
        ),
        "€/m²": st.column_config.NumberColumn("€/m²", format="€%.0f"),
        "Area": st.column_config.NumberColumn("Area", format="%.0f m²"),
        "Floor": st.column_config.NumberColumn("Floor", format="%.0f"),
        "Built": st.column_config.NumberColumn(
            "Built", help="build / renovation year", format="%d"
        ),
        "Energy": st.column_config.TextColumn("Energy", help="energy performance class"),
        "Yield": st.column_config.NumberColumn("Yield", format="%.1f%%"),
        "Metro": st.column_config.NumberColumn("Metro", help="walk to Line 3", format="%d m"),
        "Link": st.column_config.LinkColumn("Link", display_text="open ↗"),
    }
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=column_config)


def _kpi_header(listings: list[dict]) -> None:
    eligible = _eligible(listings)
    new = [d for d in eligible if d["is_new"]]
    drops = [d for d in listings if d["price_dropped"]]
    ppm = [d["price_per_m2"] for d in eligible if d["price_per_m2"]]
    median_ppm = statistics.median(ppm) if ppm else None
    cheapest_ppm = min(ppm) if ppm else None

    c = st.columns(5)
    c[0].metric("Opportunities", len(eligible))
    c[1].metric("New (24 h)", len(new))
    c[2].metric("Price drops", len(drops))
    c[3].metric("Median €/m²", fmt.euro_per_m2(median_ppm))
    c[4].metric("Cheapest €/m²", fmt.euro_per_m2(cheapest_ppm))


# ---- investment-thesis helpers --------------------------------------------


def _investment_bullets(d: dict) -> list[str]:
    """Plain-language reasons why this listing is (or isn't) interesting, ordered by impact."""
    bullets: list[str] = []

    # Undervaluation vs hedonic fair value — the headline "is this a real bargain?" signal.
    gap = d.get("value_gap_pct")
    fair = d.get("predicted_price")
    if gap is not None and fair:
        if gap >= 0.10:
            bullets.append(
                f"**{gap*100:.0f}% under fair value** → model prices it at {fmt.euro(fair)} "
                f"vs {fmt.euro(d.get('price', 0))} asked"
            )
        elif gap <= -0.10:
            bullets.append(
                f"**{abs(gap)*100:.0f}% over fair value** — model prices it at {fmt.euro(fair)}"
            )

    # Yield + income — most important signal
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    gy = d.get("gross_yield")
    if gy:
        annual = monthly * 12 if monthly else None
        if annual:
            bullets.append(
                f"**{gy*100:.1f}% gross yield** → {fmt.euro(monthly)}/mo · {fmt.euro(annual)}/yr"
            )
        else:
            bullets.append(f"**{gy*100:.1f}% gross yield**")

    # Newness & energy — quality signals (new/efficient stock rents better, holds value)
    yr = d.get("renovated_year") or d.get("year_built")
    if yr:
        label = "renovated" if d.get("renovated_year") else "built"
        tag = " — **new build**" if yr >= 2010 else (" — dated" if yr < 1990 else "")
        bullets.append(f"{label.capitalize()} **{yr}**{tag}")
    ec = d.get("energy_class")
    if ec:
        score_ec = energy_class_score(ec)
        if score_ec >= 0.75:
            note = " — efficient"
        elif energy_liability_multiplier(ec, get_strategy().scoring_reference) < 0.999:
            note = " — ⚠️ EU-EPBD renovation liability (score reduced)"
        else:
            note = ""
        bullets.append(f"**Energy class {ec}**{note}")

    # Price drop — timing signal
    fp = d.get("first_price")
    cp = d.get("price", 0)
    if fp and cp < fp:
        drop_pct = (fp - cp) / fp * 100
        bullets.append(f"**Price dropped {drop_pct:.0f}%** from original {fmt.euro(fp)}")

    # Private seller — saves agent fees
    if d.get("is_private_seller"):
        bullets.append("**Private seller** — no agent commission")

    # Currently rented — immediate cashflow
    if d.get("is_currently_rented"):
        rent_str = f" at {fmt.euro(d['listed_rent'])}/mo" if d.get("listed_rent") else ""
        bullets.append(f"**Already rented{rent_str}** — cashflow from day 1")

    # Metro proximity — rental demand driver
    metro = d.get("metro_distance_m")
    nearest = d.get("nearest_metro") or "metro"
    if metro is not None:
        qualifier = "steps" if metro <= 200 else ("walk" if metro <= 400 else "")
        if qualifier:
            bullets.append(f"**{metro} m {qualifier} to {nearest}** (Line 3)")
        else:
            bullets.append(f"{metro} m to {nearest}")

    # Timing: days on market
    dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
    if dom is not None:
        if dom == 0:
            bullets.append("**Listed today** — act fast")
        elif dom >= 60:
            bullets.append(f"**{dom} days on market** — seller likely motivated")
        elif dom >= 14:
            bullets.append(f"{dom} days on market")

    return bullets


def _score_breakdown(d: dict, strategy: Strategy) -> None:
    """Render a table showing each signal's contribution to the score."""
    w = strategy.weights
    ref = strategy.scoring_reference
    total_w = w.total() or 1.0

    # Recompute signals from stored fields (mirrors scoring.py, no DB needed)
    gy = d.get("gross_yield") or 0
    span = max(ref.yield_ceiling - ref.yield_floor, 1e-9)
    yield_sig = max(0.0, min(1.0, (gy - ref.yield_floor) / span)) if gy else 0.0

    fp, cp = d.get("first_price"), d.get("price", 0)
    if fp and fp > 0 and cp < fp:
        drop_sig = max(0.0, min(1.0, (fp - cp) / fp / max(ref.max_price_drop_pct, 1e-9)))
    else:
        drop_sig = 0.0

    rented_sig = 1.0 if d.get("is_currently_rented") else 0.0
    private_sig = 1.0 if d.get("is_private_seller") else 0.0
    new_sig = newness_score(d.get("year_built"), d.get("renovated_year"), ref)
    energy_sig = energy_class_score(d.get("energy_class"))
    built = d.get("renovated_year") or d.get("year_built")

    gap = d.get("value_gap_pct")
    target = max(getattr(ref, "target_undervaluation", 0.20), 1e-9)
    if gap is not None:
        under_sig = max(0.0, min(1.0, gap / target))
        under_value = f"{gap*100:+.0f}% vs fair"
        under_score = round(under_sig * w.undervaluation / total_w * 100, 1)
    else:
        # No hedonic fit for this area: the real scorer falls back to €/m²-vs-median,
        # which the UI can't decompose here (it lacks the market medians). Show "—"
        # rather than a misleading 0 that wouldn't reconcile with the total score.
        under_value = "via €/m² fallback"
        under_score = "—"

    rows = [
        {
            "Signal": "Undervaluation",
            "Value": under_value,
            "Score": under_score,
            "Max": round(w.undervaluation / total_w * 100, 1),
        },
        {
            "Signal": "Gross yield",
            "Value": f"{gy*100:.1f}%" if gy else "—",
            "Score": round(yield_sig * w.gross_yield / total_w * 100, 1),
            "Max": round(w.gross_yield / total_w * 100, 1),
        },
        {
            "Signal": "Newness (build/reno yr)",
            "Value": str(built) if built else "—",
            "Score": round(new_sig * w.newness / total_w * 100, 1),
            "Max": round(w.newness / total_w * 100, 1),
        },
        {
            "Signal": "Energy class",
            "Value": d.get("energy_class") or "—",
            "Score": round(energy_sig * w.energy_class / total_w * 100, 1),
            "Max": round(w.energy_class / total_w * 100, 1),
        },
        {
            "Signal": "Price drop",
            "Value": f"{(fp-cp)/fp*100:.0f}% drop" if (fp and cp < fp) else "none",
            "Score": round(drop_sig * w.price_drop / total_w * 100, 1),
            "Max": round(w.price_drop / total_w * 100, 1),
        },
        {
            "Signal": "Currently rented",
            "Value": "✅ yes" if d.get("is_currently_rented") else "✗ no",
            "Score": round(rented_sig * w.is_currently_rented / total_w * 100, 1),
            "Max": round(w.is_currently_rented / total_w * 100, 1),
        },
        {
            "Signal": "Private seller",
            "Value": "✅ yes" if d.get("is_private_seller") else "✗ no",
            "Score": round(private_sig * w.is_private_seller / total_w * 100, 1),
            "Max": round(w.is_private_seller / total_w * 100, 1),
        },
    ]
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.NumberColumn("Score pts", format="%.1f"),
            "Max": st.column_config.NumberColumn("Max pts", format="%.1f"),
        },
    )
    # The final score is scaled down for energy-inefficient stock (EU-EPBD liability), so
    # the weighted rows above don't tell the whole story — surface that adjustment.
    mult = energy_liability_multiplier(d.get("energy_class"), ref)
    if mult < 0.999:
        st.warning(
            f"⚠️ **Energy-liability adjustment: ×{mult:.2f}** — class "
            f"{d.get('energy_class') or '?'} faces EU-EPBD renovation mandates, so the "
            f"final score is reduced ~{(1 - mult) * 100:.0f}% below the weighted total above."
        )
    st.caption(
        "Undervaluation compares the asking price to a hedonic fair value predicted from "
        "this flat's own size, floor, age, energy class, metro distance and area — so it "
        "flags a genuine mispricing, not merely a cheap-but-inferior flat. It needs ≥ 25 "
        "comparables to fit; below that it falls back to raw €/m² vs the area median."
    )


def _fair_value_block(d: dict) -> None:
    """Asking price vs the model's fair value, shown WITH a ±1σ range so the estimate is
    never presented as more precise than the fit supports. Only calls it 'undervalued'
    when the discount exceeds the model's own noise band."""
    fair = d.get("predicted_price")
    gap = d.get("value_gap_pct")
    if not fair or gap is None:
        return
    v = get_valuation_summary()
    # Use THIS listing's submarket band (fall back to the widest overall band).
    area_info = v.get("areas", {}).get(d.get("search_area") or "", {})
    sigma = area_info.get("residual_std") or v.get("overall", {}).get("residual_std") or 0.0
    area_confident = area_info.get("is_confident", v.get("overall", {}).get("is_confident", False))
    lo = int(round(fair * pow(2.718281828, -sigma)))
    hi = int(round(fair * pow(2.718281828, sigma)))
    ask = d.get("price", 0)

    st.markdown("#### 💰 Fair value vs asking")
    cols = st.columns(3)
    cols[0].metric("Asking", fmt.euro(ask))
    cols[1].metric("Model fair value", fmt.euro(fair), delta=f"{gap*100:+.0f}% vs asking")
    cols[2].metric("Fair range (±1σ)", f"{fmt.euro(lo)} – {fmt.euro(hi)}")

    # Only a discount BEYOND the model's noise earns a confident "undervalued" call.
    beyond_noise = ask < lo
    if gap > 0 and beyond_noise and area_confident:
        st.success(
            "Priced **below** the model's fair range — a genuine mispricing signal, not "
            "just a cheap flat."
        )
    elif gap > 0:
        st.caption(
            "Priced below the point estimate, but *within* the model's uncertainty band — "
            "suggestive, not conclusive. Verify the listing before acting."
        )
    elif ask > hi:
        st.warning("Priced **above** the model's fair range — looks overpriced for its attributes.")


def _net_return_and_financing(d: dict, lid: int) -> None:
    """Net yield after Greek buying + operating costs, and a mortgage/cash-on-cash model.

    All inputs are UI-editable assumptions (nothing is stored); the score/thesis are
    unchanged — this is analysis layered on top of the listing's own figures.
    """
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not monthly:
        st.markdown("#### 💶 Net return")
        st.caption("_Needs a rent figure to model net return — none scraped or estimated._")
        return
    annual = monthly * 12
    price = d["price"]
    area = d.get("area_m2")
    private = bool(d.get("is_private_seller"))

    st.markdown("#### 💶 Net return (after Greek buying & operating costs)")
    with st.expander("⚙️ Cost assumptions — edit to match your case"):
        c = st.columns(3)
        vacancy = c[0].number_input("Vacancy %", 0.0, 30.0, 5.0, 0.5, key=f"vac-{lid}") / 100
        maint = c[1].number_input("Maintenance % of rent", 0.0, 30.0, 8.0, 0.5, key=f"maint-{lid}")
        enfia = c[2].number_input("ENFIA €/m²/yr", 0.0, 20.0, 4.0, 0.5, key=f"enfia-{lid}")
        c2 = st.columns(3)
        mgmt = c2[0].number_input("Management % of rent", 0.0, 20.0, 0.0, 0.5, key=f"mgmt-{lid}")
        ins = c2[1].number_input("Insurance % of value/yr", 0.0, 2.0, 0.1, 0.05, key=f"ins-{lid}")
    a = finance.CostAssumptions(
        vacancy_rate=vacancy,
        maintenance_pct_of_rent=maint / 100,
        enfia_eur_per_m2_year=enfia,
        mgmt_pct_of_rent=mgmt / 100,
        insurance_pct_of_value_year=ins / 100,
    )
    ny = finance.net_yield(price, annual, area, private, a)
    noi = finance.net_operating_income(annual, price, area, a)
    acq = finance.acquisition_costs(price, private, a)
    nc = st.columns(4)
    nc[0].metric("Net yield", fmt.pct(ny), help="Net operating income ÷ (price + buying costs)")
    nc[1].metric("Gross yield", fmt.pct(d.get("gross_yield")))
    nc[2].metric("Net income/yr", fmt.euro(noi), help="Rent after vacancy, mgmt, maintenance, tax")
    nc[3].metric(
        "Buying costs",
        fmt.euro(acq),
        help="Transfer tax, notary, legal" + ("" if private else ", agent"),
    )

    st.markdown("#### 🏦 Financing (mortgage & cash-on-cash)")
    fc = st.columns(3)
    deposit = fc[0].slider("Deposit %", 10, 100, 30, key=f"dep-{lid}") / 100
    rate = fc[1].slider("Interest rate %", 0.0, 10.0, 4.0, 0.1, key=f"rate-{lid}") / 100
    years = fc[2].slider("Term (years)", 5, 40, 25, key=f"term-{lid}")
    lev = finance.leverage_summary(price, annual, area, private, deposit, rate, years, a)
    if lev:
        lc = st.columns(4)
        lc[0].metric("Monthly payment", fmt.euro(lev["monthly_payment"]))
        lc[1].metric("Cash invested", fmt.euro(lev["cash_invested"]), help="Deposit + buying costs")
        lc[2].metric("Cashflow/yr after debt", fmt.euro(lev["annual_cashflow_after_debt"]))
        lc[3].metric(
            "Cash-on-cash", fmt.pct(lev["cash_on_cash"]), help="Annual cashflow ÷ cash invested"
        )


def _comparables(d: dict, listings: list[dict]) -> None:
    """Similar active listings in the same neighborhood, with a €/m² delta vs this one."""
    rows = comps.find_comparables(d, listings)
    if not rows:
        st.caption("No comparable active listings in this neighborhood yet.")
        return
    records = [
        {
            "Price": c["price"],
            "€/m²": c["price_per_m2"],
            "Area": c["area_m2"],
            "Floor": c["floor"],
            "vs this €/m²": c.get("ppm2_delta_pct"),
            "Score": round(c["score"], 0),
            "Link": c["url"],
        }
        for c in rows
    ]
    st.dataframe(
        pd.DataFrame(records),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Price": st.column_config.NumberColumn("Price", format="€%d"),
            "€/m²": st.column_config.NumberColumn("€/m²", format="€%.0f"),
            "Area": st.column_config.NumberColumn("Area", format="%.0f m²"),
            "Floor": st.column_config.NumberColumn("Floor", format="%.0f"),
            "vs this €/m²": st.column_config.NumberColumn(
                "vs this €/m²", help="Negative = cheaper per m² than this listing", format="%+.0f%%"
            ),
            "Score": st.column_config.NumberColumn("Score", format="%.0f"),
            "Link": st.column_config.LinkColumn("Link", display_text="open ↗"),
        },
    )
    st.caption("Same neighborhood, within ±25% area and ±30% price, ranked by €/m² closeness.")


# ---- pages -----------------------------------------------------------------


def page_opportunities(listings: list[dict]) -> None:
    st.subheader("Opportunities")
    _valuation_banner()

    if not listings:
        st.info(
            "No listings yet. Press **🔄 Refresh now** in the sidebar to run the "
            "pipeline, or wait for the daily scrape."
        )
        return

    eligible = _eligible(listings)

    # Never blank: if the hard filters reject everything, still show the real data
    # with the reason each was filtered, so the user always sees what was scraped.
    if not eligible:
        st.warning(
            f"**{len(listings)}** listings were scraped, but none pass your current "
            "hard filters. Showing them all below with the reason each was filtered — "
            "loosen the rules on the **Strategy** page to surface more."
        )
        rows = sorted(listings, key=lambda d: (d["price_per_m2"] or float("inf")))
        _table(rows, show_reason=True)
        return

    # Sidebar filters — defaults include everything so nothing hides silently.
    with st.sidebar:
        st.subheader("Filters")
        # Region filter — the classic Attica grouping (Κέντρο / Βόρεια / Νότια / Δυτικά /
        # Πειραιάς). Default = all regions present, so nothing hides until the user picks.
        present_regions = [r for r in REGIONS if any(d.get("region") == r for d in eligible)]
        chosen_regions = (
            st.multiselect("Περιοχή / Region", present_regions, default=present_regions)
            if present_regions
            else []
        )
        near_metro_only = st.checkbox(
            "🚇 Μόνο κοντά σε μετρό / Near metro only",
            value=False,
            help="Keep only listings within the metro distance below (Line 2/3).",
        )
        prices = [d["price"] for d in eligible]
        pmin, pmax = min(prices), max(prices)
        price_range = (
            st.slider("Price (€)", pmin, pmax, (pmin, pmax), step=5000)
            if pmin < pmax
            else (pmin, pmax)
        )
        areas = [d["area_m2"] for d in eligible]
        amin, amax = int(min(areas)), int(max(areas)) + 1
        area_range = (
            st.slider("Area (m²)", amin, amax, (amin, amax)) if amin < amax else (amin, amax)
        )
        min_yield = st.slider("Min gross yield (%)", 0.0, 12.0, 0.0, step=0.5) / 100
        min_value_gap = st.slider(
            "Min value gap (% below fair value)",
            0,
            40,
            0,
            step=5,
            help="Only flats the hedonic model prices at least this far below fair value.",
        )
        min_year = st.slider("Built/renovated after", 1950, 2025, 1950, step=5)
        new_only = st.checkbox("New builds only (≥ 2010)", value=False)
        include_unknown_year = st.checkbox("Include unknown build year", value=True)
        max_metro = st.slider("Max metro distance (m)", 0, 5000, 5000, step=50)
        include_unknown_metro = st.checkbox("Include unknown metro distance", value=True)

    def _built_year(d: dict) -> int | None:
        return d.get("renovated_year") or d.get("year_built")

    def keep(d: dict) -> bool:
        if chosen_regions and d.get("region") not in chosen_regions:
            return False
        if not (price_range[0] <= d["price"] <= price_range[1]):
            return False
        if not (area_range[0] <= d["area_m2"] <= area_range[1]):
            return False
        if (d["gross_yield"] or 0) < min_yield:
            return False
        if min_value_gap > 0:
            gap = d.get("value_gap_pct")
            if gap is None or gap * 100 < min_value_gap:
                return False
        yr = _built_year(d)
        effective_min = max(min_year, 2010) if new_only else min_year
        if yr is None:
            if new_only or not include_unknown_year:
                return False
        elif yr < effective_min:
            return False
        if d["metro_distance_m"] is None:
            # "Near metro only" is a hard walk-to-metro requirement: an unlocatable
            # listing can't prove it qualifies, so it's excluded when the toggle is on.
            return include_unknown_metro and not near_metro_only
        limit = (
            min(max_metro, get_strategy().hard_filters.max_metro_distance_m)
            if near_metro_only
            else max_metro
        )
        return d["metro_distance_m"] <= limit

    rows = sorted([d for d in eligible if keep(d)], key=lambda d: d["score"], reverse=True)

    st.markdown(f"**{len(rows)}** opportunities match your filters (of {len(eligible)} eligible)")
    if rows:
        # Cap the card grid to the top N by score — rendering all ~9k cards ships a
        # multi-megabyte DOM that janks the browser. The full set stays in the table/CSV.
        grid_cap = 60
        components.listing_grid(rows[:grid_cap])
        if len(rows) > grid_cap:
            st.caption(f"Showing the top {grid_cap} cards by score. Full list in the table below.")
        with st.expander("Table view (sort / export)"):
            _table(rows)
    else:
        st.info("No listings match the current filters. Widen them in the sidebar.")


def page_today(listings: list[dict]) -> None:
    st.subheader("Today")
    st.caption("New in the last 24 h that pass the hard filters, ranked by score.")
    today = sorted(
        [d for d in _eligible(listings) if d["is_new"]], key=lambda d: d["score"], reverse=True
    )
    if not today:
        st.info("Nothing new in the last 24 h. See **Opportunities** for the full list.")
        return
    components.listing_grid(today)


def page_map(listings: list[dict]) -> None:
    st.subheader("Map")
    pts = [d for d in _eligible(listings) if d["lat"] and d["lng"]]
    if not pts:
        st.info(
            "No geocoded listings to map yet. Geocoding runs during the pipeline; "
            "if listings show 'unknown' metro distance, geocoding hasn't resolved them."
        )
        return
    from scout.enrich import METRO_STATIONS

    listing_df = pd.DataFrame({"lat": d["lat"], "lon": d["lng"], "score": d["score"]} for d in pts)
    metro_df = pd.DataFrame(
        {"lat": lat, "lon": lng, "name": n} for n, (lat, lng) in METRO_STATIONS.items()
    )
    try:
        import pydeck as pdk

        st.pydeck_chart(
            pdk.Deck(
                map_style=None,
                initial_view_state=pdk.ViewState(
                    latitude=listing_df["lat"].mean(),
                    longitude=listing_df["lon"].mean(),
                    zoom=13,
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=listing_df,
                        get_position="[lon, lat]",
                        get_fill_color="[255 - score*2.55, score*2.55, 80]",
                        get_radius=60,
                        pickable=True,
                    ),
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=metro_df,
                        get_position="[lon, lat]",
                        get_fill_color="[30, 90, 255]",
                        get_radius=90,
                    ),
                ],
                tooltip={"text": "Score: {score}"},
            )
        )
        st.caption("Listings colored green (high score) → red (low). Blue = metro stations.")
    except Exception:
        st.map(listing_df)


def page_detail(listings: list[dict]) -> None:
    st.subheader("Listing detail")
    options = {f"[{d['score']:.0f}] {d['title'] or d['source_id']}": d["id"] for d in listings}
    if not options:
        st.info("No listings.")
        return
    choice = st.selectbox("Listing", list(options.keys()))
    lid = options[choice]
    d = next(x for x in listings if x["id"] == lid)

    # --- top metrics row ---
    fp = d.get("first_price")
    price_delta = fmt.euro(d["price"] - fp) if fp else None
    cols = st.columns(5)
    cols[0].metric("Price", fmt.euro(d["price"]), delta=price_delta, delta_color="inverse")
    cols[1].metric("€/m²", fmt.euro_per_m2(d["price_per_m2"]))
    cols[2].metric("Gross yield", fmt.pct(d["gross_yield"]))
    dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
    cols[3].metric("Days on market", dom if dom is not None else "—")
    cols[4].metric("Score", f"{d['score']:.0f} / 100")

    st.write(" ".join(fmt.badges(d)) or "_no badges_")
    if d["excluded"]:
        st.error(f"Excluded by hard filter: {d['exclusion_reason']}")

    # --- investment math ---
    st.markdown("#### 💰 Investment case")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if monthly:
        annual = monthly * 12
        gy = d.get("gross_yield")
        math_cols = st.columns(4)
        math_cols[0].metric("Est. monthly rent", fmt.euro(monthly))
        math_cols[1].metric("Annual income", fmt.euro(annual))
        math_cols[2].metric("Purchase price", fmt.euro(d["price"]))
        math_cols[3].metric("Gross yield", fmt.pct(gy))
        if fp and d["price"] < fp:
            drop_pct = (fp - d["price"]) / fp * 100
            st.info(
                f"📉 Price dropped **{drop_pct:.0f}%** from {fmt.euro(fp)} to {fmt.euro(d['price'])} "
                f"(saved {fmt.euro(fp - d['price'])})"
            )
    else:
        st.caption("_No rent data scraped — yield estimate uses the strategy fallback €/m²/month._")

    bullets = _investment_bullets(d)
    if bullets:
        for b in bullets:
            st.markdown(f"• {b}")

    # --- fair value vs asking (with honest uncertainty) ---
    _fair_value_block(d)

    # --- net return (after Greek costs) + financing ---
    _net_return_and_financing(d, lid)

    # --- score breakdown ---
    strategy = get_strategy()
    st.markdown("#### 📊 Score breakdown")
    _score_breakdown(d, strategy)

    # --- comparable listings ---
    st.markdown("#### 🔁 Comparable active listings nearby")
    _comparables(d, listings)

    # --- property specs ---
    st.markdown("#### 🏗️ Property specs")
    spec_cols = st.columns(3)
    spec_cols[0].markdown(
        f"**Area:** {d['area_m2']:.0f} m²  \n"
        f"**Bedrooms:** {d['bedrooms'] or '—'}  \n"
        f"**Floor:** {_floor_label(d['floor'])}  \n"
        f"**Built:** {d.get('year_built') or '—'}"
        + (f" (renov. {d['renovated_year']})" if d.get("renovated_year") else "")
    )
    spec_cols[1].markdown(
        f"**Neighborhood:** {d['neighborhood'] or '—'}  \n"
        f"**Address:** {d['address'] or '—'}  \n"
        f"**Nearest metro:** {d.get('nearest_metro') or '—'}  \n"
        f"**Metro distance:** {_metro_label(d)}"
    )
    spec_cols[2].markdown(
        f"**Energy class:** {d.get('energy_class') or '—'}  \n"
        f"**Heating:** {d.get('heating') or '—'}  \n"
        f"**Private seller:** {'✅ yes' if d['is_private_seller'] else '✗ no'}  \n"
        f"**Currently rented:** {'✅ yes' if d['is_currently_rented'] else '✗ no'}"
    )

    # --- price history ---
    st.markdown("#### 📈 Price history")
    history = get_history(lid)
    if len(history) >= 2:
        hist_df = pd.DataFrame(history, columns=["observed_at", "price"]).set_index("observed_at")
        st.line_chart(hist_df)
    elif len(history) == 1:
        st.caption(
            f"First recorded price: {fmt.euro(history[0][1])} on {history[0][0]:%Y-%m-%d}. "
            "Price history builds up over multiple pipeline runs."
        )
    else:
        st.caption("No price history yet — runs each day and accumulates over time.")

    st.link_button("Open on portal ↗", d["url"])
    watched = st.checkbox("On watchlist", value=d["is_watched"], key=f"watch-{lid}")
    if watched != d["is_watched"]:
        queries.set_watched(lid, watched)
        st.cache_data.clear()
        st.rerun()


def page_watchlist(listings: list[dict]) -> None:
    st.subheader("Watchlist")
    watched = [d for d in listings if d["is_watched"]]
    if not watched:
        st.info("Pin listings from the **Listing detail** page to watch them here.")
        return
    for d in watched:
        if d["price_dropped"]:
            st.success(
                f"📉 {d['title']} dropped to {fmt.euro(d['price'])} "
                f"(from {fmt.euro(d['first_price'])})"
            )
    _table(sorted(watched, key=lambda d: d["score"], reverse=True))


def page_strategy() -> None:
    st.subheader("Strategy")
    st.caption("Edit the investor's rules & weights, then re-score live — no redeploy.")
    strategy = load_strategy()

    with st.form("strategy"):
        st.markdown("**Hard filters**")
        min_floor = st.number_input("Min floor", value=strategy.hard_filters.min_floor, step=1)
        max_metro = st.number_input(
            "Max metro distance (m)", value=strategy.hard_filters.max_metro_distance_m, step=50
        )
        st.markdown("**Weights**")
        w = strategy.weights
        under = st.slider(
            "Undervaluation (vs hedonic fair value)", 0.0, 50.0, float(w.undervaluation)
        )
        gy = st.slider("Gross yield", 0.0, 50.0, float(w.gross_yield))
        newness = st.slider("Newness (build/reno year)", 0.0, 50.0, float(w.newness))
        energy = st.slider("Energy class", 0.0, 50.0, float(w.energy_class))
        pd_ = st.slider("Price drop", 0.0, 50.0, float(w.price_drop))
        rented = st.slider("Currently rented", 0.0, 50.0, float(w.is_currently_rented))
        private = st.slider("Private seller", 0.0, 50.0, float(w.is_private_seller))
        st.markdown("**Newness reference**")
        by_floor = st.number_input(
            "Build year = 0 signal at/below",
            value=strategy.scoring_reference.build_year_floor,
            step=5,
        )
        by_ceiling = st.number_input(
            "Build year = full signal at/above",
            value=strategy.scoring_reference.build_year_ceiling,
            step=5,
        )
        submitted = st.form_submit_button("Save & re-score")

    if submitted:
        strategy.hard_filters.min_floor = int(min_floor)
        strategy.hard_filters.max_metro_distance_m = int(max_metro)
        strategy.weights.undervaluation = under
        strategy.weights.gross_yield = gy
        strategy.weights.newness = newness
        strategy.weights.energy_class = energy
        strategy.weights.price_drop = pd_
        strategy.weights.is_currently_rented = rented
        strategy.weights.is_private_seller = private
        strategy.scoring_reference.build_year_floor = int(by_floor)
        strategy.scoring_reference.build_year_ceiling = int(by_ceiling)
        save_strategy(strategy)
        from scout.pipeline import rescore_all

        n = rescore_all(strategy)
        st.cache_data.clear()
        st.success(f"Saved and re-scored {n} listings.")


def page_debug() -> None:
    st.subheader("🐛 Debug")
    st.caption("Raw data & pipeline diagnostics for troubleshooting.")

    rows = get_all_listings_debug()
    if not rows:
        st.warning("Database is empty — run the pipeline.")
        return

    active = [d for d in rows if d["status"] == "active"]
    last_up = _last_updated(rows)
    first_seens = [d["first_seen"] for d in rows if d["first_seen"]]

    c = st.columns(4)
    c[0].metric("Total records", len(rows))
    c[1].metric("Active", len(active))
    c[2].metric("Excluded", sum(1 for d in rows if d["excluded"]))
    c[3].metric("Geocoded", sum(1 for d in rows if d["lat"] and d["lng"]))

    st.write(
        f"**Data last updated:** {last_up:%Y-%m-%d %H:%M:%S} UTC"
        if last_up
        else "**Data last updated:** never"
    )
    if first_seens:
        st.write(f"**Earliest record seen:** {min(first_seens):%Y-%m-%d %H:%M:%S} UTC")

    st.markdown("**Records by source**")
    src: dict[str, int] = {}
    for d in rows:
        src[d["source"]] = src.get(d["source"], 0) + 1
    st.write(src)

    st.markdown("**All records (raw, including excluded & inactive)**")
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "⬇️ Download as CSV", df.to_csv(index=False).encode("utf-8"), "holargos_listings.csv"
    )

    _health_panel()


def _health_panel() -> None:
    """Live scraper-health + job-queue status, so the owner can spot a broken scrape
    without opening a DB console. Every part is guarded — the panel must never crash
    the page (e.g. on an older DB missing the scrape_job / health_report tables)."""
    st.divider()
    st.markdown("### 🩺 Scraper health")
    try:
        from scout.health import check_health

        report = check_health()
        icon = {"ok": "✅", "warn": "⚠️", "error": "🚨"}.get(report.status, "•")
        st.write(f"{icon} **{report.status.upper()}**")
        for issue in report.issues:
            st.write(f"- {issue}")
        st.json(report.metrics)
    except Exception as exc:
        st.caption(f"Health check unavailable: {exc}")
    try:
        from scout.queue import job_stats

        st.write("**Scrape-job queue:**", job_stats())
    except Exception:
        pass
    recent = get_recent_health()
    if recent:
        st.markdown("**Recent health snapshots**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"checked_at": r["checked_at"], "status": r["status"], "issues": r["issues"]}
                    for r in recent
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def page_neighborhoods(listings: list[dict]) -> None:
    st.subheader("Neighborhood analytics")
    st.caption("Per-area market stats over the eligible (hard-filter-passing) listings.")
    stats = analytics.neighborhood_stats(_eligible(listings))
    if not stats:
        st.info("No neighborhood data yet — run the pipeline to populate listings.")
        return
    records = [
        {
            "Neighborhood": s["neighborhood"],
            "Listings": s["count"],
            "Median price": s["median_price"],
            "Median €/m²": s["median_ppm2"],
            "Median yield": s["median_yield_pct"],
            "Opportunities": s["opportunities"],
            "Rented": s["rented"],
        }
        for s in stats
    ]
    st.dataframe(
        pd.DataFrame(records),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Median price": st.column_config.NumberColumn("Median price", format="€%d"),
            "Median €/m²": st.column_config.NumberColumn("Median €/m²", format="€%.0f"),
            "Median yield": st.column_config.NumberColumn("Median yield", format="%.1f%%"),
        },
    )

    st.markdown("#### 📈 Market price index (monthly median)")
    idx = analytics.market_price_index(get_all_price_history())
    if len(idx) >= 2:
        idx_df = pd.DataFrame(idx).set_index("month")[["median_price"]]
        st.line_chart(idx_df)
        st.caption("Median recorded price across all listings, by month.")
    else:
        st.caption("The price index builds up over multiple pipeline runs.")


def page_deals(listings: list[dict]) -> None:
    """Motivated-seller intelligence — the sellable core: owners most likely to negotiate,
    ranked by the negotiation signal, with an exportable agent lead list."""
    import csv
    import io

    st.subheader("💰 Deals — motivated sellers")
    st.caption(
        "Owners most likely to negotiate, ranked by days-on-market, price cuts, "
        "over-asked-and-sitting, and relistings — the signals free portals hide. This "
        "sharpens every day the tracker runs (the price/status history compounds)."
    )
    eligible = _eligible(listings)
    ranked = sorted(eligible, key=lambda d: d.get("negotiation_score") or 0, reverse=True)
    motivated = [d for d in ranked if (d.get("negotiation_score") or 0) >= 45]

    c = st.columns(3)
    c[0].metric("Motivated-seller leads", len(motivated))
    c[1].metric("Tracked & eligible", len(eligible))
    tracked_days = None
    seens = [d["first_seen"] for d in eligible if d.get("first_seen")]
    if seens:
        tracked_days = (datetime.utcnow() - min(seens)).days
    c[2].metric("Market tracked for", f"{tracked_days} d" if tracked_days is not None else "—")

    # Agent lead export (the Pro product — a per-territory motivated-seller list).
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "negotiation_score",
            "price_eur",
            "area_m2",
            "neighborhood",
            "days_on_market",
            "price_cut_pct",
            "private_seller",
            "url",
        ]
    )
    for d in ranked:
        dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
        fp, cp = d.get("first_price"), d.get("price", 0)
        cut = (fp - cp) / fp if (fp and cp < fp) else 0.0
        w.writerow(
            [
                round(d.get("negotiation_score") or 0, 1),
                d["price"],
                f"{d['area_m2']:.0f}",
                d.get("neighborhood") or "",
                dom if dom is not None else "",
                f"{cut * 100:.0f}%",
                "yes" if d.get("is_private_seller") else "no",
                d["url"],
            ]
        )
    st.download_button(
        "⬇  Export agent lead list (CSV) — **Pro**",
        buf.getvalue(),
        "motivated_sellers.csv",
        "text/csv",
        help="The per-territory motivated-seller list agents subscribe for.",
    )

    if not motivated:
        st.info(
            "No strong motivated-seller signals yet — this is expected on a fresh market. "
            "The signal is built from **change over time** (price cuts, days-on-market, "
            "relistings); it fills in as the daily tracker accumulates history. Showing the "
            "current ranking below."
        )
    components.listing_grid(ranked[:60])


PAGES = {
    "Opportunities": page_opportunities,
    "Deals": page_deals,
    "Today": page_today,
    "Map": page_map,
    "Neighborhoods": page_neighborhoods,
    "Listing detail": page_detail,
    "Watchlist": page_watchlist,
}


def main() -> None:
    st.title("🏠 Holargos Property Scout")

    with st.sidebar:
        if st.button("🔄 Refresh now (run pipeline)", use_container_width=True):
            with st.spinner("Running pipeline…"):
                from scout.pipeline import run

                summary = run()
            st.cache_data.clear()
            st.success(f"Done: {summary}")
        page = st.radio("Page", [*PAGES.keys(), "Strategy", "Debug"])

    listings = get_listings()

    last_up = _last_updated(listings)
    if last_up is not None:
        sources = sorted({d["source"] for d in listings if d.get("source")})
        src_label = ", ".join(s.upper() for s in sources) if sources else "—"
        st.caption(
            f"🕒 Data last updated **{last_up:%Y-%m-%d %H:%M} UTC** · "
            f"{len(listings)} active listings · source: {src_label}"
        )
        if len(sources) <= 1:
            st.caption(
                "ℹ️ Coverage is currently a single portal (XE.gr) — a slice of the market, "
                "not every listing. Additional portals (Spitogatos, Indomio) are supported "
                "and can be enabled to broaden coverage."
            )
    else:
        st.caption("🕒 No data yet — press **Refresh now** or wait for the daily run.")

    # KPI header on the data-centric pages.
    if page in ("Opportunities", "Today"):
        _kpi_header(listings)
        st.divider()

    if page == "Strategy":
        page_strategy()
    elif page == "Debug":
        page_debug()
    else:
        PAGES[page](listings)


main()
