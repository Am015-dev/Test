"""Map and list as ONE thing with ONE selection.

``render(ranked, key=...)`` draws, top to bottom:

1. the map (yield-band colours, exact solid / approximate small and faint); the selected
   listing is drawn larger with a dark ring and the map is centred on it;
2. DIRECTLY under the map, the selected listing's card with «Προηγούμενο / Επόμενο», which
   walk ``ranked`` and recentre the map; with nothing selected, the first card of ``ranked``
   and a one-line hint;
3. the ranked list, 10 at a time («Δείξε άλλες 10»); each card has «Στον χάρτη», which selects
   it, recentres the map and scrolls back up to it.

``st.session_state["selected_id"]`` is the only selection state. Tapping a point on the map,
«Στον χάρτη» and «Προηγούμενο / Επόμενο» all write it through ``select``; nothing keeps a
second copy. The pydeck selection arrives through an ``on_select`` callback, so it is applied
once when the tap happens and never overwrites a later «Επόμενο» on the following rerun.
"""

from __future__ import annotations

import streamlit as st

from . import buyer, components
from . import format as fmt

SELECTED = "selected_id"
PAGE = 10
HINT = "Πάτα μια κουκκίδα ή Επόμενο."
APPROX = "θέση κατά προσέγγιση (κέντρο περιοχής)"
NO_POSITION = "χωρίς θέση στον χάρτη"


def select(key: str, listing_id: int | None) -> None:
    """Make ``listing_id`` the selection (the map ring, the card under the map).

    ``key`` names the map/list instance; the next render scrolls that instance's map into view
    (a one-shot request, not selection state)."""
    st.session_state[SELECTED] = listing_id
    st.session_state[f"{key}-scroll"] = True


def selected(ranked: list[dict]) -> dict | None:
    """The selected listing if it is in ``ranked`` (a selection made elsewhere doesn't count)."""
    sid = st.session_state.get(SELECTED)
    return next((d for d in ranked if d.get("id") == sid), None) if sid is not None else None


def step(key: str, ids: list[int], delta: int) -> None:
    """Walk the ranked ids from the current selection (from the first card when none)."""
    if not ids:
        return
    sid = st.session_state.get(SELECTED)
    i = ids.index(sid) if sid in ids else 0
    st.session_state[SELECTED] = ids[(i + delta) % len(ids)]


def _on_map(key: str) -> None:
    """pydeck tap → selection. Runs once per tap, before the rerun."""
    state = st.session_state.get(f"{key}-map")
    try:
        objs = state["selection"]["objects"].get(components.MAP_LAYER) or []
    except (KeyError, TypeError, AttributeError):
        return
    if objs and objs[0].get("lid") is not None:
        st.session_state[SELECTED] = int(objs[0]["lid"])


def _more(key: str) -> None:
    st.session_state[f"{key}-n"] = st.session_state.get(f"{key}-n", PAGE) + PAGE


def _scroll_to(anchor: str) -> None:
    """Bring the map back into view after «Στον χάρτη» (Streamlit has no scroll API)."""
    st.html(
        "<script>(function(){var e=parent.document.querySelector('.st-key-"
        + anchor
        + "')||document.querySelector('.st-key-"
        + anchor
        + "');if(e)e.scrollIntoView({behavior:'smooth',block:'start'});})();</script>",
        unsafe_allow_javascript=True,
    )


def _css(key: str) -> None:
    """Prev/Next stay side by side on a phone (Streamlit stacks columns below 640 px)."""
    nav = f".st-key-{key}-nav [data-testid='stHorizontalBlock']"
    st.markdown(
        f"<style>{nav}{{flex-direction:row!important;flex-wrap:nowrap!important;gap:.5rem}}"
        f"{nav}>[data-testid='stColumn']{{flex:1 1 0!important;min-width:0!important;"
        "width:auto!important}</style>",
        unsafe_allow_html=True,
    )


