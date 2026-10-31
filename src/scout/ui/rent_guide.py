"""«Οδηγός» for renters: step 0 «Τι ψάχνεις;», then five one-question screens.

Same shape as the buy flow (``ui/guide.py``): one question per screen, big tappable choices,
«Βήμα n από 5», «Πίσω», the answers as chips that reopen their question, results ten at a
time, relaxations with exact counts, «Εγκρίνω» / «Δεν μου κάνει», the assistant's note and
«Ρώτα με». Steps: 1 «Πόσο τον μήνα;» · 2 «Πόσα υπνοδωμάτια;» · 3 «Πού;» · 4 «Τι σπίτι;» ·
5 «Η πρότασή μου». Engine: ``picks_rent.find`` / ``picks_rent.relaxations``.

The mode lives in ``st.session_state["guide"]["mode"]`` and, with the rest of the guide's
answers, in the profile store under ``guide`` (``guide.mode``, ``guide.rent``).

Data: ``queries.load_rent_listings()`` (contract C1). With no rentals stored yet (or no
loader) the page says so (``SOON``).

Assistant: ``rent_facts`` builds ``facts["listings"]`` from the ``RentPick``s; the note and
«Ρώτα με» reuse ``ui.assistant``'s client, cache and grounding check with renter rules (no
yield; deposit, charges, contract length, energy certificate).
"""

from __future__ import annotations

import html
import statistics
from collections import Counter
from datetime import date, datetime

import streamlit as st

from scout import area_insights, picks, picks_rent, shortlist
from scout.ui import buyer, guide

STEPS = 5
MODES = {"buy": "Να αγοράσω", "rent": "Να νοικιάσω"}
MODE_CHIP = {"buy": "να αγοράσω", "rent": "να νοικιάσω"}
BUDGETS = (400, 600, 800, 1000, 1300, 1600)  # €/μήνα
BUDGET_MIN, BUDGET_MAX = 200, 10_000
BEDS = {"1": "1", "2": "2", "3": "3+", "any": "Αδιάφορο"}
AGES = guide.AGES
MIN_AREA = 5  # an area is offered as a chip with at least this many active rentals
SOON = (
    "Δεν έχουμε ακόμα αγγελίες ενοικίασης: η πρώτη εβδομαδιαία ενημέρωση με ενοίκια δεν έχει "
    "γίνει ακόμα. Ξαναδές μετά την επόμενη ενημέρωση."
)
DEFAULTS = {
    "step": 1,
    "budget": None,
    "beds": None,  # "1" | "2" | "3" | "any"; None = not answered
    "where": None,
    "areas": [],
    "age": None,
    "furnished": False,
}
WIDGETS = ("rent_other", "rent_areas", "rent_age", "rent_furn", "rent_chips")


# ---- state ---------------------------------------------------------------------------------


def rstate() -> dict:
    g = guide.state()
    g["rent"] = {**DEFAULTS, **(g.get("rent") or {})}
    return g["rent"]


def _saved() -> None:
    guide._save(guide.state())


def set_mode(mode: str | None) -> None:
    """Step 0's answer (None = show step 0 again)."""
    guide._resync()
    for k in WIDGETS:
        st.session_state.pop(k, None)
    guide.state()["mode"] = mode
    _saved()


def go(step: int) -> None:
    for k in WIDGETS:
        st.session_state.pop(k, None)
    if step < 1:
        set_mode(None)
        return
    rstate()["step"] = min(STEPS, step)
    _saved()


def answer(field: str, value, next_step: int | None = None) -> None:
    r = rstate()
    r[field] = value
    if next_step:
        r["step"] = next_step
    st.session_state["rent_shown"] = picks.PAGE
    _saved()


def _set_where(value: str) -> None:
    answer("where", value, None if value == "areas" else 4)


def _other_budget() -> None:
    answer("budget", int(st.session_state["rent_other"]), 2)


def _areas_picked() -> None:
    answer("areas", list(st.session_state.get("rent_areas") or []))


def _age_code(age: int | None) -> str:
    return "any" if age is None else ("10" if age <= picks.NEW_YEARS else "20")


