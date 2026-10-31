"""«Βρες μου σπίτι» — budget in, the best three flats out, each with the case for it.

Phone-first: one column, the answer above the fold, no tables, no metric rows. Each card says
first whether we read the listing's page; when too little qualifies the page offers one-tap
relaxations with exact counts instead of a dead end; the method is explained once, at the
bottom.
"""

from __future__ import annotations

import html
import statistics
from datetime import date

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


# On a phone Streamlit stacks columns, which turns a card's 2×2 buttons into four full-width
# rows. Keep the button pairs side by side (labels are short enough for 2 × 175 px).
PHONE_CSS = """<style>
[class*="st-key-pick-"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: .5rem; }
[class*="st-key-pick-"] [data-testid="stColumn"] { min-width: 0; width: auto; flex: 1 1 0; }
</style>"""


def _card(i: int, p: picks.Pick, approved: bool) -> None:
    d = p.listing
    e = html.escape
    with st.container(border=True, key=f"pick-{d['id']}"):
        st.markdown(
            f"### {i}. {buyer.eur(d['price'])}" + (" · το ενέκρινες" if approved else "") + "\n"
            f"**{e(d.get('title') or '')}** · {e(d.get('neighborhood') or '')}"
        )
        st.markdown(f":{'green' if p.checked else 'orange'}[**{e(p.status)}**]")
        st.markdown("  \n".join(e(x) for x in p.lines))
        if p.risks:
            st.markdown("**Έλεγξε**\n" + "\n".join(f"- {e(r)}" for r in p.risks))
        if p.excerpt:
            with st.expander("Τι λέει η αγγελία"):
                st.markdown(e(p.excerpt))
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


AGES: dict[int | None, str] = {
    5: "Έως 5 ετών",
    10: "Έως 10 ετών (νεόδμητο)",
    15: "Έως 15 ετών",
    20: "Έως 20 ετών",
    None: "Οποιαδήποτε",
}
# relaxation keyword (picks.find) → the widget key that holds it
WIDGETS = {
    "budget": "find_budget",
    "max_age": "find_age",
    "near_rail": "find_rail",
    "checked_only": "find_checked",
}
BUDGET_MAX = 2_000_000


def apply_relax(changes: dict) -> None:
    for k, v in changes.items():
        st.session_state[WIDGETS[k]] = min(v, BUDGET_MAX) if k == "budget" else v


def _relax(options: list[picks.Relax], intro: str) -> None:
    with st.container(border=True, key="find-relax"):
        st.markdown(intro)
        for i, r in enumerate(options):
            st.button(
                r.text, key=f"relax-{i}", on_click=apply_relax, args=(r.changes,), width="stretch"
            )


METHOD = """
- **Ενοίκιο (εκτίμηση)**: διάμεσο ζητούμενο ενοίκιο €/τ.μ. των αγγελιών ενοικίασης XE.gr στη
  γειτονιά (αλλιώς στην ευρύτερη περιοχή) × τ.μ. του διαμερίσματος, +10 % για κτίριο έως 5 ετών.
  Ζητούμενα ενοίκια, όχι συμβόλαια — το πραγματικό μπορεί να είναι ±10 %.
- **Μικτή απόδοση** = 12 × ενοίκιο ÷ τιμή.
- **Καθαρή απόδοση**: 11 μήνες ενοίκιο τον χρόνο (1 μήνας κενός), −15 % φόρος ενοικίων,
  −5 % συντήρηση, −ΕΝΦΙΑ ~3 €/τ.μ. τον χρόνο, διά τιμή + έξοδα αγοράς (φόρος μεταβίβασης,
  συμβολαιογράφος, δικηγόρος, μεσίτης αν δεν πουλάει ιδιώτης). Τα κοινόχρηστα τα πληρώνει ο
  ενοικιαστής.
- **Τιμή €/τ.μ. και παρόμοια**: διάμεσος €/τ.μ. αγγελιών στην ίδια περιοχή, ίδιου τύπου,
  παρόμοιας ηλικίας, μεγέθους και ορόφου. Πάνω από 35 % φθηνότερο είναι προειδοποίηση, όχι
  ευκαιρία.
- **Προσφορά**: ζητούμενη τιμή −3 %, −3 % ακόμα αν είναι 90+ μέρες στην αγορά, −2 % αν
  πουλάει ιδιώτης. Αφετηρία διαπραγμάτευσης, όχι εκτίμηση αξίας.
- **Σταθμός**: τα XE δεν δίνουν διεύθυνση· η γειτονιά της αγγελίας είναι η περιοχή ενός
  σταθμού. Επιβεβαίωσε τη διεύθυνση.
- **Ελέγχθηκε η περιγραφή**: διαβάσαμε τη σελίδα της αγγελίας· δεν δηλώνει «Υπό κατασκευή»,
  διαθεσιμότητα σε μελλοντική ημερομηνία ή παράδοση σε επόμενο έτος, και η περιγραφή δεν γράφει
  «ημιτελές», «υπό κατασκευή», «σκελετός». Οι φωτογραφίες δεν ελέγχονται αυτόματα· σημειώνω
  μόνο όσες αγγελίες έχουν έως 2. Όσες δεν έχουν ελεγχθεί ακόμα μπαίνουν μετά τις ελεγμένες.
- **Σειρά**: ελεγμένες πρώτα, μετά όσες έχουν περισσότερες από 2 φωτογραφίες, μετά η
  μικτή απόδοση και η τιμή σε σχέση με τα παρόμοια.
- Τιμές: ζητούμενες τιμές XE.gr, όχι τιμές πώλησης.
"""