def _header(d: dict, pos: int, total: int, chosen: bool) -> str:
    parts = [f"**{pos} από {fmt._gr_int(total)}**"]
    if not (d.get("lat") and d.get("lng")):
        parts.append(NO_POSITION)
    elif d.get("location_precision") != "exact":
        parts.append(APPROX)
    if not chosen:
        parts.append(HINT)
    return " · ".join(parts)


def render(ranked: list[dict], *, key: str, height: int = 380, intel=None) -> None:
    """Map + selected card + ranked list for ``ranked`` (already filtered and ordered)."""
    buyer._css()
    _css(key)
    if not ranked:
        st.info("Καμία αγγελία δεν ταιριάζει.")
        return
    if intel is None:
        from scout import market_intel

        intel = market_intel.build(ranked)
    ids = [d["id"] for d in ranked]
    chosen = selected(ranked)
    current = chosen or ranked[0]

    with st.container(key=f"{key}-anchor"):
        if st.session_state.pop(f"{key}-scroll", False):
            _scroll_to(f"{key}-anchor")
        components.results_map(
            ranked,
            key=f"{key}-map",
            height=height,
            selected_id=chosen["id"] if chosen else None,
            on_select=lambda: _on_map(key),
            legend=False,
        )

        # The selected card, directly under the map.
        st.markdown(_header(current, ids.index(current["id"]) + 1, len(ids), chosen is not None))
        c1, c2 = st.container(key=f"{key}-nav").columns(2, gap="small")
        c1.button(
            "Προηγούμενο",
            key=f"{key}-prev",
            on_click=step,
            args=(key, ids, -1),
            width="stretch",
            disabled=len(ids) < 2,
        )
        c2.button(
            "Επόμενο",
            key=f"{key}-next",
            on_click=step,
            args=(key, ids, 1),
            width="stretch",
            disabled=len(ids) < 2,
        )
        buyer.result_card(
            current,
            buyer.buyer_view(current, intel),
            f"{key}-sel",
            [("Λεπτομέρειες", buyer.open_detail, (current["id"],)), buyer._star_action(current)],
        )

    # What the colours mean and how exact the positions are — after the card, not between.
    components.map_legend()
    pts = [d for d in ranked if d.get("lat") and d.get("lng")]
    exact = sum(1 for d in pts if d.get("location_precision") == "exact")
    if pts and exact < len(pts):
        st.caption(
            f"Μόνο {fmt._gr_int(exact)} από {fmt._gr_int(len(pts))} έχουν ακριβή θέση· "
            "οι υπόλοιπες στο κέντρο της περιοχής τους."
            if exact
            else "Καμία δεν έχει ακριβή θέση· όλες είναι στο κέντρο της περιοχής τους."
        )

    # The ranked list, 10 at a time.
    n = min(st.session_state.get(f"{key}-n", PAGE), len(ranked))
    st.markdown(f"#### Όλες με τη σειρά · {fmt._gr_int(len(ranked))}")
    for d in ranked[:n]:
        actions = [
            ("Στον χάρτη", select, (key, d["id"]), "primary" if d is chosen else "secondary"),
            ("Λεπτομέρειες", buyer.open_detail, (d["id"],)),
            buyer._star_action(d),
        ]
        buyer.result_card(d, buyer.buyer_view(d, intel), f"{key}-l", actions)
    if n < len(ranked):
        st.button(
            f"Δείξε άλλες {min(PAGE, len(ranked) - n)}",
            key=f"{key}-more",
            on_click=_more,
            args=(key,),
            width="stretch",
        )
        st.caption(f"Εμφανίζονται {fmt._gr_int(n)} από {fmt._gr_int(len(ranked))}.")


# ---- the area map (the «Χάρτης» page) ------------------------------------------------------
#
# Most listings carry only their area's centre, so one dot per flat is a pile of fake positions.
# The page maps areas instead: one circle per area (size = how many flats, colour = the typical
# yield), and the selected area's best flats as cards under it.

