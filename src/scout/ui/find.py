"""«Βρες μου σπίτι» — budget in, the best three flats out, each with the case for it.

Phone-first: one column, the answer above the fold, no tables.
"""

from __future__ import annotations

import html
import statistics

import streamlit as st

from scout import market_intel, picks
from scout.ui import buyer

TITLE = "Βρες μου σπίτι"


@st.cache_data(ttl=600, show_spinner=False)
def _rent_rows() -> list[dict]:
    from scout.ui import queries

    return queries.load_rent_comp_rows()


def _card(i: int, p: picks.Pick) -> None:
    d = p.listing
    e = html.escape
    with st.container(border=True, key=f"pick-{d['id']}"):
        st.markdown(
            f"### {i}. {buyer.eur(d['price'])}\n"
            f"**{e(d.get('title') or '')}** · {e(d.get('neighborhood') or '')}"
        )
        c = st.columns(3)
        c[0].metric("Ενοίκιο", f"~{buyer.eur(p.rent)}", help="ανά μήνα, εκτίμηση")
        c[1].metric("Μικτή απόδοση", picks.gr_pct(p.gross))
        c[2].metric("Καθαρή", f"~{picks.gr_pct(p.net)}")
        st.caption(
            f"Ενοίκιο μάλλον {buyer.eur(p.rent_low)}–{buyer.eur(p.rent_high)} τον μήνα. "
            f"Πρόταση προσφοράς: ~{buyer.eur(p.offer)}."
        )
        st.markdown("**Γιατί αυτό**\n" + "\n".join(f"- {e(w)}" for w in p.why))
        if p.risks:
            st.markdown("**Έλεγξε**\n" + "\n".join(f"- {e(r)}" for r in p.risks))
        cols = st.columns(3)
        cols[0].link_button("Άνοιγμα στο XE ↗", d["url"], width="stretch")
        cols[1].button(
            "Λεπτομέρειες",
            key=f"pick-det-{d['id']}",
            on_click=buyer.open_detail,
            args=(d["id"],),
            width="stretch",
        )
        label, cb, args, kind = buyer._star_action(d)
        cols[2].button(
            label, key=f"pick-star-{d['id']}", on_click=cb, args=args, type=kind, width="stretch"
        )


def page_find(listings: list[dict]) -> None:
    st.markdown(f"## {TITLE}")
    st.caption(
        "Πες τον προϋπολογισμό σου. Βρίσκω τα 3 καλύτερα για αγορά προς ενοικίαση και "
        "εξηγώ γιατί, με τους αριθμούς."
    )
    with st.container(border=True, key="find-form"):
        budget = st.number_input(
            "Προϋπολογισμός (€)", 50_000, 2_000_000, 300_000, 10_000, key="find_budget"
        )
        c = st.columns(2)
        new_only = c[0].toggle(f"Νεόδμητο (έως {picks.NEW_YEARS} ετών)", True, key="find_new")
        near_rail = c[1].toggle("Δίπλα σε σταθμό μετρό/ΗΣΑΠ", True, key="find_rail")
    intel = market_intel.build(listings)
    rents = _rent_rows()
    every = picks.find(
        listings, intel, rents, int(budget), new_only=new_only, near_rail=near_rail, top=10_000
    )
    lo, hi = budget * (1 - picks.BUDGET_BAND), budget * (1 + picks.BUDGET_BAND)
    if not every:
        st.info(
            "Δεν βρήκα αγγελίες με αυτά τα κριτήρια. Δοκίμασε μεγαλύτερο προϋπολογισμό ή "
            "βγάλε έναν όρο (νεόδμητο / σταθμός)."
        )
        return
    gross = [p.gross for p in every]
    st.markdown(
        f"Από **{len(every)}** αγγελίες {buyer.eur(lo)}–{buyer.eur(hi)}"
        + (", νεόδμητες" if new_only else "")
        + (", δίπλα σε σταθμό" if near_rail else "")
        + f", η διάμεση μικτή απόδοση είναι **{picks.gr_pct(statistics.median(gross))}**. "
        "Αυτές είναι οι 3 με την καλύτερη απόδοση και τιμή:"
    )
    checked = sum(p.checked for p in every)
    if checked < len(every):
        st.caption(
            f"Ελεγμένες σελίδες αγγελιών: {checked} από {len(every)}. Πρώτα δείχνω όσες "
            "επιβεβαιώθηκε ότι είναι έτοιμες (όχι υπό κατασκευή)."
        )
    for i, p in enumerate(every[: picks.TOP], start=1):
        _card(i, p)
    if near_rail or new_only:
        loose = picks.find(listings, intel, rents, int(budget), new_only=False, near_rail=False)
        if loose and loose[0].gross > every[0].gross + 0.005:
            b = loose[0].listing
            st.caption(
                f"Για σύγκριση: χωρίς τους όρους «νεόδμητο»/«σταθμός» η καλύτερη απόδοση "
                f"είναι {picks.gr_pct(loose[0].gross)} ({b.get('neighborhood')}, "
                f"κτίριο {b.get('year_built') or '—'}). Νεόδμητο δίπλα σε σταθμό σημαίνει "
                "ακριβότερο τ.μ. — άρα χαμηλότερη απόδοση, αλλά πιο εύκολη ενοικίαση και "
                "μεταπώληση."
            )
    st.caption(
        "Ζητούμενες τιμές και ζητούμενα ενοίκια XE.gr, όχι συμβόλαια. Η εγγύτητα σε σταθμό "
        "προκύπτει από το όνομα της γειτονιάς στην αγγελία — επιβεβαίωσε τη διεύθυνση."
    )