def page_find(listings: list[dict]) -> None:
    st.markdown(f"## {TITLE}")
    st.caption("Πες τον προϋπολογισμό σου. Βρίσκω τα 3 καλύτερα για αγορά προς ενοικίαση.")
    st.markdown(PHONE_CSS, unsafe_allow_html=True)
    st.session_state.setdefault("find_age", picks.NEW_YEARS)
    with st.container(border=True, key="find-form"):
        budget = st.number_input(
            "Προϋπολογισμός (€)", 50_000, BUDGET_MAX, 300_000, 10_000, key="find_budget"
        )
        max_age = st.selectbox(
            "Ηλικία κτιρίου", list(AGES), format_func=AGES.__getitem__, key="find_age"
        )
        c = st.columns(2)
        near_rail = c[0].toggle("Δίπλα σε σταθμό μετρό/ΗΣΑΠ", True, key="find_rail")
        checked_only = c[1].toggle("Μόνο ελεγμένες σελίδες", False, key="find_checked")
    intel = market_intel.build(listings)
    rents = _rent_rows()
    year = date.today().year
    rules = dict(max_age=max_age, near_rail=near_rail, checked_only=checked_only, year=year)
    found = picks.find(listings, intel, rents, int(budget), top=10_000, **rules)
    review = _review()
    every, dropped = arrange(found, review)
    lo, hi = budget * (1 - picks.BUDGET_BAND), budget * (1 + picks.BUDGET_BAND)
    what = (
        f"{buyer.eur(lo)}–{buyer.eur(hi)}"
        + (f", κτίριο έως {max_age} ετών" if max_age is not None else "")
        + (", δίπλα σε σταθμό" if near_rail else "")
        + (", μόνο ελεγμένες" if checked_only else "")
    )
    checked = sum(p.checked for p in every)
    relax = (
        picks.relaxations(listings, intel, rents, int(budget), **rules)
        if len(every) < picks.TOP or checked < picks.TOP
        else []
    )
    if not every:
        st.markdown(f"Καμία αγγελία {what}.")
        if relax:
            _relax(relax, "Χαλάρωσε έναν όρο — σε παρένθεση πόσες αγγελίες προστίθενται:")
        else:
            st.info("Ούτε με έναν όρο λιγότερο βρίσκω κάτι. Άλλαξε τον προϋπολογισμό.")
        if dropped:
            _dropped(dropped)
        _method()
        return
    st.markdown(
        f"**{len(every)}** αγγελίες {what}. Ελέγχθηκε η περιγραφή σε **{checked}** από αυτές."
        f" Διάμεση μικτή απόδοση **{picks.gr_pct(statistics.median(p.gross for p in every))}**."
    )
    intro = (
        f"Μόνο {len(every)} {'ταιριάζει' if len(every) == 1 else 'ταιριάζουν'}"
        if len(every) < picks.TOP
        else f"Μόνο {checked} {'ελεγμένη' if checked == 1 else 'ελεγμένες'}"
    ) + ". Με έναν όρο λιγότερο (σε παρένθεση πόσες προστίθενται):"
    if relax and len(every) < picks.TOP:
        _relax(relax, intro)
    ok = {shortlist.lkey(p.listing) for p in every if review.get(shortlist.lkey(p.listing)) == "ok"}
    for i, p in enumerate(every[: max(picks.TOP, len(ok))], start=1):
        _card(i, p, shortlist.lkey(p.listing) in ok)
    if relax and len(every) >= picks.TOP:
        _relax(relax, intro)
    if dropped:
        _dropped(dropped)
    _method()


def _method() -> None:
    with st.expander("Πώς υπολογίζω"):
        st.markdown(METHOD)