AREA = "map_area"  # session key: the selected area's name (the map tap and the list both set it)
AREA_LAYER = "areas"


def area_of(d: dict) -> str:
    """The area a listing was collected for (its search area, in Greek): the unit the positions
    are good for. Neighbourhood names are not: dozens of them share one point."""
    from scout.place_names import SEARCH_AREA_GREEK

    sa = d.get("search_area") or ""
    return SEARCH_AREA_GREEK.get(sa, sa).replace(" Αττικής", "")


def area_groups(ranked: list[dict]) -> list[dict]:
    """One row per area with a position: name, count, centre, median yield and €/τ.μ.; most
    flats first."""
    import statistics

    by: dict[str, list[dict]] = {}
    for d in ranked:
        if d.get("lat") and d.get("lng") and (a := area_of(d)):
            by.setdefault(a, []).append(d)
    out = []
    for a, rows in by.items():
        ys = [y for d in rows if (y := components.gross_yield_of(d)) is not None]
        ppm = [d["price_per_m2"] for d in rows if d.get("price_per_m2")]
        out.append(
            {
                "name": a,
                "n": len(rows),
                "lat": statistics.median(d["lat"] for d in rows),
                "lon": statistics.median(d["lng"] for d in rows),
                "gy": statistics.median(ys) if ys else None,
                "ppm": statistics.median(ppm) if ppm else None,
            }
        )
    return sorted(out, key=lambda g: (-g["n"], g["name"]))


def area_line(g: dict) -> str:
    """«**Κυψέλη** · 312 αγγελίες · απόδοση ~4,6 % · ~2.900 €/τ.μ.»"""
    parts = [
        f"**{g['name']}**",
        f"{fmt._gr_int(g['n'])} {'αγγελία' if g['n'] == 1 else 'αγγελίες'}",
    ]
    if g["gy"] is not None:
        parts.append(f"απόδοση ~{components._pct_gr(g['gy'])}")
    if g["ppm"]:
        parts.append(f"~{fmt._gr_int(round(g['ppm'] / 10) * 10)} €/τ.μ.")
    return " · ".join(parts)


def _on_area(key: str) -> None:
    state = st.session_state.get(f"{key}-areas")
    try:
        objs = state["selection"]["objects"].get(AREA_LAYER) or []
    except (KeyError, TypeError, AttributeError):
        return
    if objs and objs[0].get("name"):
        st.session_state[AREA] = objs[0]["name"]
        st.session_state[f"{key}-n"] = PAGE


def _area_picked(key: str) -> None:
    st.session_state[f"{key}-n"] = PAGE


def _area_deck(groups: list[dict], chosen: str | None, view: tuple[float, float, float]):
    import math

    import pandas as pd
    import pydeck as pdk

    df = pd.DataFrame(
        {
            "name": g["name"],
            "n": g["n"],
            "lat": g["lat"],
            "lon": g["lon"],
            "fill": [*components.yield_color(g["gy"]), 255 if g["name"] == chosen else 190],
            "r": 180 + 14 * math.sqrt(g["n"]),  # metres: shrinks with the zoom
            "line": [17, 24, 39, 255] if g["name"] == chosen else [255, 255, 255, 220],
            "w": 3 if g["name"] == chosen else 1,
            "tip": area_line(g).replace("**", ""),
        }
        for g in groups
    )
    lat_c, lng_c, zoom = view
    if chosen and (row := next((g for g in groups if g["name"] == chosen), None)):
        lat_c, lng_c, zoom = row["lat"], row["lon"], max(zoom, 12.5)
    layers = [
        pdk.Layer(
            "ScatterplotLayer", id=AREA_LAYER, data=df, get_position="[lon, lat]",
            get_fill_color="fill", get_radius="r", radius_min_pixels=7, radius_max_pixels=26,
            stroked=True, get_line_color="line", get_line_width="w", line_width_units="'pixels'",
            pickable=True,
        ),
        pdk.Layer(  # the names, so a circle is a place and not a puzzle
            "TextLayer", id="names", data=df[df["n"] >= 20], get_position="[lon, lat]",
            get_text="name", get_size=12, get_color=[15, 23, 42, 255],
            get_pixel_offset=[0, 16], font_family="'Inter, system-ui, sans-serif'",
            character_set="'auto'", outline_width=3, outline_color=[255, 255, 255, 230],
            font_settings={"sdf": True},
        ),
    ]  # fmt: skip
    return components._compact_deck_class()(
        map_style="light",
        initial_view_state=pdk.ViewState(latitude=lat_c, longitude=lng_c, zoom=zoom),
        layers=layers,
        tooltip={"html": "{tip}", "style": {"fontSize": "14px", "maxWidth": "240px"}},
    )