def _age_changed() -> None:
    v = st.session_state.get("rent_age")
    if v is None:  # tapping the selected option clears it: keep the answer
        st.session_state["rent_age"] = _age_code(rstate().get("age"))
    else:
        rstate()["age"] = None if v == "any" else int(v)


def _furn_changed() -> None:
    rstate()["furnished"] = bool(st.session_state.get("rent_furn"))


def _chip_jump() -> None:
    pick = st.session_state.get("rent_chips")
    st.session_state["rent_chips"] = None
    for i, label in enumerate(answer_chips(rstate())):
        if label == pick:
            go(i)


def apply_relax(changes: dict) -> None:
    for k in WIDGETS:
        st.session_state.pop(k, None)
    r = rstate()
    for k, v in changes.items():
        if k == "budget_month":
            r["budget"] = min(int(v), BUDGET_MAX)
        elif k == "max_age":
            r["age"] = v
        elif k == "near_rail" and not v:
            r["where"] = "best"
        elif k == "areas" and not v:
            r["where"], r["areas"] = "best", []
        elif k == "bedrooms":
            r["beds"] = "any"
        elif k == "furnished":
            r["furnished"] = bool(v)
    st.session_state["rent_shown"] = picks.PAGE
    _saved()


def _more() -> None:
    st.session_state["rent_shown"] = st.session_state.get("rent_shown", picks.PAGE) + picks.PAGE


def _toggle_details(listing_id: int) -> None:
    opened = st.session_state.setdefault("rent_details", set())
    opened.symmetric_difference_update({listing_id})


# ---- words ---------------------------------------------------------------------------------


def eur(v: float) -> str:
    return picks_rent.eur(v)


def bedrooms(r: dict) -> int | None:
    b = r.get("beds")
    return None if b in (None, "any") else int(b)


def answer_chips(r: dict) -> list[str]:
    """Mode chip, then one chip per rent question (steps 1–4)."""
    where = {
        "rail": "κοντά σε μετρό",
        "best": "όλες οι περιοχές",
        "areas": ", ".join(r.get("areas") or []) or "περιοχές",
    }
    beds = r.get("beds")
    kind = guide.age_text(r.get("age"))
    return [
        MODE_CHIP["rent"],
        f"έως {eur(r['budget'])}/μήνα" if r.get("budget") else "ποσό;",
        "υπν. αδιάφορο" if beds == "any" else (f"{BEDS[beds]} υπν." if beds else "υπνοδωμάτια;"),
        where.get(r.get("where") or "", "πού;"),
        ("επιπλωμένο · " if r.get("furnished") else "") + kind,
    ]


def covered_areas(rentals: list[dict]) -> list[tuple[str, int]]:
    n = Counter(
        area_insights.area_name(d.get("neighborhood"))
        for d in rentals
        if picks_rent.usable(d) and d.get("neighborhood")
    )
    return [(a, c) for a, c in n.most_common() if c >= MIN_AREA]


def recommend(found: list[picks_rent.RentPick]) -> str | None:
    """One sentence: the area of the list where rents sit lowest against their comparables."""
    by: dict[str, list[picks_rent.RentPick]] = {}
    for p in found:
        if p.vs_area_pct is not None and not p.too_cheap:
            by.setdefault(area_insights.area_name(p.listing.get("neighborhood")), []).append(p)
    if not by:
        return None

    def med(ps, f):
        return statistics.median(f(p) for p in ps)

    area = min(by, key=lambda a: (med(by[a], lambda p: p.vs_area_pct), -len(by[a])))
    ps = by[area]
    vs = med(ps, lambda p: p.vs_area_pct)
    rel = (
        "όσο τα παρόμοια"
        if abs(vs) < 0.02
        else f"{round(abs(vs) * 100)} % {'κάτω' if vs < 0 else 'πάνω'} από τα παρόμοια"
    )
    return (
        f"Πρόταση: **{html.escape(area)}** — {len(ps)} από τις {len(found)} αγγελίες της λίστας, "
        f"διάμεσο ενοίκιο {picks_rent.gr_num(med(ps, lambda p: p.rent_per_m2))} €/τ.μ., "
        f"διάμεσα {rel}."
    )


