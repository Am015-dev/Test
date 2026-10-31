"""«Βρες μου σπίτι» — budget in, the best three flats out, each with the case for it.

Phone-first: one column, the answer above the fold, no tables.
"""

from __future__ import annotations

import html
import statistics

import streamlit as st

from scout import market_intel, picks, shortlist
from scout.ui import buyer

TITLE = "Βρες μου σπίτι"


@st.cache_data(ttl=600, show_spinner=False)
def _rent_rows() -> list[dict]:
    from scout.ui import queries

    return queries.load_rent_comp_rows()


def arrange(
    found: list[picks.Pick], review: dict[str, str]
) -> tuple[list[picks.Pick], list[picks.Pick]]:
    """(shown, dropped): approved picks first, then the ranking; dropped ones leave the list
    so the next best move up."""

    def v(p: picks.Pick) -> str | None:
        return review.get(shortlist.lkey(p.listing))

    shown = sorted((p for p in found if v(p) != "no"), key=lambda p: v(p) != "ok")
    return shown, [p for p in found if v(p) == "no"]


def _review() -> dict[str, str]:
    """The owner's verdicts (listing key → "ok" | "no"), loaded from storage once a session."""
    if "pick_review" not in st.session_state:
        verdicts: dict[str, str] = {}
        try:
            verdicts = shortlist.review_map()
            st.session_state["review_persisted"] = True
        except shortlist.StorageNotConfigured:
            st.session_state["review_persisted"] = False
        except Exception as e:  # network / auth: keep working, say so once
            st.session_state["review_persisted"] = False
            buyer._flash("error", f"Οι επιλογές σου δεν φορτώθηκαν ({buyer._reason(e)}).")
        st.session_state["pick_review"] = verdicts
    return st.session_state["pick_review"]


def set_verdict(key: str, verdict: str | None) -> None:
    review = _review()
    if verdict is None:
        review.pop(key, None)
    else:
        review[key] = verdict
    if verdict == "ok":
        buyer.watch_keys().add(key)
    if st.session_state.get("review_persisted"):
        try:
            shortlist.set_review(key, verdict)
        except Exception as e:
            buyer._flash(
                "error",
                f"Δεν αποθηκεύτηκε ({buyer._reason(e)}) — ισχύει μέχρι να κλείσεις τη σελίδα.",
            )


def _card(i: int, p: picks.Pick, approved: bool) -> None:
    d = p.listing
    e = html.escape
    with st.container(border=True, key=f"pick-{d['id']}"):
        st.markdown(
            f"### {i}. {buyer.eur(d['price'])}" + (" · ✓ το ενέκρινες" if approved else "") + "\n"
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
        key = shortlist.lkey(d)
        cols = st.columns(2)
        cols[0].link_button("Άνοιγμα στο XE ↗", d["url"], width="stretch")
        cols[1].button(
            "Λεπτομέρειες",
            key=f"pick-det-{d['id']}",
            on_click=buyer.open_detail,
            args=(d["id"],),
            width="stretch",
        )
        cols = st.columns(2)
        if approved:
            cols[0].button(
                "↺ Αναίρεση έγκρισης",
                key=f"pick-undo-{d['id']}",
                on_click=set_verdict,
                args=(key, None),
                width="stretch",
            )
        else:
            cols[0].button(
                "✓ Εγκρίνω",
                key=f"pick-ok-{d['id']}",
                on_click=set_verdict,
                args=(key, "ok"),
                type="primary",
                width="stretch",
                help="Το κρατάω — μπαίνει πρώτο και στα αγαπημένα.",
            )
        cols[1].button(
            "✗ Δεν μου κάνει",
            key=f"pick-no-{d['id']}",
            on_click=set_verdict,
            args=(key, "no"),
            width="stretch",
            help="Φεύγει από τη λίστα και εμφανίζεται το επόμενο.",
        )


def _dropped(rows: list[picks.Pick]) -> None:
    with st.expander(f"Απέρριψες {len(rows)}"):
        for p in rows:
            d = p.listing
            c = st.columns([3, 1])
            c[0].markdown(
                f"[{buyer.eur(d['price'])} · {d.get('area_m2') or '?'} τ.μ. · "
                f"{html.escape(d.get('neighborhood') or '')}]({d['url']})"
            )
            c[1].button(
                "Επαναφορά",
                key=f"pick-back-{d['id']}",
                on_click=set_verdict,
                args=(shortlist.lkey(d), None),
                width="stretch",
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
    found = picks.find(
        listings, intel, rents, int(budget), new_only=new_only, near_rail=near_rail, top=10_000
    )
    review = _review()
    every, dropped = arrange(found, review)
    lo, hi = budget * (1 - picks.BUDGET_BAND), budget * (1 + picks.BUDGET_BAND)
    if not every:
        if dropped:
            _dropped(dropped)
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
        "Αυτές είναι οι 3 με την καλύτερη απόδοση και τιμή. Άνοιξε την αγγελία και δες τις "
        "φωτογραφίες: αν είναι μόνο renders ή σχέδια, ή δείχνουν γυμνούς τοίχους και σκαλωσιές, "
        "πάτα «Δεν μου κάνει» και έρχεται το επόμενο."
    )
    checked = sum(p.checked for p in every)
    if checked < len(every):
        st.caption(
            f"Ελεγμένες σελίδες αγγελιών: {checked} από {len(every)}. Πρώτα δείχνω όσες "
            "επιβεβαιώθηκε ότι είναι έτοιμες (όχι υπό κατασκευή)."
        )
    ok = {shortlist.lkey(p.listing) for p in every if review.get(shortlist.lkey(p.listing)) == "ok"}
    for i, p in enumerate(every[: max(picks.TOP, len(ok))], start=1):
        _card(i, p, shortlist.lkey(p.listing) in ok)
    if dropped:
        _dropped(dropped)
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
