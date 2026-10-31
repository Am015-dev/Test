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
            "‹ Προηγούμενο",
            key=f"{key}-prev",
            on_click=step,
            args=(key, ids, -1),
            width="stretch",
            disabled=len(ids) < 2,
        )
        c2.button(
            "Επόμενο ›",
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
    st.markdown(f"#### Όλες με τη σειρά ({fmt._gr_int(len(ranked))})")
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