def coverage(rentals: list[dict]) -> str:
    names = {guide.SOURCES.get(d.get("source") or "", d.get("source") or "") for d in rentals}
    srcs = sorted((s for s in names if s), key=lambda s: (s != "XE.gr", s))
    active = sum(1 for d in rentals if d.get("is_fresh", True))
    return f"Πηγές: {', '.join(srcs) or 'XE.gr'} · {buyer._num(active)} αγγελίες ενοικίασης ενεργές"


def _day(v) -> str | None:
    return f"{v:%d/%m/%Y}" if isinstance(v, (date, datetime)) else None


# ---- data ----------------------------------------------------------------------------------


@st.cache_data(ttl=600, show_spinner=False)
def _load() -> list[dict] | None:
    from scout.ui import queries

    try:
        return queries.load_rent_listings()
    except AttributeError:  # contract C1 not merged yet
        return None


def rentals() -> list[dict] | None:
    try:
        return _load()
    except Exception:
        return None


def starred(keys: set[str]) -> list[picks_rent.RentPick]:
    """The starred rentals (``buyer.page_watchlist``), as picks for the rent card."""
    rows = rentals() or []
    index = picks_rent.comps_index(rows)
    return [
        picks_rent.pick(d, index)
        for d in rows
        if picks_rent.usable(d) and shortlist.lkey(d) in keys
    ]


# ---- assistant -----------------------------------------------------------------------------

SUGGESTIONS = (
    "Γιατί αυτό και όχι το φθηνότερο;",
    "Τι να ρωτήσω τον ιδιοκτήτη;",
    "Είναι λογικό το ενοίκιο;",
    "Τι να προσέξω στο συμβόλαιο;",
)


def _assistant():
    return guide._assistant()


def _rules() -> str:
    a = _assistant()
    unknown = getattr(a, "UNKNOWN", "δεν το ξέρω από τα δεδομένα")
    return f"""Είσαι ο βοηθός ενός Έλληνα που ψάχνει ΕΝΑ σπίτι να νοικιάσει στη ΒΑ Αθήνα για να \
μείνει. Μιλάς σαν φίλος που έχει ανοιχτό το λογιστικό φύλλο: σύντομα, με αριθμούς, συγκρίνοντας.

Κανόνες (αυστηροί):
1. Χρησιμοποίησε ΜΟΝΟ αριθμούς που υπάρχουν αυτούσιοι στο JSON. Μην υπολογίζεις νέους.
2. Αν τα δεδομένα δεν το λένε, γράψε «{unknown}» και πες τι να ρωτήσει τον ιδιοκτήτη ή τον \
μεσίτη: εγγύηση (πόσα ενοίκια), κοινόχρηστα και θέρμανση (ποσό τον μήνα, ποιος πληρώνει), \
διάρκεια συμβολαίου (συνήθως 3 χρόνια) και αυξήσεις, πιστοποιητικό ενεργειακής απόδοσης (ΠΕΑ), \
αμοιβή μεσίτη, πότε είναι διαθέσιμο.
3. Δεν μιλάς για απόδοση, επένδυση, αγορά ή δάνειο: ο χρήστης νοικιάζει.
4. Κανένα επίθετο αξιολόγησης, καμία φράση-γέμισμα, κανένα emoji, καμία εισαγωγή.
5. Μόνο ελληνικά, χωρίς ονόματα πεδίων του JSON. Αριθμοί ελληνικά (1.234 €, 4,7 %). Όροι: \
Ενοίκιο, €/τ.μ., Παρόμοια ενοίκια, μέρες στην αγορά. Τα ενοίκια είναι ζητούμενα ενοίκια \
αγγελιών, όχι συμβόλαια. Το seller_text είναι κείμενο του ιδιοκτήτη, όχι επαληθευμένο γεγονός.
6. Ενοίκιο πάνω από 35 % κάτω από τα παρόμοια = πες πρώτα να ελέγξει ότι η αγγελία υπάρχει.
7. Έως 120 λέξεις (στις ερωτήσεις έως 90). Τα σπίτια τα λες #1, #2… με τη σειρά του JSON."""


