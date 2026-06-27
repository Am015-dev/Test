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

from scout.config import Strategy, load_strategy, save_strategy  # noqa: E402
from scout.ui import format as fmt  # noqa: E402
from scout.ui import queries  # noqa: E402

st.set_page_config(page_title="Holargos Property Scout", page_icon="🏠", layout="wide")


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
            "Price": d["price"],
            "€/m²": d["price_per_m2"],
            "Area": d["area_m2"],
            "Floor": d["floor"],
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
        "Price": st.column_config.NumberColumn("Price", format="€%d"),
        "€/m²": st.column_config.NumberColumn("€/m²", format="€%.0f"),
        "Area": st.column_config.NumberColumn("Area", format="%.0f m²"),
        "Floor": st.column_config.NumberColumn("Floor", format="%.0f"),
        "Yield": st.column_config.NumberColumn("Yield", format="%.1f%%"),
        "Metro": st.column_config.NumberColumn("Metro", help="walk to Line 3", format="%d m"),
        "Link": st.column_config.LinkColumn("Link", display_text="open ↗"),
    }
    st.dataframe(df, use_container_width=True, hide_index=True, column_config=column_config)


def _top_picks(rows: list[dict]) -> None:
    """Three highlight cards for the best-scoring opportunities."""
    if not rows:
        return
    st.markdown("#### ⭐ Top picks")
    cols = st.columns(min(3, len(rows)))
    for col, d in zip(cols, rows[:3], strict=False):
        with col.container(border=True):
            # Header: price + neighborhood
            st.markdown(f"### {fmt.euro(d['price'])}")
            dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
            dom_str = (
                ("listed today" if dom == 0 else f"{dom}d on market") if dom is not None else ""
            )
            st.caption(
                f"{d['neighborhood'] or '—'} · {d['area_m2']:.0f} m² · "
                f"{fmt.euro_per_m2(d['price_per_m2'])} · floor {_floor_label(d['floor'])}"
                + (f" · {dom_str}" if dom_str else "")
            )

            # Score bar
            st.progress(min(max(int(d["score"]), 0), 100) / 100, text=f"Score {d['score']:.0f}/100")

            # Badges
            flags = " ".join(fmt.badges(d))
            if flags:
                st.write(flags)

            # Investment case — the WHY
            bullets = _investment_bullets(d)
            if bullets:
                for b in bullets[:3]:  # top 3 to keep card compact
                    st.markdown(f"• {b}")

            st.link_button("View listing ↗", d["url"], use_container_width=True)


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

    rows = [
        {
            "Signal": "Gross yield",
            "Value": f"{gy*100:.1f}%" if gy else "—",
            "Score": round(yield_sig * w.gross_yield / total_w * 100, 1),
            "Max": round(w.gross_yield / total_w * 100, 1),
        },
        {
            "Signal": "Price vs area median",
            "Value": "See score",
            "Score": "—",
            "Max": round(w.price_vs_area_median / total_w * 100, 1),
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
    st.caption(
        "Price vs area median is computed from all area listings — accurate once ≥ 3 "
        "comparables exist per neighborhood."
    )


# ---- pages -----------------------------------------------------------------


def page_opportunities(listings: list[dict]) -> None:
    st.subheader("Opportunities")

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
        max_metro = st.slider("Max metro distance (m)", 0, 2000, 2000, step=50)
        include_unknown_metro = st.checkbox("Include unknown metro distance", value=True)

    def keep(d: dict) -> bool:
        if not (price_range[0] <= d["price"] <= price_range[1]):
            return False
        if not (area_range[0] <= d["area_m2"] <= area_range[1]):
            return False
        if (d["gross_yield"] or 0) < min_yield:
            return False
        if d["metro_distance_m"] is None:
            return include_unknown_metro
        return d["metro_distance_m"] <= max_metro

    rows = sorted([d for d in eligible if keep(d)], key=lambda d: d["score"], reverse=True)

    _top_picks(rows)
    st.markdown(f"**{len(rows)}** opportunities match your filters (of {len(eligible)} eligible)")
    if rows:
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
    _top_picks(today)
    _table(today)


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

    # --- score breakdown ---
    strategy = get_strategy()
    st.markdown("#### 📊 Score breakdown")
    _score_breakdown(d, strategy)

    # --- property specs ---
    st.markdown("#### 🏗️ Property specs")
    spec_cols = st.columns(3)
    spec_cols[0].markdown(
        f"**Area:** {d['area_m2']:.0f} m²  \n"
        f"**Rooms:** {d['rooms'] or '—'}  \n"
        f"**Bedrooms:** {d['bedrooms'] or '—'}  \n"
        f"**Floor:** {_floor_label(d['floor'])}"
    )
    spec_cols[1].markdown(
        f"**Neighborhood:** {d['neighborhood'] or '—'}  \n"
        f"**Address:** {d['address'] or '—'}  \n"
        f"**Nearest metro:** {d.get('nearest_metro') or '—'}  \n"
        f"**Metro distance:** {_metro_label(d)}"
    )
    spec_cols[2].markdown(
        f"**Source:** {d['source']}  \n"
        f"**Private seller:** {'✅ yes' if d['is_private_seller'] else '✗ no'}  \n"
        f"**Currently rented:** {'✅ yes' if d['is_currently_rented'] else '✗ no'}  \n"
        f"**Listed rent:** {fmt.euro(d.get('listed_rent'))}"
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
        gy = st.slider("Gross yield", 0.0, 50.0, float(w.gross_yield))
        pm = st.slider("Price vs area median", 0.0, 50.0, float(w.price_vs_area_median))
        pd_ = st.slider("Price drop", 0.0, 50.0, float(w.price_drop))
        rented = st.slider("Currently rented", 0.0, 50.0, float(w.is_currently_rented))
        private = st.slider("Private seller", 0.0, 50.0, float(w.is_private_seller))
        submitted = st.form_submit_button("Save & re-score")

    if submitted:
        strategy.hard_filters.min_floor = int(min_floor)
        strategy.hard_filters.max_metro_distance_m = int(max_metro)
        strategy.weights.gross_yield = gy
        strategy.weights.price_vs_area_median = pm
        strategy.weights.price_drop = pd_
        strategy.weights.is_currently_rented = rented
        strategy.weights.is_private_seller = private
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


PAGES = {
    "Opportunities": page_opportunities,
    "Today": page_today,
    "Map": page_map,
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
        st.caption(
            f"🕒 Data last updated **{last_up:%Y-%m-%d %H:%M} UTC** · "
            f"{len(listings)} active listings"
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
