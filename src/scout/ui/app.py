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

import os  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

# Streamlit Cloud's Secrets manager populates st.secrets, NOT the process environment —
# but Settings (config.py) is a pydantic-settings BaseSettings that only reads env vars /
# .env. Bridge DATABASE_URL across so the deployed app reaches the same Postgres the daily
# workflow writes to, instead of silently falling back to a local (empty) SQLite file.
# Guarded: st.secrets raises if no secrets.toml exists at all (e.g. local `streamlit run`).
try:
    if "DATABASE_URL" in st.secrets:
        os.environ.setdefault("DATABASE_URL", st.secrets["DATABASE_URL"])
except Exception:
    pass

from scout import (  # noqa: E402
    acquisition,
    analytics,
    comps,
    comps_panel,
    deal_scorecard,
    epbd,
    finance,
    investment,
    liquidity,
    listing_report,
    projection,
    score_explain,
    sensitivity,
)
from scout.config import Strategy, load_strategy, save_strategy  # noqa: E402
from scout.regions import REGIONS  # noqa: E402
from scout.regulatory import (  # noqa: E402
    golden_visa_status,
    renovation_subsidy,
    str_legality,
)
from scout.relative_value import annotate_relative_value, relative_value  # noqa: E402
from scout.scoring import (
    energy_class_score,
    energy_liability_multiplier,
    newness_score,
)  # noqa: E402
from scout.strategy_fit import strategy_tags  # noqa: E402
from scout.ui import (
    components,  # noqa: E402
    queries,  # noqa: E402
)
from scout.ui import format as fmt  # noqa: E402
from scout.ui.theme import inject_css  # noqa: E402

st.set_page_config(
    page_title="Holargos Property Scout",
    page_icon="🏠",
    layout="wide",
    # Keep the filter sidebar open on load (mobile/narrow viewports otherwise hide it
    # behind the « chevron and the filters look "lost").
    initial_sidebar_state="expanded",
)
inject_css()

# MEMORY: the big reads use st.cache_RESOURCE, not cache_data. cache_data pickles the
# value and hands every access a fresh deep copy — with 22k listing dicts (~226 MB
# materialised) a couple of concurrent reruns blew straight past Streamlit Community
# Cloud's ~1 GB limit and the app OOM-restarted (dropped websocket, "lost" sidebar).
# cache_resource shares ONE object across sessions; pages treat these as READ-ONLY —
# never mutate a dict from these caches (copy first).


@st.cache_resource(ttl=300)
def get_listings() -> list[dict]:
    rows = queries.load_listings(include_excluded=True, only_active=True)
    # Annotate each listing's honest market-position rank (cheaper per m² than X% of
    # comparable active listings) — needs the whole pool, so do it once here. Then recompute
    # strategy tags: the "Underpriced" tag now keys off this percentile, which only exists
    # after annotation (queries.py computed tags per-row before the pool was known).
    annotate_relative_value(rows)
    for d in rows:
        d["strategy_tags"] = strategy_tags(d)
    return rows


@st.cache_data(ttl=300)
def get_strategy() -> Strategy:
    return load_strategy()


@st.cache_resource(ttl=600)
def get_all_listings_debug() -> list[dict]:
    """Everything, including excluded and inactive (gone) listings — for the Debug page."""
    return queries.load_listings(
        include_excluded=True, only_active=False, collapse_relistings=False
    )


@st.cache_data(ttl=60)
def get_history(listing_id: int):
    return queries.load_price_history(listing_id)


@st.cache_resource(ttl=600)
def get_all_price_history() -> list[dict]:
    return queries.load_all_price_history()


@st.cache_data(ttl=120)
def get_recent_health() -> list[dict]:
    return queries.load_recent_health(10)


@st.cache_resource(ttl=300)
def get_valuation_summary() -> dict:
    return queries.load_valuation_summary()