def area_legend() -> str:
    dots = [
        (components._YIELD_COLORS["low"], "κάτω από 3,5 %"),
        (components._YIELD_COLORS["mid"], "3,5–5 %"),
        (components._YIELD_COLORS["high"], "πάνω από 5 %"),
    ]
    items = "".join(
        f'<span style="margin-right:12px;white-space:nowrap"><span style="display:inline-block;'
        f"width:11px;height:11px;border-radius:50%;background:rgb({c[0]},{c[1]},{c[2]});"
        f'margin-right:5px;vertical-align:middle"></span>{label}</span>'
        for c, label in dots
    )
    return f'<div class="hg-legend" style="line-height:1.7">Απόδοση: {items}</div>'


def render_areas(ranked: list[dict], *, key: str, intel, height: int = 380) -> None:
    """The area map, the area picker under it, then the chosen area's flats (best first)."""
    buyer._css()
    groups = area_groups(ranked)
    if not groups:
        st.info("Καμία αγγελία δεν ταιριάζει.")
        return
    names = [g["name"] for g in groups]
    if st.session_state.get(AREA) not in names:
        st.session_state[AREA] = None
    chosen = st.session_state.get(AREA)
    pts = [d for d in ranked if d.get("lat") and d.get("lng")]  # frame where the flats are
    lats, lngs = sorted(d["lat"] for d in pts), sorted(d["lng"] for d in pts)
    view = (lats[len(lats) // 2], lngs[len(lngs) // 2], 10.8)  # every area on a phone
    st.pydeck_chart(
        _area_deck(groups, chosen, view), height=height, key=f"{key}-areas",
        on_select=lambda: _on_area(key), selection_mode="single-object",
    )  # fmt: skip
    st.markdown(area_legend(), unsafe_allow_html=True)
    count = {g["name"]: g["n"] for g in groups}
    st.selectbox(
        "Περιοχή", names, key=AREA, index=None, placeholder="Διάλεξε περιοχή ή πάτα έναν κύκλο",
        format_func=lambda a: f"{a} · {fmt._gr_int(count[a])} {'αγγελία' if count[a] == 1 else 'αγγελίες'}", on_change=_area_picked,
        args=(key,), label_visibility="collapsed",
    )  # fmt: skip
    if chosen:
        rows = [d for d in ranked if area_of(d) == chosen]
        st.markdown(area_line(next(g for g in groups if g["name"] == chosen)))
    else:
        rows = ranked
        st.markdown("#### Οι καλύτερες σε όλες τις περιοχές")
    n = min(st.session_state.get(f"{key}-n", PAGE), len(rows))
    for i, d in enumerate(rows[:n], start=1):
        buyer.result_card(
            d, buyer.buyer_view(d, intel), f"{key}-l",
            [("Λεπτομέρειες", buyer.open_detail, (d["id"],)), buyer._star_action(d)],
            lead=f"{i}.",
        )  # fmt: skip
    if n < len(rows):
        st.button(
            f"Δείξε άλλες {min(PAGE, len(rows) - n)}", key=f"{key}-more", on_click=_more,
            args=(key,), width="stretch",
        )  # fmt: skip