BRIEF_TASK = """Γράψε το «Σημείωμα»: 4 γραμμές, χωρίς τίτλο, έως 25 λέξεις η καθεμία.
- Γραμμή 1: το δίλημμα ανάμεσα στα #1–#3 σε αριθμούς (ενοίκιο, €/τ.μ. έναντι παρόμοιων, \
μέρες στην αγορά).
- Μία γραμμή για καθένα από τα #1–#3: το ΕΝΑ πράγμα να ρωτήσεις τον ιδιοκτήτη (εγγύηση, \
κοινόχρηστα, διάρκεια συμβολαίου, ΠΕΑ) με βάση ό,τι λείπει από τα δεδομένα.
Αν υπάρχουν λιγότερα από 3 σπίτια, γράψε μόνο για όσα υπάρχουν."""


def rent_facts(shown: list[picks_rent.RentPick], r: dict, all_rentals: list[dict]) -> dict:
    """Compact, JSON-able facts for the assistant: ``listings`` built from up to ten picks,
    the renter's answers (``mode: "rent"``) and the areas they are in."""
    rows = []
    for i, p in enumerate(shown[:10], start=1):
        d = p.listing
        rows.append(
            {
                "rank": i,
                "area": area_insights.area_name(d.get("neighborhood")),
                "neighbourhood": d.get("neighborhood"),
                "rent_eur_month": d.get("price"),
                "m2": d.get("area_m2"),
                "rent_per_m2": round(p.rent_per_m2, 1),
                "comps": (
                    {"median_rent_per_m2": round(p.comps_ppm, 1), "n": p.comps_n,
                     "where": p.comps_where}  # fmt: skip
                    if p.comps_ppm
                    else None
                ),
                "vs_comps_pct": round(p.vs_area_pct * 100) if p.vs_area_pct is not None else None,
                "days_on_market": (
                    {"days": p.dom, "basis": d.get("dom_basis")} if p.dom is not None else None
                ),
                "relisted_on": _day(d.get("relisted_on")),
                "floor": d.get("floor"),
                "year_built": d.get("year_built"),
                "bedrooms": d.get("bedrooms"),
                "furnished": d.get("furnished"),
                "available_from": _day(d.get("available_from")),
                "energy_class": d.get("energy_class"),
                "private_owner": d.get("is_private_seller"),
                "station": p.station or None,
                "photo_count": d.get("photo_count"),
                "over_budget_eur": p.over_budget or None,
                "risks": p.risks,
                "seller_text": picks.excerpt(d.get("description")),
            }
        )
    wanted = {row["area"] for row in rows}
    areas = []
    for a in sorted(wanted):
        xs = [
            picks_rent.ppm(d)
            for d in all_rentals
            if picks_rent.usable(d) and area_insights.area_name(d.get("neighborhood")) == a
        ]
        if xs:
            areas.append(
                {"area": a, "active_rentals": len(xs), "median_rent_per_m2": round(statistics.median(xs), 1)}  # fmt: skip
            )
    renter = {
        "mode": "rent",
        "budget_eur_month": r.get("budget"),
        "band_pct": round(picks_rent.BUDGET_BAND * 100),
        "bedrooms": BEDS.get(r.get("beds") or "", None),
        "where": guide.WHERE.get(r.get("where") or ""),
        "areas": r.get("areas") or None,
        "max_age": r.get("age"),
        "furnished_only": bool(r.get("furnished")),
    }
    return {
        "today": date.today().isoformat(),
        "mode": "rent",
        "renter": {k: v for k, v in renter.items() if v not in (None, "", [])},
        "listings": rows,
        "areas": areas,
    }


def _call(system: str, messages: list[dict], max_tokens: int, cache_key: str) -> str | None:
    a = _assistant()
    if a is None:
        return None
    cache = a._cache()
    if cache_key not in cache:
        resp = a._client().messages.create(**a._request(system, messages, max_tokens))
        text = a._text(resp)
        if not text:
            return None
        cache[cache_key] = text
    return cache[cache_key]


def _facts_block(facts: dict) -> str:
    import json

    return "Δεδομένα (JSON):\n" + json.dumps(facts, ensure_ascii=False, default=str)


def rent_brief(facts: dict) -> str | None:
    """The four-line note for renters, grounding-checked; None without a key or listings."""
    a = _assistant()
    if a is None or not facts.get("listings") or not a.enabled():
        return None
    msg = {"role": "user", "content": _facts_block(facts) + "\n\n" + BRIEF_TASK}
    try:
        text = _call(_rules(), [msg], a.BRIEF_MAX_TOKENS, "rent-brief:" + a.facts_hash(facts))
    except Exception:
        return None
    return a.checked(text, facts) if text else None