@st.cache_data(ttl=60)
def get_recent_price_drops(hours: int = 24) -> list[dict]:
    return queries.load_recent_price_drops(hours)


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
    # One-line headline, with the full honesty caveats tucked in an expander so the top of
    # the page isn't a five-line wall of yellow text on every visit.
    conf = "reliable" if o["is_confident"] else "indicative — shortlist, then verify"
    headline = f"📐 Fair-value model: R²={r2:.2f}, typical range {band} — {conf}."
    (st.success if o["is_confident"] else st.warning)(headline)
    with st.expander("How to read the fair-value figures"):
        st.markdown(
            f"{scope}. {basis} A wide ± range means the model can't price that submarket "
            "precisely — use the ranking to shortlist and verify each listing on the portal."
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


def _max_affordable_price(
    monthly_income: float,
    *,
    dsr: float = 0.35,
    rate: float = 0.045,
    term_years: int = 25,
    deposit_pct: float = 0.30,
) -> int | None:
    """Max purchase price supported by a monthly net income: cap the mortgage payment at a
    debt-service ratio of income, invert the amortization to a loan, then gross up for the
    deposit. A rough affordability gate for filtering, not mortgage advice."""
    if monthly_income <= 0:
        return None
    max_payment = monthly_income * dsr
    r = rate / 12
    n = term_years * 12
    loan = max_payment * n if r <= 0 else max_payment * (1 - (1 + r) ** -n) / r
    return int(loan / max(1 - deposit_pct, 1e-9))


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
            # Honest market-position rank: cheaper per m² than N% of comparable active listings.
            "vs market": (
                d["value_percentile"] * 100 if d.get("value_percentile") is not None else None
            ),
            "€/m²": d["price_per_m2"],
            "Area": d["area_m2"],
            "Floor": d["floor"],
            "Built": d.get("renovated_year") or d.get("year_built"),
            "Energy": d.get("energy_class") or "",
            "Yield": (d["gross_yield"] * 100) if d["gross_yield"] is not None else None,
            "Short-let": {
                "FROZEN": "🚫 frozen",
                "EXPANDING_RISK": "⚠️ risk",
                "ALLOWED": "✓ ok",
            }.get(str_legality(_area_key(d)).status, ""),
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
            "Fair value (est.)",
            help="Model estimate vs TYPICAL ASKING for similar flats (±44% band, not a "
            "sold-price valuation — Greece has no open sold register). Blank when too noisy.",
            format="€%d",
        ),
        "Value gap": st.column_config.NumberColumn(
            "vs asking (est.)",
            help="+ = priced below the model's estimate of typical asking. An indicative "
            "screen, not a proven discount.",
            format="%+.0f%%",
        ),
        "vs market": st.column_config.NumberColumn(
            "vs market",
            help="Cheaper per m² than this % of comparable active listings (same area, ±30% "
            "size). A true market-position rank — no sold-price data, no pseudo-precision.",
            format="%.0f%%",
        ),
        "Short-let": st.column_config.TextColumn(
            "Short-let", help="Can a buyer legally run a NEW Airbnb here? (2026 Athens freeze)"
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
    nys = [d["net_yield"] for d in eligible if d.get("net_yield") is not None]
    median_ny = statistics.median(nys) if nys else None
    # Lead with what's REAL and differentiated, not with "every eligible listing = an
    # opportunity" (which flagged 82% of inventory and sorted nothing). Two honest headline
    # counts: the curated BUY verdicts (the actual shortlist), and the regulatory signal no
    # portal offers — how many listings a buyer cannot legally short-let, and how many clear
    # the Golden-Visa bar. These are computed from data we already hold, no history needed.
    buys = sum(1 for d in eligible if d.get("rec_verdict") == "BUY")
    str_frozen = sum(1 for d in eligible if str_legality(_area_key(d)).status == "FROZEN")
    # Golden Visa is intentionally NOT a headline here: this suburban inventory is almost
    # entirely below the €800k Attica threshold, so the count is ~0 — useless as a KPI (it
    # still shows per-listing on the detail page for the rare qualifier). The energy-subsidy
    # candidate count IS real and populated (74% of listings carry an EPC class).
    reno = sum(
        1
        for d in eligible
        if renovation_subsidy(d.get("energy_class"), d.get("year_built")).candidate
    )

    # Four short-labelled metrics (was five with long labels that truncated to "LISTINGS T…").
    # Energy-subsidy drops off the headline — it stays a sidebar filter and a per-card badge.
    _ = reno  # still computed for parity / possible reuse; not shown in the compact header
    c = st.columns(4)
    c[0].metric("Listings", len(eligible), help="Active listings after your filters")
    c[1].metric(
        "🟢 BUY picks",
        buys,
        help="Listings that clear the verified BUY bar — the curated shortlist, not all inventory",
    )
    c[2].metric(
        "🚫 No short-let",
        str_frozen,
        help="In Athens districts where a buyer cannot get a new Airbnb licence (2026 freeze)",
    )
    c[3].metric("Median yield", fmt.pct(median_ny) if median_ny is not None else "—")


def _area_key(d: dict) -> str | None:
    """The area name to resolve regulatory zones against. `search_area` is the clean Latin
    scrape area ("Koukaki", "Pagkrati") that matches the regulatory tables; `neighborhood`
    is free-text Greek ("Αθήνα (Κουκάκι)") and won't match — so prefer search_area."""
    return d.get("search_area") or d.get("neighborhood")


def _regulatory_panel(d: dict) -> None:
    """The differentiator no portal shows: can a buyer legally short-let this, does it clear
    the Golden-Visa bar, is it an energy-subsidy candidate. Indicative flags — always tell the
    user to verify with a lawyer; regulation shifts and a wrong call costs real money."""
    strl = str_legality(_area_key(d))
    gv = golden_visa_status(d.get("price"), d.get("area_m2"))
    reno = renovation_subsidy(d.get("energy_class"), d.get("year_built"))

    st.markdown("#### 📜 Regulatory check — what portals don't tell you")
    box = {"FROZEN": st.error, "EXPANDING_RISK": st.warning, "ALLOWED": st.success}.get(
        strl.status, st.info
    )
    box(f"**Short-let (Airbnb):** {strl.headline} — {strl.detail}")

    cols = st.columns(2)
    (cols[0].success if gv.qualifies else cols[0].info)(
        f"**Golden Visa:** {gv.headline}" + (f" — {gv.detail}" if gv.detail else "")
    )
    if reno.candidate:
        cols[1].info(f"**Energy subsidy:** {reno.headline} — {reno.detail}")
    else:
        cols[1].caption("Energy subsidy: not flagged (needs EPC class C or lower).")
    st.caption(
        "⚖️ Indicative flags from public 2026 rules — confirm STR/visa/subsidy eligibility "
        "with a Greek lawyer before committing. Sources in docs/PRODUCT_STRATEGY.md."
    )


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
    # Plain-language "why this score" first — what lifted it, what lowered it, what's
    # unknown (and therefore not scored) — before the detailed weight table.
    rows = score_explain.explain_score(d)
    if rows:
        icon = {"positive": "🟢", "negative": "🔴", "unknown": "⚪"}
        for r in rows:
            st.markdown(f"{icon.get(r['effect'], '•')} **{r['label']}** — {r['detail']}")
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
        # Keep the column numeric (None → blank cell). A "—" string here made the whole
        # "Score" column object-dtype, which Streamlit/pyarrow can't serialise under the
        # NumberColumn config — the breakdown table then fell back to unformatted text.
        under_score = None

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
    # Fall back to the softer, tested comps panel so the section is never empty just because
    # nothing sat inside the strict tolerance bands.
    if not rows:
        rows = comps_panel.comparable_listings(d, listings, n=6)
    if not rows:
        st.caption("No comparable active listings in this neighborhood yet.")
        return
    records = [
        {
            "Price": c.get("price"),
            "€/m²": c.get("price_per_m2"),
            "Area": c.get("area_m2"),
            "Floor": c.get("floor"),
            "vs this €/m²": c.get("ppm2_delta_pct"),
            "Score": round(c["score"], 0) if c.get("score") is not None else None,
            "Link": c.get("url"),
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


def _acquisition_block(d: dict) -> None:
    """Total cash to actually buy — sticker price is not the real cost. Greek purchase
    carries transfer tax, notary, land registry, legal and (unless private) agent fees."""
    price = d.get("price")
    if not price:
        return
    private = bool(d.get("is_private_seller"))
    ac = acquisition.acquisition_costs(price, agent_fee_pct=0.0 if private else 0.0248)
    st.markdown("#### 🧾 Total acquisition cost")
    c = st.columns(4)
    c[0].metric("Sticker price", fmt.euro(ac["price"]))
    c[1].metric(
        "Fees & taxes",
        fmt.euro(ac["total_fees"]),
        help="Transfer tax, notary, registry, legal, agent",
    )
    c[2].metric("Total cash-in", fmt.euro(ac["total_cash"]))
    c[3].metric("Fees % of price", f"{ac['fees_pct_of_price'] * 100:.1f}%")
    st.caption(
        f"Transfer tax {fmt.euro(ac['transfer_tax'])} · notary {fmt.euro(ac['notary'])} · "
        f"registry {fmt.euro(ac['land_registry'])} · legal {fmt.euro(ac['legal'])} · "
        f"agent {fmt.euro(ac['agent'])}"
        + ("  _(private seller — no agent fee)_" if private else "")
    )


def _investor_metrics_block(d: dict) -> None:
    """The recognized metrics an investor scans for by name — cap rate, GRM, DSCR,
    break-even occupancy — on the same Greek cost model as the net yield above."""
    price = d.get("price")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not price or not monthly:
        return
    from scout import metrics as _m

    mm = _m.investor_metrics(
        price, monthly * 12, d.get("area_m2"), is_private_seller=bool(d.get("is_private_seller"))
    )
    v = mm["verdicts"]
    emoji = {"good": "🟢", "ok": "🟡", "weak": "🔴", None: "⚪"}

    def cell(label, val, key, fmt_s):
        shown = fmt_s.format(val) if val is not None else "—"
        return f"{emoji[v[key]]} **{label}:** {shown}"

    st.markdown("#### 📐 Investor metrics")
    c = st.columns(4)
    c[0].markdown(cell("Cap rate", mm["cap_rate"], "cap_rate", "{:.1%}"))
    c[1].markdown(cell("GRM", mm["grm"], "grm", "{:.0f}×"))
    c[2].markdown(cell("DSCR", mm["dscr"], "dscr", "{:.2f}"))
    c[3].markdown(
        cell("Break-even occ.", mm["break_even_occupancy"], "break_even_occupancy", "{:.0%}")
    )
    est = " Rent is estimated." if d.get("rent_estimated") else ""
    st.caption(
        "Athens-calibrated (cap rate ≥4.5%, GRM ≤22, DSCR ≥1.2, break-even ≤80% = good). We "
        "deliberately don't use US rules like the '1% rule' — at ~5% Athens yields they'd fail "
        "on every flat and tell you nothing." + est
    )


def _scorecard_block(d: dict) -> None:
    """Transparent Athens-calibrated deal scorecard — every check, its points, and why,
    so the grade isn't a black box."""
    sc = deal_scorecard.scorecard(d)
    if not sc.get("checks"):
        return
    color = {"Strong": "🟢", "Fair": "🟡", "Pass": "🔴"}
    st.markdown(f"#### 🧮 Deal scorecard — {color.get(sc['verdict'], '')} {sc['verdict']}")
    st.caption(f"{sc['points']}/{sc['max_points']} points ({sc['pct']:.0f}%). Athens-calibrated.")
    st.dataframe(
        pd.DataFrame(
            [
                {"Check": c["label"], "Pts": f"{c['points']}/{c['max_points']}", "Note": c["note"]}
                for c in sc["checks"]
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


def _projection_block(d: dict) -> None:
    """5-year total-return projection — the four pillars (cashflow, appreciation, debt
    paydown, equity). Appreciation is a labelled assumption, not a forecast."""
    price = d.get("price")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not price or not monthly:
        return
    pr = projection.five_year_projection(
        price, monthly * 12, d.get("area_m2"), is_private_seller=bool(d.get("is_private_seller"))
    )
    if not pr:
        return
    t = pr["total"]
    st.markdown("#### 📈 5-year projection")
    c = st.columns(4)
    c[0].metric("Cumulative cashflow", fmt.euro(t["cumulative_cash_flow"]))
    c[1].metric("Appreciation (2%/yr)", fmt.euro(t["property_appreciation"]))
    c[2].metric("Debt paydown", fmt.euro(t["debt_paydown"]))
    c[3].metric("Total return on cash", f"{t['total_return_pct'] * 100:.0f}%")
    st.caption(
        "The four pillars of return over a 5-yr hold (30% down, 25-yr @4.5%). Appreciation is "
        "a MODEST 2%/yr assumption, not a forecast — the market may do more or less."
    )


def _sensitivity_block(d: dict) -> None:
    """How the return holds up if rates rise or the flat sits empty — the stress test an
    investor actually underwrites on."""
    price = d.get("price")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not price or not monthly:
        return
    grid = sensitivity.sensitivity_grid(price, monthly * 12)
    if not grid.get("net_yield"):
        return
    st.markdown("#### 🎛️ Rate × vacancy sensitivity")
    rates = grid["rates"]
    vac = grid["vacancies"]
    ny = pd.DataFrame(
        grid["net_yield"],
        index=[f"{r * 100:.0f}% rate" for r in rates],
        columns=[f"{v * 100:.0f}% empty" for v in vac],
    )
    st.caption("Net yield (after vacancy, costs, mortgage interest) — 30% down, 25-yr term.")
    st.dataframe(ny.style.format("{:.1%}"), use_container_width=True)

    annual = monthly * 12
    with st.expander("More what-ifs — rent & purchase-price moves"):
        rs = sensitivity.rent_sensitivity(price, annual)
        if rs.get("net_yield"):
            rdf = pd.DataFrame(
                {
                    "Rent change": [f"{s * 100:+.0f}%" for s in rs["steps"]],
                    "Net yield": rs["net_yield"],
                    "Cashflow/mo": rs["cashflow_monthly"],
                }
            )
            st.markdown("**If rent moves**")
            st.dataframe(
                rdf.style.format({"Net yield": "{:.1%}", "Cashflow/mo": "€{:.0f}"}),
                use_container_width=True,
                hide_index=True,
            )
        ps = sensitivity.price_sensitivity(price, annual)
        if ps.get("net_yield"):
            pdf = pd.DataFrame(
                {
                    "Price change": [f"{s * 100:+.0f}%" for s in ps["steps"]],
                    "Net yield": ps["net_yield"],
                    "Cash-on-cash": ps["cash_on_cash"],
                }
            )
            st.markdown("**If you negotiate the price**")
            st.dataframe(
                pdf.style.format({"Net yield": "{:.1%}", "Cash-on-cash": "{:.1%}"}),
                use_container_width=True,
                hide_index=True,
            )
    if d.get("rent_estimated"):
        st.caption("_Rent is estimated (no local comp) — treat these as indicative._")


# ---- pages -----------------------------------------------------------------


def _coverage_panel(listings: list[dict]) -> None:
    """Honest per-region coverage: how many listings, how complete, how fresh. Trust comes
    from showing exactly what we have and what's still shallow, not hiding the gaps."""
    from collections import defaultdict

    if not listings:
        return
    by_region: dict[str, list[dict]] = defaultdict(list)
    for d in listings:
        by_region[d.get("region") or "—"].append(d)
    total = len(listings)
    complete = sum(1 for d in listings if d.get("data_complete"))
    with st.expander(
        (
            f"📦 Coverage — {total:,} listings, {complete / total * 100:.0f}% fully-detailed"
            if total
            else "📦 Coverage"
        ),
        expanded=False,
    ):
        rows = []
        for region, ds in sorted(by_region.items(), key=lambda kv: -len(kv[1])):
            n = len(ds)
            comp = sum(1 for d in ds if d.get("data_complete"))
            en = sum(1 for d in ds if (d.get("energy_class") or "").strip())
            exact = sum(1 for d in ds if d.get("location_precision") == "exact")
            newest = max((d["last_seen"] for d in ds if d.get("last_seen")), default=None)
            rows.append(
                {
                    "Region": region,
                    "Listings": n,
                    "Fully detailed": f"{comp / n * 100:.0f}%" if n else "—",
                    "Has energy": f"{en / n * 100:.0f}%" if n else "—",
                    "Exact location": f"{exact / n * 100:.0f}%" if n else "—",
                    "Last updated": newest.strftime("%Y-%m-%d %H:%M") if newest else "—",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(
            "Depth is recovered continuously by the detail-enrichment pass; card-only "
            "listings carry a *limited data* badge until then."
        )


def page_opportunities(listings: list[dict]) -> None:
    st.subheader("Opportunities")
    _valuation_banner()
    _coverage_panel(_eligible(listings))

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
        # Keep the everyday filters visible; tuck the rest into an expander so the sidebar
        # isn't a wall of ~15 controls (the #1 "hard to use" complaint).
        present_regions = [r for r in REGIONS if any(d.get("region") == r for d in eligible)]
        chosen_regions = (
            st.multiselect("Region", present_regions, default=present_regions)
            if present_regions
            else []
        )
        prices = [d["price"] for d in eligible]
        pmin, pmax = min(prices), max(prices)
        price_range = (
            st.slider("Price (€)", pmin, pmax, (pmin, pmax), step=5000)
            if pmin < pmax
            else (pmin, pmax)
        )
        min_vs_market = st.slider(
            "Only good value — cheaper than …% of similar",
            0,
            95,
            0,
            step=5,
            help="Market-position rank vs comparable active listings (same area, ±30% size). "
            "0 = show all. An honest relative-value screen — no sold-price data needed.",
        )
        short_let_filter = st.selectbox(
            "🏠 Short-let (Airbnb)",
            ["Any", "Short-let allowed", "Frozen (long-let only)"],
            index=0,
            help="Frozen = a buyer cannot get a new Airbnb licence (2026 Athens district freeze).",
        )

        with st.expander("⚙️ More filters"):
            near_metro_only = st.checkbox(
                "🚇 Near a metro station only",
                value=False,
                help="Keep only listings within the metro distance below (Line 2/3).",
            )
            income = st.number_input(
                "Your monthly net income (€) — 0 = off",
                min_value=0,
                value=0,
                step=100,
                help="Filters to homes a 25-yr mortgage at ~30% down supports on this income.",
            )
            max_afford = _max_affordable_price(income)
            if max_afford:
                st.caption(
                    f"≈ affordable up to **{fmt.euro(max_afford)}** (35% of income, ~4.5%, 25 yr)."
                )
            present_strats = sorted({t for d in eligible for t in (d.get("strategy_tags") or [])})
            strat_filter = (
                st.multiselect(
                    "Strategy",
                    present_strats,
                    default=[],
                    help="Cashflow · Value-add · Underpriced · Motivated seller · Prime location",
                )
                if present_strats
                else []
            )
            subsidy_only = st.checkbox(
                "🔧 Energy-subsidy candidates only",
                value=False,
                help="EPC class C or lower — eligible for the Exoikonomo 2026 renovation subsidy.",
            )
            areas = [d["area_m2"] for d in eligible]
            amin, amax = int(min(areas)), int(max(areas)) + 1
            area_range = (
                st.slider("Area (m²)", amin, amax, (amin, amax)) if amin < amax else (amin, amax)
            )
            min_yield = st.slider("Min gross yield (%)", 0.0, 12.0, 0.0, step=0.5) / 100
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
        if max_afford is not None and d["price"] > max_afford:
            return False
        if strat_filter and not (set(strat_filter) & set(d.get("strategy_tags") or [])):
            return False
        if short_let_filter != "Any":
            status = str_legality(_area_key(d)).status
            if short_let_filter == "Short-let allowed" and status == "FROZEN":
                return False
            if short_let_filter == "Frozen (long-let only)" and status != "FROZEN":
                return False
        if (
            subsidy_only
            and not renovation_subsidy(d.get("energy_class"), d.get("year_built")).candidate
        ):
            return False
        if not (area_range[0] <= d["area_m2"] <= area_range[1]):
            return False
        if (d["gross_yield"] or 0) < min_yield:
            return False
        if min_vs_market > 0:
            vp = d.get("value_percentile")
            if vp is None or vp * 100 < min_vs_market:
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

    # Let the buyer rank by the signal they care about — not just the quality score. All
    # of these are real numbers already in the data. Every sort puts BUY verdicts ahead of
    # WATCH ahead of PASS first: a verified BUY at score 70 beats an unverifiable WATCH at
    # 75 — the verdict already encodes how much of that score we can stand behind.
    _verdict_rank = {"BUY": 2, "WATCH": 1, "PASS": 0}
    sort_opts = {
        "Best overall (score)": lambda d: (d["score"], d.get("data_complete", False)),
        "Cheapest vs comparable listings": lambda d: (d.get("value_percentile") or -1),
        "Most negotiable (days on market)": lambda d: (d.get("days_on_market") or 0),
        "Highest net yield": lambda d: (d.get("net_yield") or -1),
    }
    scol, fcol = st.columns([4, 1])
    with scol:
        sort_by = st.radio(
            "Sort by", list(sort_opts), horizontal=True, label_visibility="collapsed"
        )
    with fcol:
        buys_only = st.checkbox("🟢 BUYs only", value=False, help="Verified BUY verdicts only")
    inner = sort_opts[sort_by]
    rows = sorted(
        [d for d in eligible if keep(d) and (not buys_only or d.get("rec_verdict") == "BUY")],
        # Data-quality suspects (whole building priced as a flat, future year, off-by-10x
        # €/m²) sink below every clean listing regardless of score — they can't top the rank.
        key=lambda d: (
            not d.get("is_suspect"),
            _verdict_rank.get(d.get("rec_verdict"), 0),
            inner(d),
        ),
        reverse=True,
    )

    n_buys = sum(1 for d in rows if d.get("rec_verdict") == "BUY")
    st.markdown(
        f"**{len(rows)}** listings match your filters (of {len(eligible)} tracked) · "
        f"**{n_buys}** on the BUY shortlist"
    )
    if rows:
        # Cap the card grid to the top N by score — rendering all ~9k cards ships a
        # multi-megabyte DOM that janks the browser. The full set stays in the table/CSV.
        grid_cap = 60
        components.listing_grid(rows[:grid_cap])
        if len(rows) > grid_cap:
            st.caption(
                f"Showing the top {grid_cap} cards ({sort_by.split(' (')[0].lower()}). "
                "Full list in the table below."
            )
        with st.expander("Table view (sort / export)"):
            _table(rows)
    else:
        st.info("No listings match the current filters. Widen them in the sidebar.")


def page_today(listings: list[dict]) -> None:
    st.subheader("🗞️ Daily brief")
    elig = _eligible(listings)
    cap = 30

    new = sorted([d for d in elig if d["is_new"]], key=lambda d: d["score"], reverse=True)
    new_buys = [d for d in new if d.get("rec_verdict") == "BUY"]
    try:
        drops = get_recent_price_drops(24)
    except Exception:
        drops = []

    # Counts strip — the "what changed since yesterday" a subscriber opens the tool for.
    c = st.columns(3)
    c[0].metric("🟢 New BUYs (24 h)", len(new_buys))
    c[1].metric("💸 Price drops (24 h)", len(drops))
    c[2].metric("🆕 New listings (24 h)", len(new))
    # Honest framing when the 24h feed is empty: the change-signals (new listings, price
    # drops, motivated sellers) are BUILT by comparing daily snapshots — they only appear
    # once the pipeline has run on consecutive days. Show that instead of three bare zeros
    # that read as "broken". The always-useful briefs below still make the page actionable.
    if not new_buys and not drops and not new:
        st.info(
            "No 24-hour changes to show yet. The daily-change feed (new listings, price "
            "drops, motivated sellers) is built by comparing snapshots across days and fills "
            "in as the pipeline runs — the price-history depth grows every day. Meanwhile the "
            "**best current opportunities** are below."
        )
    st.divider()

    # Lead with the actual decisions: BUY-verdict listings that appeared today. This is the
    # feed a paying user wants — not "here's everything new", but "here's what to act on".
    if new_buys:
        st.markdown("#### 🟢 New BUY signals today")
        components.listing_grid(new_buys[:cap])
        st.divider()

    # Price cuts today — the classic motivated-seller trigger, straight from price history.
    if drops:
        st.markdown("#### 💸 Price drops in the last 24 h")
        for d in drops:
            # Surface the cut as a lead strategy pill (the recommendation line owns the
            # thesis slot, so a deal_thesis here would never render). €old→€new is the
            # actionable bit — a fresh cut is the classic motivated-seller trigger.
            pill = f"💸 −{d['drop_pct'] * 100:.0f}% today (€{d['new_price']:,.0f})"
            d["strategy_tags"] = [pill, *(d.get("strategy_tags") or [])]
        components.listing_grid(sorted(drops, key=lambda d: d["drop_pct"], reverse=True)[:cap])
        st.divider()

    if new and not new_buys:
        st.markdown(f"#### 🆕 {len(new)} new in the last 24 h (none cleared the BUY bar)")
        components.listing_grid(new[:cap])
        st.divider()

    # Always-useful daily brief from the real signals: the best value, the most negotiable,
    # and the highest yield right now — so the landing view is actionable even between runs.
    briefs = [
        (
            "💰 Cheapest vs comparable listings",
            lambda d: d.get("value_percentile") or -1,
            lambda d: (d.get("value_percentile") or 0) >= 0.90,
        ),
        (
            "⏳ Most negotiable (longest on market)",
            lambda d: d.get("days_on_market") or 0,
            lambda d: (d.get("days_on_market") or 0) > 90,
        ),
        (
            "📈 Highest net yield",
            lambda d: d.get("net_yield") or -1,
            lambda d: d.get("net_yield") is not None,
        ),
    ]
    for title, keyfn, pred in briefs:
        picks = sorted([d for d in elig if pred(d)], key=keyfn, reverse=True)[:4]
        if picks:
            st.markdown(f"#### {title}")
            components.listing_grid(picks)
    if not new and not drops and not any(any(pred(d) for d in elig) for _, _, pred in briefs):
        st.info("No listings yet — run the pipeline from the sidebar.")


def _rank_color(t: float) -> list[int]:
    """Red → amber → green for a rank fraction t∈[0,1]. Colours by RELATIVE rank, not the
    absolute score: the market's absolute scores are low (data is thin), so an absolute
    red→green scale paints almost everything red and hides where the best options are.
    Rank-colouring makes the map a useful heatmap of relatively-better listings."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        u = t / 0.5
        return [220, int(70 + 120 * u), 60]  # (220,70,60) red → (220,190,60) amber
    u = (t - 0.5) / 0.5
    return [int(220 - 170 * u), int(190 - 10 * u), int(60 + 20 * u)]  # amber → (50,180,80) green


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

    # Split exact vs approx (centroid) points: an approx point is one shared location for a
    # whole municipality, so plotting it as a precise pin would imply an accuracy we don't
    # have. Exact points render solid & small; approx render large, faint and hollow — read
    # as an area blob, not an address.
    exact = [d for d in pts if d.get("location_precision") == "exact"]
    approx = [d for d in pts if d.get("location_precision") != "exact"]
    exact_df = pd.DataFrame({"lat": d["lat"], "lon": d["lng"], "score": d["score"]} for d in exact)
    if not exact_df.empty:
        # Colour by rank within the plotted set (greener = better than most in view), so the
        # map surfaces the relatively-best options instead of a sea of red on low absolutes.
        ranks = exact_df["score"].fillna(0).rank(pct=True, method="average")
        exact_df["fill"] = [_rank_color(t) for t in ranks]
    approx_df = pd.DataFrame(
        {"lat": d["lat"], "lon": d["lng"], "score": d["score"]} for d in approx
    )
    center = exact_df if not exact_df.empty else approx_df
    metro_df = pd.DataFrame(
        {"lat": lat, "lon": lng, "name": n} for n, (lat, lng) in METRO_STATIONS.items()
    )
    try:
        import pydeck as pdk

        layers = []
        if not approx_df.empty:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=approx_df,
                    get_position="[lon, lat]",
                    get_fill_color="[150, 150, 160, 40]",  # faint = approximate area location
                    get_radius=300,
                )
            )
        if not exact_df.empty:
            layers.append(
                pdk.Layer(
                    "ScatterplotLayer",
                    data=exact_df,
                    get_position="[lon, lat]",
                    get_fill_color="fill",
                    get_radius=60,
                    pickable=True,
                )
            )
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=metro_df,
                get_position="[lon, lat]",
                get_fill_color="[30, 90, 255]",
                get_radius=90,
            )
        )
        st.pydeck_chart(
            pdk.Deck(
                map_style="light",  # token-free Carto basemap so pins sit on real streets
                initial_view_state=pdk.ViewState(
                    latitude=center["lat"].mean(), longitude=center["lon"].mean(), zoom=13
                ),
                layers=layers,
                tooltip={"text": "Score: {score}"},
            )
        )
        st.caption(
            f"Solid pins ({len(exact)}) = exact location, coloured by **relative rank** "
            "(greener = scores better than most listings in view). "
            f"Faint blobs ({len(approx)}) = approximate (area centroid — not enriched yet). "
            "Blue = metro stations."
        )
    except Exception:
        st.map(center)


@st.cache_data(ttl=300)
def get_area_liquidity() -> dict:
    """Per-area liquidity (median days-on-market before delisting + absorption) over the
    full tracked set — the exit signal. Plain dicts so Streamlit can cache it."""
    allrows = queries.load_listings(include_excluded=True, only_active=False)
    out = {}
    for area, liq in liquidity.liquidity_by_area(allrows).items():
        out[area] = {
            "median_days": liq.median_days_on_market,
            "cleared": liq.cleared,
            "absorption": liq.absorption_rate,
        }
    return out


def _scenarios_block(d: dict) -> None:
    """Downside range + the questions a buyer underwrites on: net-yield under good/bad
    assumptions, yield if they land the recommended offer, break-even rent, and payback."""
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not monthly:
        return
    annual = monthly * 12
    price, area, priv = d["price"], d.get("area_m2"), bool(d.get("is_private_seller"))
    st.markdown("#### 📉 Downside & scenarios")
    sens = investment.net_yield_sensitivity(price, annual, area, priv)
    if sens:
        c = st.columns(3)
        c[0].metric(
            "Net yield — pessimistic",
            fmt.pct(sens["pessimistic"]),
            help="12% vacancy + higher maintenance",
        )
        c[1].metric("Net yield — base", fmt.pct(sens["base"]))
        c[2].metric(
            "Net yield — optimistic",
            fmt.pct(sens["optimistic"]),
            help="2% vacancy + light maintenance",
        )
    c2 = st.columns(3)
    yoo = d.get("yield_on_offer")
    if yoo is not None:
        c2[0].metric(
            "Net yield at suggested offer",
            fmt.pct(yoo),
            help=f"if you land it at {fmt.euro(d.get('suggested_offer'))}",
        )
    be = investment.break_even_rent(price, area, priv)
    if be:
        c2[1].metric(
            "Break-even rent",
            fmt.euro(be) + "/mo",
            help="rent below which it bleeds cash before financing",
        )
    pb = investment.payback_years(price, annual, area, priv)
    if pb:
        c2[2].metric("Payback (unlevered)", f"~{pb:.0f} yrs")
    tax = investment.greek_rental_tax(annual)
    if tax:
        st.caption(
            f"🧾 Greek rental-income tax ≈ **{fmt.euro(tax['annual_tax'])}/yr** "
            f"({tax['effective_rate'] * 100:.0f}% effective) — inside the net figures above."
        )
    reno = investment.renovation_roi(d.get("energy_class"), area, annual)
    if reno:
        st.caption(
            f"🔧 Retrofit case: ~{fmt.euro(reno['capex'])} capex → "
            f"+{fmt.euro(reno['annual_rent_uplift'])}/yr rent "
            f"({reno['roi_pct'] * 100:.0f}% ROI, ~{reno['payback_years']:.0f}yr payback)."
        )
    if d.get("rent_estimated"):
        st.caption(
            "_Rent is an area estimate — treat these as indicative until a real comp lands._"
        )


def _risk_and_context(d: dict, listings: list[dict]) -> None:
    """EPBD renovation liability, transparent price percentile, area liquidity, and a
    leverage one-liner — the decision context portals don't give."""
    st.markdown("#### 🧭 Risk & context")

    # EPBD renovation-mandate liability + indicative capex (only for a known poor class).
    flag = epbd.epbd_flag(d.get("energy_class"), d.get("area_m2"))
    if flag.at_risk:
        st.warning(f"⚠️ **EPBD liability** — {flag.note}")

    cols = st.columns(2)
    # Transparent, checkable value signal: cheaper per m² than X% of this municipality.
    dist = analytics.area_ppm2_distributions(listings)
    pct = analytics.ppm2_percentile_cheaper(
        d.get("price_per_m2"), dist.get(d.get("search_area"), [])
    )
    if pct is not None:
        cols[0].metric(
            "Cheaper per m² than",
            f"{pct * 100:.0f}% of {d.get('search_area') or 'area'}",
            help="Share of active listings in this municipality with a higher €/m².",
        )

    # Area liquidity — how fast this submarket clears (from our own tracked lifecycle).
    liq = get_area_liquidity().get(d.get("search_area"))
    if liq and liq["median_days"] is not None:
        cols[1].metric(
            "Typical days on market",
            f"~{liq['median_days']:.0f}",
            help=(
                f"Median dwell before delisting in {d.get('search_area')} "
                f"({liq['cleared']} tracked; absorption {(liq['absorption'] or 0) * 100:.0f}%). "
                "Delisting is a proxy for sold."
            ),
        )

    # Leverage: cash-on-cash at standard assumptions (a buyer tweaks them per deal).
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if monthly:
        line = finance.leverage_oneliner(
            d["price"], monthly * 12, d.get("area_m2"), bool(d.get("is_private_seller"))
        )
        if line:
            est = " _(rent est.)_" if d.get("rent_estimated") else ""
            st.caption(f"🏦 {line}{est}")


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

    if d["excluded"]:
        st.error(f"Excluded by hard filter: {d['exclusion_reason']}")

    # Verdict up front — the answer before any deep dive.
    sc = deal_scorecard.scorecard(d)
    vic = {"Strong": "🟢", "Fair": "🟡", "Pass": "🔴"}
    vc = st.columns(4)
    vc[0].metric("Deal grade", d.get("deal_grade") or "—")
    vc[1].metric("Scorecard", f"{vic.get(sc['verdict'], '')} {sc['verdict']}")
    vc[2].metric("Net yield", fmt.pct(d["net_yield"]) if d.get("net_yield") is not None else "—")
    # Honest headline value signal: market-position rank among comparable ACTIVE listings
    # (no sold-price data, no pseudo-precise ±44% "discount"). The hedonic model gap is kept
    # below as a secondary, clearly-labelled estimate.
    rv = relative_value(d)
    vc[3].metric(
        "vs market",
        f"cheaper than {rv.percentile * 100:.0f}%" if rv else "—",
        help="Share of comparable active listings (same area, ±30% size) priced higher per m².",
    )
    if d.get("strategy_tags"):
        st.write(" ".join(f"`{t}`" for t in d["strategy_tags"]))
    # The recommendation — the decision, up front: verdict + concrete action + why + risks.
    from scout.recommendation import verdict_emoji

    rv, rh = d.get("rec_verdict"), d.get("rec_headline")
    if rv and rh:
        box = {"BUY": st.success, "WATCH": st.info, "PASS": st.error}.get(rv, st.info)
        box(f"{verdict_emoji(rv)} **{rv} — {rh}**")
        rc = st.columns(2)
        if d.get("rec_rationale"):
            rc[0].markdown("**Why:**\n" + "\n".join(f"- {x}" for x in d["rec_rationale"]))
        if d.get("rec_risks"):
            rc[1].markdown("**Watch out:**\n" + "\n".join(f"- {x}" for x in d["rec_risks"]))
    elif d.get("deal_thesis"):
        st.info(f"💡 {d['deal_thesis']}")

    _regulatory_panel(d)

    tabs = st.tabs(
        ["💰 Returns", "🧾 Costs & risk", "🎛️ Sensitivity", "🧮 Score & comps", "🏗️ Details"]
    )

    with tabs[0]:
        monthly = d.get("listed_rent") or d.get("est_monthly_rent")
        if monthly:
            math_cols = st.columns(4)
            math_cols[0].metric("Est. monthly rent", fmt.euro(monthly))
            math_cols[1].metric("Annual income", fmt.euro(monthly * 12))
            math_cols[2].metric("Purchase price", fmt.euro(d["price"]))
            math_cols[3].metric("Gross yield", fmt.pct(d.get("gross_yield")))
            if fp and d["price"] < fp:
                drop_pct = (fp - d["price"]) / fp * 100
                st.info(
                    f"📉 Price dropped **{drop_pct:.0f}%** from {fmt.euro(fp)} to "
                    f"{fmt.euro(d['price'])} (saved {fmt.euro(fp - d['price'])})"
                )
        else:
            st.caption("_No rent scraped — yield uses the strategy fallback €/m²/month._")
        for b in _investment_bullets(d):
            st.markdown(f"• {b}")
        _fair_value_block(d)
        _net_return_and_financing(d, lid)
        _investor_metrics_block(d)
        _projection_block(d)

    with tabs[1]:
        _acquisition_block(d)
        _risk_and_context(d, listings)
        _scenarios_block(d)

    with tabs[2]:
        _sensitivity_block(d)

    with tabs[3]:
        _scorecard_block(d)
        st.markdown("#### 📊 Score breakdown")
        _score_breakdown(d, get_strategy())
        st.markdown("#### 🔁 Comparable active listings nearby")
        _comparables(d, listings)

    with tabs[4]:
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
        st.markdown("#### 📈 Price history")
        history = get_history(lid)
        if len(history) >= 2:
            hist_df = pd.DataFrame(history, columns=["observed_at", "price"]).set_index(
                "observed_at"
            )
            st.line_chart(hist_df)
        elif len(history) == 1:
            st.caption(
                f"First recorded price: {fmt.euro(history[0][1])} on {history[0][0]:%Y-%m-%d}. "
                "Price history builds up over multiple pipeline runs."
            )
        else:
            st.caption("No price history yet — accumulates over daily runs.")

    st.divider()
    lb, db = st.columns(2)
    with lb:
        st.link_button("Open on portal ↗", d["url"], use_container_width=True)
    with db:
        st.download_button(
            "⬇ One-page report (HTML)",
            listing_report.build_report_html(d),
            file_name=f"holargos-{lid}.html",
            mime="text/html",
            use_container_width=True,
            help="A printable one-pager to hand a client — the agent deliverable.",
        )
    watched = st.checkbox("On watchlist", value=d["is_watched"], key=f"watch-{lid}")
    if watched != d["is_watched"]:
        queries.set_watched(lid, watched)
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()


def page_watchlist(listings: list[dict]) -> None:
    st.subheader("⭐ Watchlist")
    watched = [d for d in listings if d["is_watched"]]
    if not watched:
        st.info("Pin listings from the **Listing detail** page to watch them here.")
        return

    # Portfolio summary across the shortlist — the "if I bought all of these" snapshot.
    prices = [d["price"] for d in watched if d.get("price")]
    nys = [d["net_yield"] for d in watched if d.get("net_yield") is not None]
    doms = [d["days_on_market"] for d in watched if d.get("days_on_market") is not None]
    c = st.columns(4)
    c[0].metric("Watched", len(watched))
    c[1].metric("Total asking", fmt.euro(sum(prices)) if prices else "—")
    c[2].metric("Median net yield", fmt.pct(statistics.median(nys)) if nys else "—")
    c[3].metric("Median days on market", f"{int(statistics.median(doms))}d" if doms else "—")

    for d in watched:
        if d["price_dropped"]:
            st.success(
                f"📉 {d['title']} dropped to {fmt.euro(d['price'])} "
                f"(from {fmt.euro(d['first_price'])})"
            )

    components.listing_grid(sorted(watched, key=lambda d: d["score"], reverse=True))
    with st.expander("Table view (sort / export)"):
        _table(sorted(watched, key=lambda d: d["score"], reverse=True))


def page_strategy() -> None:
    st.subheader("Strategy")
    st.caption("Edit the investor's rules & weights, then re-score live — no redeploy.")
    strategy = load_strategy()

    with st.form("strategy"):
        st.markdown("**Hard filters**")
        min_floor = st.number_input("Min floor", value=strategy.hard_filters.min_floor, step=1)
        max_metro = st.number_input(
            "Metro distance for the 'near metro' filter (m)",
            value=strategy.hard_filters.max_metro_distance_m,
            step=50,
            help="Not a hard cutoff — metro proximity is a scoring signal. This only sets the "
            "threshold for the optional 'Near metro only' toggle on Opportunities.",
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
        st.cache_resource.clear()
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

    # Data-quality audit panel — the same numbers the improvement loop optimises, so the
    # depth of the dataset is visible, not hidden.
    st.markdown("**Data-quality audit**")
    try:
        from scout.data_quality import audit as _audit

        a = _audit()
        ac = st.columns(4)
        ac[0].metric("Fully detailed", f"{a.get('complete_pct', 0) * 100:.0f}%")
        ac[1].metric("Top-100 complete", f"{a.get('top100_complete', 0)}%")
        ac[2].metric("Biggest gap", str(a.get("top_gap", "—")))
        ac[3].metric("Eligible", a.get("total", len(active)))
        fields = a.get("fields") or {}
        if fields:

            def _fld(k: str, v: float) -> str:
                # "real_rent" is the share with the listing's OWN scraped rent; the rest use an
                # area-comp ESTIMATE. Show it to 0.1% (a ~0.3% share must not read as "0%") and
                # spell out the estimated majority so the yield isn't mistaken for measured.
                if k == "real_rent":
                    return f"real rent (own): {v * 100:.1f}% · {(1 - v) * 100:.0f}% estimated (area comp)"
                return f"{k}: {v * 100:.0f}%"

            st.caption(" · ".join(_fld(k, v) for k, v in fields.items()))
    except Exception as exc:  # never break the debug page on an audit hiccup
        st.caption(f"_audit unavailable: {exc}_")

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
            "Median price": fmt.euro(s["median_price"]),
            "Median €/m²": fmt.euro_per_m2(s["median_ppm2"]),
            "Median gross yield": (
                f"{s['median_yield_pct']:.1f}%" if s["median_yield_pct"] is not None else "—"
            ),
            "Opportunities": s["opportunities"],
            "Sitting >180d": s["long_sitting"],
            "Below model": s["below_model"],
            "Rented": s["rented"],
        }
        for s in stats
    ]
    st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)

    # Rental market by area — REAL asked rents (scraped rental listings), joined with the
    # sale market to show where yield is structurally high vs low. This is the aggregation
    # a free portal never gives: the rent gradient (e.g. Vouliagmeni ~€22/m² vs Kamatero
    # ~€8/m²) next to what flats cost to buy there.
    try:
        import statistics as _stats

        from scout.rent_comps import OVERALL_KEY, load_rent_comps

        comps = load_rent_comps()
        sale_by_area: dict[str, list[float]] = {}
        for d in _eligible(listings):
            if d.get("price_per_m2") and d.get("search_area"):
                sale_by_area.setdefault(d["search_area"], []).append(d["price_per_m2"])
        rent_rows = []
        for area, per_hood in sorted(comps.items()):
            rent = per_hood.get(OVERALL_KEY)
            sales = sale_by_area.get(area) or []
            if not rent or len(sales) < 5:
                continue
            sale_med = _stats.median(sales)
            rent_rows.append(
                {
                    "Area": area,
                    "Median rent (€/m²/mo)": round(rent, 1),
                    "Median sale (€/m²)": int(sale_med),
                    "Implied gross yield": f"{rent * 12 / sale_med * 100:.1f}%",
                }
            )
        if rent_rows:
            st.markdown("#### 🏠 Rental market by area — real asked rents")
            rent_rows.sort(key=lambda r: -float(r["Implied gross yield"].rstrip("%")))
            st.dataframe(pd.DataFrame(rent_rows), use_container_width=True, hide_index=True)
            st.caption(
                "Median asked rent from scraped rental listings ÷ median sale €/m² = the "
                "area's structural gross yield — where rental demand outruns prices."
            )
    except Exception:  # rent table must never break the page
        pass
    st.caption(
        "**Sitting >180d** = motivated-seller supply · **Below model** = flats priced under "
        "fair value (beyond the model's ±band) — where to hunt for deals in each area."
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
    from scout import metrics as _m

    w = csv.writer(buf)
    w.writerow(
        [
            "negotiation_score",
            "deal_grade",
            "price_eur",
            "suggested_offer_eur",
            "area_m2",
            "eur_per_m2",
            "neighborhood",
            "region",
            "days_on_market",
            "price_cut_pct",
            "below_model_pct",
            "net_yield_pct",
            "cap_rate_pct",
            "energy_class",
            "private_seller",
            "strategy_tags",
            "url",
        ]
    )
    for d in ranked:
        dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
        fp, cp = d.get("first_price"), d.get("price", 0)
        cut = (fp - cp) / fp if (fp and cp < fp) else 0.0
        monthly = d.get("listed_rent") or d.get("est_monthly_rent")
        cap = _m.cap_rate(d["price"], monthly * 12, d.get("area_m2")) if monthly else None
        gap = d.get("value_gap_pct")
        ny = d.get("net_yield")
        w.writerow(
            [
                round(d.get("negotiation_score") or 0, 1),
                d.get("deal_grade") or "",
                d["price"],
                d.get("suggested_offer") or "",
                f"{d['area_m2']:.0f}",
                f"{d['price_per_m2']:.0f}" if d.get("price_per_m2") else "",
                d.get("neighborhood") or "",
                d.get("region") or "",
                dom if dom is not None else "",
                f"{cut * 100:.0f}%",
                f"{gap * 100:.0f}%" if gap is not None else "",
                f"{ny * 100:.1f}%" if ny is not None else "",
                f"{cap * 100:.1f}%" if cap is not None else "",
                d.get("energy_class") or "",
                "yes" if d.get("is_private_seller") else "no",
                " | ".join(d.get("strategy_tags") or []),
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
    components.listing_grid(ranked[:60], metric="negotiation_score")


def page_saved_searches(listings: list[dict]) -> None:
    """Saved searches — the recurring investor mandate. Create one, see live matches, and
    (with an alert sink configured) get only these delivered daily. The €19/mo core loop."""
    from scout import saved_search as ss

    st.subheader("🔔 Saved searches")
    st.caption(
        "Define your mandate once — region, budget, min net yield, min deal grade. The daily "
        "digest then delivers only what matches, before you'd find it yourself."
    )
    eligible = _eligible(listings)

    with st.form("new_saved_search"):
        name = st.text_input("Name", placeholder="e.g. Centre ≤€200k, ≥4% net")
        regions = st.multiselect("Regions", list(REGIONS.keys()))
        c = st.columns(3)
        max_price = c[0].number_input("Max price (€)", 0, 2_000_000, 250_000, step=10_000)
        min_ny = c[1].slider("Min net yield (%)", 0.0, 8.0, 3.0, step=0.5) / 100
        min_grade = c[2].selectbox("Min grade", ["", "A", "B", "C"], index=0)
        if st.form_submit_button("💾 Save search") and name:
            ss.create_saved_search(
                ss.SavedSearch(
                    id=None,
                    name=name,
                    regions=regions,
                    max_price=int(max_price) or None,
                    min_net_yield=min_ny or None,
                    min_grade=min_grade or None,
                )
            )
            st.success(f"Saved '{name}'. It will appear below.")
            st.rerun()

    searches = ss.list_saved_searches()
    if not searches:
        st.info("No saved searches yet — create one above.")
        return
    for s in searches:
        matched = ss.matching_listings(s, eligible)
        new = [d for d in matched if d.get("is_new")]
        with st.expander(
            f"**{s.name}** — {len(matched)} matches · {len(new)} new today", expanded=False
        ):
            bits = []
            if s.regions:
                bits.append("/".join(s.regions))
            if s.max_price:
                bits.append(f"≤{fmt.euro(s.max_price)}")
            if s.min_net_yield:
                bits.append(f"≥{s.min_net_yield * 100:.1f}% net")
            if s.min_grade:
                bits.append(f"≥grade {s.min_grade}")
            st.caption(" · ".join(bits) or "no filters")
            if matched:
                components.listing_grid(matched[:12])
            if st.button("🗑 Delete", key=f"del-{s.id}"):
                ss.delete_saved_search(s.id)
                st.rerun()


def page_compare(listings: list[dict]) -> None:
    """Shortlist several flats and rank them side-by-side on the numbers that decide it —
    the "which of these do I chase?" view (inspired by deal-analyzer compare tools)."""
    from scout import metrics as _m

    st.subheader("⚖️ Compare")
    st.caption("Pick 2–4 listings to line up their metrics side by side.")
    elig = _eligible(listings)
    if not elig:
        st.info("No listings to compare yet.")
        return
    opts = {
        f"[{d['score']:.0f}] {d.get('neighborhood') or d['source_id']} · {fmt.euro(d['price'])}": d[
            "id"
        ]
        for d in elig
    }
    picks = st.multiselect("Listings", list(opts.keys()), max_selections=4)
    chosen = [next(x for x in elig if x["id"] == opts[p]) for p in picks]
    if len(chosen) < 2:
        st.info("Select at least two listings.")
        return

    def _metrics(d: dict) -> dict:
        monthly = d.get("listed_rent") or d.get("est_monthly_rent")
        annual = monthly * 12 if monthly else None
        im = _m.investor_metrics(
            d["price"], annual, d.get("area_m2"), is_private_seller=bool(d.get("is_private_seller"))
        )
        return {
            "Score": f"{d['score']:.0f}",
            "Grade": d.get("deal_grade") or "—",
            "Price": fmt.euro(d["price"]),
            "€/m²": fmt.euro_per_m2(d.get("price_per_m2")),
            "Area": f"{d['area_m2']:.0f} m²" if d.get("area_m2") else "—",
            "Net yield": fmt.pct(d.get("net_yield")) if d.get("net_yield") is not None else "—",
            "Cap rate": f"{im['cap_rate']:.1%}" if im["cap_rate"] is not None else "—",
            "GRM": f"{im['grm']:.0f}×" if im["grm"] is not None else "—",
            "DSCR": f"{im['dscr']:.2f}" if im["dscr"] is not None else "—",
            "Days on market": (
                d.get("days_on_market") if d.get("days_on_market") is not None else "—"
            ),
            "To metro": _metro_label(d),
            "Energy": d.get("energy_class") or "—",
        }

    table = {}
    for d in chosen:
        label = f"{d.get('neighborhood') or d['source_id']}"
        table[label] = _metrics(d)
    st.dataframe(pd.DataFrame(table), use_container_width=True)
    st.caption("Higher score/net yield/cap rate & lower GRM/days-on-market is better.")


# Everyday pages first, secondary tools after — so the nav reads top-to-bottom by how
# often it's used, instead of an 11-item jumble.
PAGES = {
    "Opportunities": page_opportunities,
    "Today": page_today,
    "Map": page_map,
    "Neighborhoods": page_neighborhoods,
    "Listing detail": page_detail,
    "Deals": page_deals,
    "Compare": page_compare,
    "Watchlist": page_watchlist,
    "Saved searches": page_saved_searches,
}


def main() -> None:
    st.title("🏠 Holargos Property Scout")

    with st.sidebar:
        if st.button("🔄 Refresh now (run pipeline)", use_container_width=True):
            with st.spinner("Running pipeline…"):
                from scout.pipeline import run

                summary = run()
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success(f"Done: {summary}")
        page = st.radio("Page", [*PAGES.keys(), "Strategy", "Debug"])

    listings = get_listings()

    last_up = _last_updated(listings)
    if last_up is not None:
        # Honest source label: name the dominant source with its real share rather than
        # listing every source equally (99.7% XE + a handful of green-acres read as
        # "multi-source" when it isn't). Shows the true mix.
        counts: dict[str, int] = {}
        for d in listings:
            if d.get("source"):
                counts[d["source"]] = counts.get(d["source"], 0) + 1
        total = sum(counts.values())
        if counts:
            top, top_n = max(counts.items(), key=lambda kv: kv[1])
            share = top_n / total if total else 0
            src_label = (
                top.upper()
                if share >= 0.98
                else " + ".join(
                    f"{s.upper()} {n/total:.0%}"
                    for s, n in sorted(counts.items(), key=lambda kv: -kv[1])
                )
            )
        else:
            src_label = "—"
        st.caption(
            f"🕒 Data last updated **{last_up:%Y-%m-%d %H:%M} UTC** · "
            f"{len(listings)} active listings · source: {src_label}"
        )
        # Freshness doctor: the whole product's premise is a daily-refreshed feed. If the
        # pipeline hasn't run in days the "opportunities" are stale — say so loudly rather
        # than let a buyer act on old prices.
        stale_days = (datetime.utcnow() - last_up).days
        if stale_days >= 3:
            st.warning(
                f"⚠️ Data is **{stale_days} days old** — the daily pipeline may not be running. "
                "Prices, new listings and price-drops won't be current until it runs again "
                "(**Refresh now**, or check the scheduled job)."
            )
        if len(counts) <= 1 or (total and max(counts.values()) / total >= 0.98):
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
