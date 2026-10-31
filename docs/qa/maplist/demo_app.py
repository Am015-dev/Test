"""QA harness: the «Χάρτης» page body as W10 will wire it (see the PR body), on the live DB.

    DATABASE_URL=sqlite:////ABS/data/listings.db \
        streamlit run docs/qa/maplist/demo_app.py --server.headless true --server.port 8502
"""

from __future__ import annotations

import streamlit as st

from scout import market_intel, nl_search
from scout.nl_search import SearchFilters
from scout.ui import buyer, maplist, queries
from scout.ui.theme import inject_css

st.set_page_config(page_title="Χάρτης", layout="centered", initial_sidebar_state="collapsed")
inject_css()


@st.cache_resource
def _ranked():
    listings = queries.load_listings(include_excluded=True, only_active=True)
    shown = [
        d
        for d in listings
        if not (d["excluded"] or d.get("is_suspect") or d.get("is_unfinished"))
        and d.get("is_fresh", True)
    ]
    intel = market_intel.build(listings)
    rank = buyer.SORTS[buyer.DEFAULT_SORT]

    def _key(d):
        m = nl_search.match(d, SearchFilters())
        return rank(m[0] if m else 0, buyer.buyer_view(d, intel), d)

    return sorted(shown, key=_key), intel


st.subheader("Χάρτης")
ranked, intel = _ranked()
maplist.render(ranked, key="map", intel=intel)