def rent_ask(facts: dict, question: str, history: list[dict]) -> str:
    a = _assistant()
    past = [{"role": m["role"], "content": m["content"]} for m in history[-12:]]
    msgs = [*past, {"role": "user", "content": question}]
    system = _rules() + "\n\n" + _facts_block(facts)
    key = "rent-ask:" + a.facts_hash(facts, question)
    try:
        text = _call(system, msgs, a.MAX_TOKENS, key)
    except Exception as e:
        return f"Ο βοηθός δεν απάντησε ({buyer._reason(e)}). Δοκίμασε ξανά."
    return a.checked(text or a.UNKNOWN, facts)


def _brief(facts: dict) -> None:
    if text := rent_brief(facts):
        with st.container(border=True, key="guide-brief"):
            st.markdown("**Σημείωμα**")
            st.markdown(html.escape(text))


def _panel(facts: dict) -> None:
    """«Ρώτα με» for renters: suggestion chips + a question box; hidden without a key."""
    a = _assistant()
    if a is None or not a.enabled() or not facts.get("listings"):
        return
    turns: list[dict] = st.session_state.setdefault("rent_turns", [])

    def _chip() -> None:
        st.session_state["rent_pending"] = st.session_state.get("rent_ask_chip")
        st.session_state["rent_ask_chip"] = None

    with st.container(border=True, key="rent-ask"):
        st.markdown("**Ρώτα με**")
        for m in turns:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
        st.pills(
            "Προτάσεις",
            SUGGESTIONS,
            key="rent_ask_chip",
            on_change=_chip,
            label_visibility="collapsed",
        )
        typed = st.chat_input("Ρώτα με", key="rent_ask_input")
        question = typed or st.session_state.pop("rent_pending", None)
        if question:
            reply = rent_ask(facts, question, turns)
            for role, text in (("user", question), ("assistant", reply)):
                with st.chat_message(role):
                    st.markdown(text)
            turns.extend(
                [{"role": "user", "content": question}, {"role": "assistant", "content": reply}]
            )
            del turns[: max(0, len(turns) - 12)]


# ---- screens -------------------------------------------------------------------------------


def mode_step(g: dict) -> None:
    """Step 0: buy or rent."""
    st.markdown("### Τι ψάχνεις;")
    with st.container(key="guide-mode"):
        for k, label in MODES.items():
            guide._choice(label, f"guide-mode-{k}", set_mode, (k,), g.get("mode") == k)


def _progress(step: int) -> None:
    with st.container(key="guide-progress"):
        c = st.columns([1, 2], vertical_alignment="center")
        c[0].button("Πίσω", key="guide-back", on_click=go, args=(step - 1,))
        c[1].markdown(f"**Βήμα {step} από {STEPS}**")
    st.progress(step / STEPS)


def _step1(r: dict) -> None:
    st.markdown("### Πόσο τον μήνα;")
    with st.container(key="guide-rbudgets"):
        for row in range(0, len(BUDGETS), 2):
            cols = st.columns(2)
            for c, k in zip(cols, BUDGETS[row : row + 2], strict=True):
                with c:
                    guide._choice(
                        eur(k), f"guide-rb{k}", answer, ("budget", k, 2), r.get("budget") == k
                    )
    with st.expander("Άλλο ποσό"):
        st.session_state.setdefault("rent_other", r.get("budget") or 800)
        st.number_input("Ποσό (€/μήνα)", BUDGET_MIN, BUDGET_MAX, step=50, key="rent_other")
        st.button("Συνέχεια", key="guide-rother-go", on_click=_other_budget, width="stretch")
    st.caption(f"Δείχνω ενοίκια έως {round(picks_rent.BUDGET_BAND * 100)} % πάνω από το ποσό σου.")


def _step2(r: dict) -> None:
    st.markdown("### Πόσα υπνοδωμάτια;")
    with st.container(key="guide-rbeds"):
        keys = list(BEDS)
        for row in range(0, len(keys), 2):
            cols = st.columns(2)
            for c, k in zip(cols, keys[row : row + 2], strict=True):
                with c:
                    guide._choice(
                        BEDS[k], f"guide-rbd-{k}", answer, ("beds", k, 3), r.get("beds") == k
                    )


