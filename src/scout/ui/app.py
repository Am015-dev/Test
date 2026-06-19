"""Streamlit app — reads the DB the pipeline populated and surfaces opportunities.

Pages: Today, All opportunities, Map, Listing detail, Watchlist, Strategy editor.
The app NEVER scrapes in the request cycle; scraping is the scheduled pipeline's
job. A "Refresh now" button runs the pipeline explicitly in the foreground.

Run:  streamlit run src/scout/ui/app.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Allow running via `streamlit run src/scout/ui/app.py` without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from scout.config import load_strategy, save_strategy  # noqa: E402
from scout.ui import format as fmt  # noqa: E402
from scout.ui import queries  # noqa: E402

st.set_page_config(page_title="Holargos Property Scout", page_icon="🏠", layout="wide")


@st.cache_data(ttl=300)
def get_listings() -> list[dict]:
    return queries.load_listings(include_excluded=True, only_active=True)


@st.cache_data(ttl=300)
def get_all_listings_debug() -> list[dict]:
    """Everything, including excluded and inactive (gone) listings — for the Debug page."""
    return queries.load_listings(include_excluded=True, only_active=False)


@st.cache_data(ttl=300)
def get_history(listing_id: int):
    return queries.load_price_history(listing_id)


def _last_updated(listings: list[dict]) -> datetime | None:
    """Most recent time any listing was seen by the pipeline."""
    seens = [d["last_seen"] for d in listings if d["last_seen"]]
    return max(seens) if seens else None


def _eligible(listings: list[dict]) -> list[dict]:
    """Listings that pass the hard filters (not excluded)."""
    return [d for d in listings if not d["excluded"]]


def _row_summary(d: dict) -> dict:
    return {
        "Score": round(d["score"], 1),
        "Badges": " ".join(fmt.badges(d)),
        "Price": fmt.euro(d["price"]),
        "€/m²": fmt.euro_per_m2(d["price_per_m2"]),
        "Area": f"{d['area_m2']:.0f} m²",
        "Floor": d["floor"],
        "Metro": f"{d['metro_distance_m']} m" if d["metro_distance_m"] is not None else "—",
        "Yield": fmt.pct(d["gross_yield"]),
        "Neighborhood": d["neighborhood"] or "—",
        "DOM": fmt.days_on_market(d["first_seen"], d["last_seen"]),
        "id": d["id"],
        "url": d["url"],
    }


def page_today(listings: list[dict]) -> None:
    st.header("Today")
    st.caption("New in the last 24 h that pass the hard filters, by score.")
    today = [d for d in _eligible(listings) if d["is_new"]]
    today.sort(key=lambda d: d["score"], reverse=True)
    if not today:
        st.info("Nothing new in the last 24 h. Check **All opportunities**.")
        return
    df = pd.DataFrame(_row_summary(d) for d in today)
    st.dataframe(df, use_container_width=True, hide_index=True)


def page_all(listings: list[dict]) -> None:
    st.header("All opportunities")
    eligible = _eligible(listings)
    if not eligible:
        st.info("No eligible listings yet. Run the pipeline or seed the DB.")
        return

    with st.sidebar:
        st.subheader("Filters")
        prices = [d["price"] for d in eligible]
        pmin, pmax = min(prices), max(prices)
        price_range = st.slider("Price (€)", pmin, pmax, (pmin, pmax), step=5000)
        areas = [d["area_m2"] for d in eligible]
        amin, amax = int(min(areas)), int(max(areas)) + 1
        area_range = st.slider("Area (m²)", amin, amax, (amin, amax))
        min_yield = st.slider("Min gross yield (%)", 0.0, 12.0, 0.0, step=0.5) / 100
        max_metro = st.slider("Max metro distance (m)", 0, 1500, 600, step=50)

    rows = [
        d
        for d in eligible
        if price_range[0] <= d["price"] <= price_range[1]
        and area_range[0] <= d["area_m2"] <= area_range[1]
        and (d["gross_yield"] or 0) >= min_yield
        and (d["metro_distance_m"] or 9999) <= max_metro
    ]
    rows.sort(key=lambda d: d["score"], reverse=True)
    st.write(f"**{len(rows)}** listings match.")
    df = pd.DataFrame(_row_summary(d) for d in rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={"url": st.column_config.LinkColumn("Link")},
    )


def page_map(listings: list[dict]) -> None:
    st.header("Map")
    pts = [d for d in _eligible(listings) if d["lat"] and d["lng"]]
    if not pts:
        st.info("No geocoded listings to map yet.")
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
    st.header("Listing detail")
    eligible = listings
    options = {f"[{d['score']:.0f}] {d['title'] or d['source_id']}": d["id"] for d in eligible}
    if not options:
        st.info("No listings.")
        return
    choice = st.selectbox("Listing", list(options.keys()))
    lid = options[choice]
    d = next(x for x in listings if x["id"] == lid)

    cols = st.columns(4)
    cols[0].metric(
        "Price",
        fmt.euro(d["price"]),
        delta=fmt.euro(d["price"] - d["first_price"]) if d["first_price"] else None,
    )
    cols[1].metric("€/m²", fmt.euro_per_m2(d["price_per_m2"]))
    cols[2].metric("Gross yield", fmt.pct(d["gross_yield"]))
    cols[3].metric("Days on market", fmt.days_on_market(d["first_seen"], d["last_seen"]))

    st.write(" ".join(fmt.badges(d)) or "_no badges_")
    if d["excluded"]:
        st.error(f"Excluded by hard filter: {d['exclusion_reason']}")

    st.subheader("Specs")
    st.json(
        {
            "neighborhood": d["neighborhood"],
            "area_m2": d["area_m2"],
            "rooms": d["rooms"],
            "bedrooms": d["bedrooms"],
            "floor": d["floor"],
            "nearest_metro": d["nearest_metro"],
            "metro_distance_m": d["metro_distance_m"],
            "is_private_seller": d["is_private_seller"],
            "is_currently_rented": d["is_currently_rented"],
            "listed_rent": d["listed_rent"],
            "est_monthly_rent": d["est_monthly_rent"],
            "source": d["source"],
        }
    )

    st.subheader("Price history")
    history = get_history(lid)
    if len(history) >= 1:
        hist_df = pd.DataFrame(history, columns=["observed_at", "price"]).set_index("observed_at")
        st.line_chart(hist_df)
    else:
        st.caption("No price history yet.")

    st.link_button("Open on portal ↗", d["url"])
    watched = st.checkbox("On watchlist", value=d["is_watched"], key=f"watch-{lid}")
    if watched != d["is_watched"]:
        queries.set_watched(lid, watched)
        st.cache_data.clear()
        st.rerun()


def page_watchlist(listings: list[dict]) -> None:
    st.header("Watchlist")
    watched = [d for d in listings if d["is_watched"]]
    if not watched:
        st.info("Pin listings from the detail page to watch them.")
        return
    for d in watched:
        if d["price_dropped"]:
            st.success(
                f"📉 {d['title']} dropped to {fmt.euro(d['price'])} "
                f"(from {fmt.euro(d['first_price'])})"
            )
    df = pd.DataFrame(_row_summary(d) for d in watched)
    st.dataframe(df, use_container_width=True, hide_index=True)


def page_strategy() -> None:
    st.header("Strategy")
    st.caption("Edit the investor's rules & weights, then re-score live — no redeploy.")
    strategy = load_strategy()

    with st.form("strategy"):
        st.subheader("Hard filters")
        min_floor = st.number_input("Min floor", value=strategy.hard_filters.min_floor, step=1)
        max_metro = st.number_input(
            "Max metro distance (m)", value=strategy.hard_filters.max_metro_distance_m, step=50
        )
        st.subheader("Weights")
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
    st.header("🐛 Debug")
    st.caption("Raw data & pipeline diagnostics for troubleshooting.")

    rows = get_all_listings_debug()
    if not rows:
        st.warning("Database is empty — run the pipeline or seed it.")
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
        f"**Data last updated:** " f"{last_up:%Y-%m-%d %H:%M:%S} UTC"
        if last_up
        else "**Data last updated:** never"
    )
    if first_seens:
        st.write(f"**Earliest record seen:** {min(first_seens):%Y-%m-%d %H:%M:%S} UTC")

    st.subheader("Records by source")
    src: dict[str, int] = {}
    for d in rows:
        src[d["source"]] = src.get(d["source"], 0) + 1
    st.write(src)

    st.subheader("Records by status")
    status: dict[str, int] = {}
    for d in rows:
        status[d["status"]] = status.get(d["status"], 0) + 1
    st.write(status)

    st.subheader("All records (raw, including excluded & inactive)")
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "⬇️ Download as CSV", df.to_csv(index=False).encode("utf-8"), "holargos_listings.csv"
    )

    st.subheader("Inspect a single record")
    options = {f"{d['id']}: {d['title'] or d['source_id']}": d["id"] for d in rows}
    choice = st.selectbox("Record", list(options.keys()))
    rec = next(x for x in rows if x["id"] == options[choice])
    st.json({k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in rec.items()})


def main() -> None:
    st.title("🏠 Holargos Property Scout")

    with st.sidebar:
        if st.button("🔄 Refresh now (run pipeline)"):
            with st.spinner("Running pipeline…"):
                from scout.pipeline import run

                summary = run()
            st.cache_data.clear()
            st.success(f"Done: {summary}")

    listings = get_listings()

    # Freshness banner: when did the pipeline last see data?
    last_up = _last_updated(listings)
    if last_up is not None:
        st.caption(
            f"🕒 Data last updated **{last_up:%Y-%m-%d %H:%M} UTC** "
            f"· {len(listings)} active listings"
        )
    else:
        st.caption("🕒 No data yet — press **Refresh now** or wait for the daily run.")

    page = st.sidebar.radio(
        "Page",
        ["Today", "All opportunities", "Map", "Listing detail", "Watchlist", "Strategy", "Debug"],
    )
    if page == "Today":
        page_today(listings)
    elif page == "All opportunities":
        page_all(listings)
    elif page == "Map":
        page_map(listings)
    elif page == "Listing detail":
        page_detail(listings)
    elif page == "Watchlist":
        page_watchlist(listings)
    elif page == "Strategy":
        page_strategy()
    elif page == "Debug":
        page_debug()


main()