def _step3(r: dict, rows: list[dict]) -> None:
    st.markdown("### Πού;")
    with st.container(key="guide-rwhere"):
        for k, label in guide.WHERE.items():
            label = "Όλες οι περιοχές" if k == "best" else label
            guide._choice(label, f"guide-rw-{k}", _set_where, (k,), r.get("where") == k)
    if r.get("where") == "areas":
        options = covered_areas(rows)
        count = dict(options)
        st.session_state.setdefault("rent_areas", [a for a in r.get("areas", []) if a in count])
        st.pills(
            "Διάλεξε περιοχές",
            list(count),
            selection_mode="multi",
            format_func=lambda a: f"{a} ({count[a]})",
            key="rent_areas",
            on_change=_areas_picked,
        )
        st.caption("Σε παρένθεση: ενεργές αγγελίες ενοικίασης.")
        with st.container(key="guide-rareas-go"):
            st.button(
                "Συνέχεια",
                key="guide-rareas-next",
                on_click=go,
                args=(4,),
                type="primary",
                disabled=not r.get("areas"),
                width="stretch",
            )


def _step4(r: dict) -> None:
    st.markdown("### Τι σπίτι;")
    st.session_state.setdefault("rent_furn", bool(r.get("furnished")))
    st.toggle("Επιπλωμένο", key="rent_furn", on_change=_furn_changed)
    st.session_state.setdefault("rent_age", _age_code(r.get("age")))
    st.segmented_control(
        "Ηλικία κτιρίου", list(AGES), format_func=AGES.get, key="rent_age", on_change=_age_changed
    )
    with st.container(key="guide-rfinish"):
        st.button(
            "Η πρότασή μου",
            key="guide-rshow",
            on_click=answer,
            args=("step", 5),
            type="primary",
            width="stretch",
        )


METHOD = f"""
- **Σειρά**: πρώτα όσες έχουν το χαμηλότερο ενοίκιο ανά τ.μ. σε σχέση με τα παρόμοια, μετά οι
  πιο πρόσφατες αγγελίες. Όσες είναι πάνω από {round(picks_rent.TOO_CHEAP * 100)} % κάτω από τα
  παρόμοια πάνε μετά (συχνά δωμάτιο, λάθος τιμή ή αγγελία που δεν υπάρχει), όσες δεν έχουν
  παρόμοια στο τέλος.
- **Παρόμοια ενοίκια**: διάμεσο €/τ.μ. των άλλων ενεργών αγγελιών ενοικίασης στην ίδια γειτονιά
  (τουλάχιστον {picks_rent.MIN_COMPS}), αλλιώς στην ευρύτερη περιοχή.
- **Ποσό**: ενοίκια έως {round(picks_rent.BUDGET_BAND * 100)} % πάνω από το ποσό σου.
- **Μέρες στην αγορά**: από την ημερομηνία της αγγελίας, αλλιώς από τότε που τη βλέπουμε.
- **Σταθμός**: απόσταση με τα πόδια όταν η αγγελία έχει ακριβή θέση, αλλιώς από το όνομα της
  γειτονιάς.
- Ζητούμενα ενοίκια αγγελιών, όχι συμβόλαια. Δεν ξέρουμε εγγύηση, κοινόχρηστα και διάρκεια
  συμβολαίου: ρώτα τον ιδιοκτήτη.
"""


def card_more(p: picks_rent.RentPick) -> list[str]:
    """What sits behind «Από πού βγαίνουν» on the rent card: the four checks, the risks,
    furnished / available from, the listing's own words and the basis of the comparison."""
    d = p.listing
    more = [d["title"]] if d.get("title") else []
    more += [f"{k}: {v}" for k, v in p.checks]
    more += [f"Έλεγξε: {r}" for r in p.risks]
    if d.get("furnished"):
        more.append("Επιπλωμένο")
    if avail := _day(d.get("available_from")):
        more.append(f"Διαθέσιμο από {avail}")
    if text := picks.excerpt(d.get("description")):
        more.append(f"Τι λέει η αγγελία: «{text}»")
    if p.comps_ppm:
        more.append(
            f"Παρόμοια ενοίκια: διάμεσο €/τ.μ. των {p.comps_n} άλλων ενεργών αγγελιών "
            f"ενοικίασης ({p.comps_where})."
        )
    more.append("Ενοίκιο: αυτό που ζητά η αγγελία, όχι συμβόλαιο.")
    return more


def card_adv(p: picks_rent.RentPick) -> dict:
    """Line 5 of the compact card (``buyer.comps_text``) from the rental comparables."""
    if p.vs_area_pct is None:
        return {}
    return {"cmp": {"pct": p.vs_area_pct, "n": p.comps_n, "ppm": p.comps_ppm}}


def card(i: int | None, p: picks_rent.RentPick, k: str, verdicts: bool = False,
         approved: bool = False) -> None:  # fmt: skip
    """The compact rent card (C3's five lines) and its buttons: «Λεπτομέρειες» (inline: the
    listing page is for sales) and «Αγαπημένο», then «Εγκρίνω» / «Δεν μου κάνει» when
    ``verdicts``."""
    d = p.listing
    lid = d["id"]
    with st.container(border=True, key=f"pick-{k}{lid}"):
        st.markdown(
            buyer.card_html(
                d, card_adv(p), False, compact=True, lead=f"{i}." if i else "", more=card_more(p)
            ),
            unsafe_allow_html=True,
        )
        if lid in st.session_state.get("rent_details", set()):
            _details(d)
        star, toggle, args, kind = buyer._star_action(d)
        cols = st.columns(2)
        cols[0].button(
            "Λεπτομέρειες", key=f"{k}-det-{lid}", on_click=_toggle_details, args=(lid,),
            width="stretch",
        )  # fmt: skip
        cols[1].button(
            star, key=f"{k}-star-{lid}", on_click=toggle, args=args, type=kind, width="stretch"
        )
        if not verdicts and not approved:
            return
        key = shortlist.lkey(d)
        cols = st.columns(2)
        if approved:
            cols[0].button("Αναίρεση", key=f"{k}-undo-{lid}", on_click=guide.set_verdict,
                           args=(key, None), width="stretch")  # fmt: skip
        else:
            cols[0].button("Εγκρίνω", key=f"{k}-ok-{lid}", on_click=guide.set_verdict,
                           args=(key, "ok"), type="primary", width="stretch")  # fmt: skip
        cols[1].button("Δεν μου κάνει", key=f"{k}-no-{lid}", on_click=guide.set_verdict,
                       args=(key, "no"), width="stretch")  # fmt: skip


def _details(d: dict) -> None:
    facts = [
        ("Υπνοδωμάτια", str(d["bedrooms"]) if d.get("bedrooms") else "άγνωστο"),
        ("Ανακαίνιση", str(d["renovated_year"]) if d.get("renovated_year") else "άγνωστο"),
        ("Επιπλωμένο", {True: "ναι", False: "όχι"}.get(d.get("furnished"), "άγνωστο")),
        ("Διαθέσιμο από", _day(d.get("available_from")) or "άγνωστο"),
        ("Φωτογραφίες", str(d["photo_count"]) if d.get("photo_count") else "άγνωστο"),
    ]
    st.markdown(
        '<div class="hg-card">'
        + "".join(f"<div>{html.escape(k)}: {html.escape(v)}</div>" for k, v in facts)
        + "</div>",
        unsafe_allow_html=True,
    )
    src = guide.SOURCES.get(d.get("source") or "xe", (d.get("source") or "").upper())
    st.link_button(f"Άνοιγμα στο {src}", d["url"], width="stretch")
    st.caption(
        "Ρώτα τον ιδιοκτήτη: εγγύηση, κοινόχρηστα και θέρμανση, διάρκεια συμβολαίου, "
        "πιστοποιητικό ενεργειακής απόδοσης."
    )


def _relax(options: list[picks_rent.Relax], intro: str) -> None:
    with st.container(border=True, key="guide-relax"):
        st.markdown(intro)
        for i, x in enumerate(options):
            st.button(
                x.text, key=f"rent-relax-{i}", on_click=apply_relax, args=(x.changes,),
                width="stretch",
            )  # fmt: skip


def _dropped(rows: list[picks_rent.RentPick]) -> None:
    with st.expander(f"Απέρριψες {len(rows)}"):
        for p in rows:
            d = p.listing
            c = st.columns([3, 1])
            c[0].markdown(
                f"[{eur(d['price'])}/μήνα · {buyer._m2(d['area_m2'])} τ.μ. · "
                f"{html.escape(d.get('neighborhood') or '')}]({d['url']})"
            )
            c[1].button("Επαναφορά", key=f"rent-back-{d['id']}", on_click=guide.set_verdict,
                        args=(shortlist.lkey(d), None), width="stretch")  # fmt: skip


def _results(r: dict, rows: list[dict]) -> None:
    st.markdown("### Η πρότασή μου")
    st.session_state["rent_chips"] = None
    st.pills(
        "Οι απαντήσεις σου",
        answer_chips(r),
        key="rent_chips",
        on_change=_chip_jump,
        label_visibility="collapsed",
    )
    budget = int(r.get("budget") or 800)
    where = r.get("where") or "best"
    rules = dict(
        bedrooms=bedrooms(r),
        near_rail=where == "rail",
        areas=(r.get("areas") or None) if where == "areas" else None,
        max_age=r.get("age"),
        furnished=bool(r.get("furnished")),
    )
    found = picks_rent.find(rows, budget, **rules, top=10**6)
    review = guide._review()
    every, dropped = guide.arrange(found, review)
    what = f"έως {eur(budget * (1 + picks_rent.BUDGET_BAND))}/μήνα (το ποσό σου + 10 %)" + (
        ", κοντά σε σταθμό" if where == "rail" else ""
    )
    relax = picks_rent.relaxations(rows, budget, **rules) if len(every) < picks.PAGE else []
    if not every:
        st.markdown(f"Καμία αγγελία ενοικίασης {what}.")
        if relax:
            _relax(relax, "Χαλάρωσε έναν όρο — σε παρένθεση πόσες αγγελίες προστίθενται:")
        else:
            st.info("Ούτε με έναν όρο λιγότερο βρίσκω κάτι. Άλλαξε το ποσό.")
    else:
        if sentence := recommend(every):
            st.markdown(sentence)
        st.markdown(f"**{len(every)}** αγγελίες ενοικίασης {what}.")
        if relax:
            _relax(
                relax, f"Μόνο {len(every)}. Με έναν όρο λιγότερο (σε παρένθεση πόσες προστίθενται):"
            )
        facts = rent_facts(every, r, rows)
        _brief(facts)
        n = st.session_state.setdefault("rent_shown", picks.PAGE)
        visible = every[:n]
        for i, p in enumerate(visible, start=1):
            ok = review.get(shortlist.lkey(p.listing)) == "ok"
            card(i, p, "rent", verdicts=i <= picks.PAGE, approved=ok)
        if len(every) > n:
            with st.container(key="guide-rmore"):
                st.button(
                    f"Δείξε άλλες {min(picks.PAGE, len(every) - n)}",
                    key="guide-rmore-btn",
                    on_click=_more,
                    width="stretch",
                )
        st.caption(f"Βλέπεις {len(visible)} από {len(every)}.")
        _panel(facts)
    if dropped:
        _dropped(dropped)
    with st.expander("Πώς υπολογίζω"):
        st.markdown(METHOD)
    st.caption(coverage(rows))
    if guide._store() is None:
        st.caption("Οι απαντήσεις κρατιούνται μόνο σε αυτή τη συνεδρία.")


def page(g: dict) -> None:
    """The rent flow (the guide's title, CSS and flash are already on the page)."""
    r = rstate()
    rows = rentals()
    step = int(r.get("step") or 1)
    if step > 1 and not r.get("budget"):
        step = 1
    if step > 2 and not r.get("beds"):
        step = 2
    if step > 3 and (not r.get("where") or (r["where"] == "areas" and not r.get("areas"))):
        step = 3
    _progress(step)
    if not rows:  # no loader, or no rental stored yet
        st.info(SOON)
        return
    if step == 1:
        _step1(r)
    elif step == 2:
        _step2(r)
    elif step == 3:
        _step3(r, rows)
    elif step == 4:
        _step4(r)
    else:
        _results(r, rows)
