"""«Οδηγός» — five one-question screens, then «Η πρότασή μου».

Phone-first and tap-only (the budget is the one number you may type): 1 budget (+ «με
δάνειο»), 2 what matters most (sets the ranking weights, ``picks.GOAL_WEIGHTS``), 3 where,
4 what kind of flat, 5 the answer — one sentence naming the area and its numbers, then the
ranking 10 at a time. The answers sit as chips on top of the answer; a chip reopens its
question. Engine: ``picks.find`` / ``picks.relaxations``.

Optional neighbours (other workstreams), each imported lazily and skipped when absent:
``ui.maplist.render(listings, key)`` (map toggle), ``ui.assistant.brief(facts)`` /
``panel(facts, key)`` (investor note, «Ρώτα με»), ``ui.account.storage()`` (answers kept in
the profile; otherwise this session only).
"""

from __future__ import annotations

import html
import statistics
from collections import Counter
from datetime import date

import streamlit as st

from scout import area_insights, market_intel, picks, shortlist
from scout.ui import buyer

TITLE = "Οδηγός"
STEPS = 5
BUDGETS = (150, 200, 250, 300, 400, 500)  # χιλ. €
BUDGET_MIN, BUDGET_MAX = 50_000, 2_000_000
GOALS = {
    "yield": "Απόδοση ενοικίου",
    "safety": "Σιγουριά & εύκολη ενοικίαση",
    "growth": "Ανατίμηση (μετρό, ανάπτυξη περιοχής)",
}
GOAL_HINT = {
    "yield": "Πρώτα όσα βγάζουν το μεγαλύτερο ενοίκιο για την τιμή τους.",
    "safety": "Πρώτα ελεγμένες αγγελίες με φωτογραφίες, σε περιοχές με πολλές αγγελίες.",
    "growth": "Πρώτα δίπλα σε σταθμό ή σε μελλοντικό σταθμό της Γραμμής 4.",
}
GOAL_CHIP = {"yield": "απόδοση", "safety": "σιγουριά", "growth": "ανατίμηση"}
WHERE = {
    "rail": "Κοντά σε μετρό/ΗΣΑΠ",
    "areas": "Συγκεκριμένες περιοχές",
    "best": "Όπου βγαίνει ο καλύτερος αριθμός",
}
AGES = {"10": "Νεόδμητο (έως 10 ετών)", "20": "Έως 20 ετών", "any": "Οτιδήποτε"}
BEDS = {"any": "Όσα να 'ναι", "1": "1", "2": "2", "3": "3+"}
MIN_AREA = 20  # an area is offered as a chip with at least this many active listings
DEFAULTS = {
    "step": 1,
    "budget": None,
    "loan": False,
    "goal": None,
    "where": None,
    "areas": [],
    "age": picks.NEW_YEARS,
    "bedrooms": None,
}
SOURCES = {
    "xe": "XE.gr",
    "spitogatos": "Spitogatos.gr",
    "indomio": "Indomio.gr",
    "greenacres": "Green-Acres",
}

# Big tap targets; keep 2-up button rows side by side on a 390 px phone (Streamlit would stack
# them into full-width rows).
CSS = """<style>
[class*="st-key-guide-"] button { min-height: 3rem; font-size: 1.02rem; }
[class*="st-key-guide-"] [data-testid="stHorizontalBlock"],
[class*="st-key-pick-"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: .5rem; }
[class*="st-key-guide-"] [data-testid="stColumn"],
[class*="st-key-pick-"] [data-testid="stColumn"] { min-width: 0; width: auto; flex: 1 1 0; }
</style>"""


# ---- optional neighbours -------------------------------------------------------------------


def _maplist():
    try:
        from scout.ui import maplist
    except ImportError:
        return None
    return maplist if callable(getattr(maplist, "render", None)) else None


def _assistant():
    try:
        from scout.ui import assistant
    except ImportError:
        return None
    return assistant


def _store():
    """The signed-in profile's store (``account.storage()``), or None = this session only."""
    try:
        from scout.ui import account
    except ImportError:
        return None
    try:
        return account.storage()
    except Exception:
        return None


def _load_saved() -> dict | None:
    s = _store()
    if s is None:
        return None
    try:
        got = s.get("guide") if hasattr(s, "get") else None
    except Exception:
        return None
    return dict(got) if isinstance(got, dict) else None


def _save(g: dict) -> None:
    s = _store()
    if s is None:
        return
    try:
        if hasattr(s, "set"):
            s.set("guide", dict(g))
        else:
            s["guide"] = dict(g)
    except Exception as e:  # keep working; the answers still live in this session
        buyer._flash("error", f"Οι απαντήσεις δεν αποθηκεύτηκαν ({buyer._reason(e)}).")


# ---- state ---------------------------------------------------------------------------------


def state() -> dict:
    if "guide" not in st.session_state:
        st.session_state["guide"] = {**DEFAULTS, **(_load_saved() or {})}
    return st.session_state["guide"]


def _changed(g: dict) -> None:
    st.session_state["guide_shown"] = picks.PAGE
    if g.get("budget"):
        st.session_state["find_budget"] = g["budget"]  # «Πού να αγοράσω» reads it
    _save(g)


WIDGETS = ("guide_loan", "guide_other", "guide_areas", "guide_age", "guide_beds")


def _resync() -> None:
    """Drop the step widgets' own state so they re-read the answers (after a jump/relax)."""
    for k in WIDGETS:
        st.session_state.pop(k, None)


def go(step: int) -> None:
    _resync()
    g = state()
    g["step"] = max(1, min(STEPS, step))
    _save(g)


def answer(field: str, value, next_step: int | None = None) -> None:
    g = state()
    g[field] = value
    if next_step:
        g["step"] = next_step
    _changed(g)


def _set_where(value: str) -> None:
    answer("where", value, None if value == "areas" else 4)


def _other_budget() -> None:
    answer("budget", int(st.session_state["guide_other"]), 2)


def _loan_toggled() -> None:
    answer("loan", bool(st.session_state["guide_loan"]))


def _areas_picked() -> None:
    answer("areas", list(st.session_state.get("guide_areas") or []))


def _age_code(age: int | None) -> str:
    return "any" if age is None else ("10" if age <= picks.NEW_YEARS else "20")


def _beds_code(beds: int | None) -> str:
    return "any" if beds is None else str(min(beds, 3))


def _kind_changed(key: str) -> None:
    """Tapping the selected option of a segmented control clears it: keep the answer."""
    g = state()
    v = st.session_state.get(key)
    if key == "guide_age":
        if v is None:
            st.session_state[key] = _age_code(g.get("age"))
        else:
            g["age"] = None if v == "any" else int(v)
    elif v is None:
        st.session_state[key] = _beds_code(g.get("bedrooms"))
    else:
        g["bedrooms"] = None if v == "any" else int(v)


def _finish_step4() -> None:
    g = state()
    g["step"] = 5
    _changed(g)


def _chip_jump() -> None:
    pick = st.session_state.get("guide_chips")
    st.session_state["guide_chips"] = None
    for i, label in enumerate(answer_chips(state()), start=1):
        if label == pick:
            go(i)


def apply_relax(changes: dict) -> None:
    """A tapped relaxation (``picks.Relax.changes``) → the guide's answers."""
    _resync()
    g = state()
    for k, v in changes.items():
        if k == "budget":
            g["budget"] = min(int(v), BUDGET_MAX)
        elif k == "max_age":
            g["age"] = v
        elif k == "near_rail" and not v:
            g["where"] = "best"
        elif k == "areas" and not v:
            g["where"], g["areas"] = "best", []
        elif k == "bedrooms":
            g["bedrooms"] = v
    _changed(g)


# ---- words ---------------------------------------------------------------------------------


def thousands(budget: int) -> str:
    return f"{budget / 1000:g}".replace(".", ",") + " χιλ."


def age_text(age: int | None) -> str:
    if age is None:
        return "οποιαδήποτε ηλικία"
    return "νεόδμητο" if age == picks.NEW_YEARS else f"έως {age} ετών"


def answer_chips(g: dict) -> list[str]:
    """One chip per answered question (steps 1–4), in order: «300 χιλ. · με δάνειο», …"""
    where = {
        "rail": "κοντά σε μετρό",
        "best": "όπου βγαίνει",
        "areas": ", ".join(g.get("areas") or []) or "περιοχές",
    }
    beds = g.get("bedrooms")
    kind = age_text(g.get("age")) + (
        f" · {beds}{'+' if beds >= 3 else ''} υπν." if beds is not None else ""
    )
    return [
        (thousands(g["budget"]) if g.get("budget") else "ποσό;")
        + (" · με δάνειο" if g.get("loan") else ""),
        GOAL_CHIP.get(g.get("goal") or "", "στόχος;"),
        where.get(g.get("where") or "", "πού;"),
        kind,
    ]


def covered_areas(listings: list[dict]) -> list[tuple[str, int]]:
    """(area, active listings) with at least MIN_AREA active, most first."""
    n = Counter(
        area_insights.area_name(d.get("neighborhood"))
        for d in listings
        if d.get("is_fresh", True) and d.get("neighborhood")
    )
    return [(a, c) for a, c in n.most_common() if c >= MIN_AREA]


def recommend(found: list[picks.Pick], facts: dict, goal: str) -> str | None:
    """One sentence: the area the list points to for ``goal`` and the numbers behind it.

    Candidates are the areas of the listed flats; yield → highest median gross yield of the
    flats there; safety → most active listings in the area (``AreaInsight.n_fresh``, else the
    flats listed); growth → highest median growth points, then yield."""
    if not found:
        return None
    by: dict[str, list[picks.Pick]] = {}
    for p in found:
        by.setdefault(area_insights.area_name(p.listing.get("neighborhood")), []).append(p)

    def med(ps, f):
        return statistics.median(f(p) for p in ps)

    def size(a):
        x = facts.get(a)
        return x.n_fresh if x is not None else len(by[a])

    keys = {
        "yield": lambda a: (med(by[a], lambda p: p.gross), len(by[a])),
        "safety": lambda a: (size(a), med(by[a], lambda p: p.parts.get("safety", 0))),
        "growth": lambda a: (
            med(by[a], lambda p: p.parts.get("growth", 0)),
            med(by[a], lambda p: p.gross),
        ),
    }
    area = max(by, key=keys.get(goal, keys["yield"]))
    ps, x = by[area], facts.get(area)
    out = (
        f"Πρόταση: **{html.escape(area)}** — {len(ps)} από τις {len(found)} αγγελίες της λίστας, "
        f"διάμεση μικτή απόδοση τους {picks.gr_pct(med(ps, lambda p: p.gross))}"
    )
    extra = []
    if goal == "yield" and x is not None and x.rent_ppm:
        n = f" από {x.rent_samples} αγγελίες ενοικίασης" if x.rent_samples else ""
        extra.append(f"ενοίκιο περιοχής {picks.gr_num(x.rent_ppm)} €/τ.μ.{n}")
    if goal == "safety" and x is not None:
        extra.append(f"{x.n_fresh} αγγελίες πώλησης στην περιοχή")
        if x.median_dom:
            extra.append(f"διάμεσα {x.median_dom:.0f} μέρες στην αγορά")
    if goal == "growth":
        stations = sorted({p.station for p in ps if p.station})
        if stations:
            extra.append(", ".join(stations[:2]))
        if l4 := picks.line4_station(area):
            extra.append(f"Γραμμή 4: {l4}")
        if x is not None and x.new_premium is not None:
            extra.append(f"νεόδμητα {round(x.new_premium * 100):+d} % από τα παλιά")
    out += " · " + " · ".join(extra) if extra else ""
    return out if out.endswith(".") else out + "."


def facts_for(shown: list[picks.Pick], g: dict, area_facts: dict, intel) -> dict:
    """What the assistant may quote: the answers and the numbers we computed for the top 3."""
    rows = []
    for p in shown[:3]:
        d = p.listing
        cmp = intel.comps(d)
        area = area_insights.area_name(d.get("neighborhood"))
        x = area_facts.get(area)
        rows.append(
            {
                "τίτλος": d.get("title"),
                "περιοχή": area,
                "γειτονιά": d.get("neighborhood"),
                "τιμή": d.get("price"),
                "τ.μ.": d.get("area_m2"),
                "€/τ.μ.": round(d["price"] / d["area_m2"]),
                "παρόμοια_διάμεσος_€/τ.μ.": round(cmp["ppm"]) if cmp else None,
                "παρόμοια_n": cmp["n"] if cmp else None,
                "ενοίκιο_εκτίμηση_€/μήνα": p.rent,
                "ενοίκιο_βάση": p.lines[0] if p.lines else None,
                "μικτή_απόδοση": round(p.gross, 4),
                "καθαρή_απόδοση": round(p.net, 4),
                "μέρες_στην_αγορά": d.get("days_on_market"),
                "μέρες_βάση": d.get("dom_basis"),
                "κατάσταση": p.status,
                "φωτογραφίες": d.get("photo_count"),
                "σταθμός": p.station,
                "γραμμή_4": picks.line4_station(area),
                "προσφορά_αφετηρία": p.offer,
                "δόση_δανείου_€/μήνα": p.instalment if g.get("loan") else None,
                "ενοίκιο_μείον_δόση": p.cashflow if g.get("loan") else None,
                "κίνδυνοι": p.risks,
                "περιοχή_απόδοση": x.gross_yield if x is not None else None,
                "περιοχή_αγγελίες": x.n_fresh if x is not None else None,
                "περιοχή_διάμεσες_μέρες": x.median_dom if x is not None else None,
                "περιοχή_premium_νεόδμητων": x.new_premium if x is not None else None,
            }
        )
    return {
        "απαντήσεις": {
            "προϋπολογισμός": g.get("budget"),
            "δάνειο": bool(g.get("loan")),
            "στόχος": GOALS.get(g.get("goal") or ""),
            "πού": WHERE.get(g.get("where") or ""),
            "περιοχές": g.get("areas") or [],
            "ηλικία": age_text(g.get("age")),
            "υπνοδωμάτια": g.get("bedrooms"),
        },
        "αγγελίες": rows,
    }


def coverage(listings: list[dict]) -> str:
    srcs = sorted({SOURCES.get(d.get("source") or "", d.get("source") or "") for d in listings})
    active = sum(1 for d in listings if d.get("is_fresh", True))
    checked = sum(1 for d in listings if d.get("page_checked"))
    return (
        f"Πηγές: {', '.join(s for s in srcs if s) or 'XE.gr'} · "
        f"{buyer._num(active)} αγγελίες ενεργές · {buyer._num(checked)} ελεγμένες σελίδες"
    )


# ---- verdicts (✓ / ✗) ----------------------------------------------------------------------


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


def _on_map(listing_id: int) -> None:
    st.session_state["selected_id"] = listing_id
    st.session_state["guide_map"] = True


def _more() -> None:
    st.session_state["guide_shown"] = st.session_state.get("guide_shown", picks.PAGE) + picks.PAGE


# ---- screens -------------------------------------------------------------------------------


def _progress(step: int) -> None:
    with st.container(key="guide-progress"):
        c = st.columns([1, 2], vertical_alignment="center")
        if step > 1:
            c[0].button("← Πίσω", key="guide-back", on_click=go, args=(step - 1,))
        c[1].markdown(f"**Βήμα {step} από {STEPS}**")
    st.progress(step / STEPS)


def _choice(label: str, key: str, cb, args: tuple, on: bool) -> None:
    kind = "primary" if on else "secondary"
    st.button(label, key=key, on_click=cb, args=args, type=kind, width="stretch")


def _step1(g: dict) -> None:
    st.markdown("### Πόσα θες να βάλεις;")
    st.session_state.setdefault("guide_loan", bool(g.get("loan")))
    st.toggle("Με δάνειο", key="guide_loan", on_change=_loan_toggled)
    if st.session_state["guide_loan"]:
        st.caption(
            f"Δάνειο {round(picks.LTV * 100)} % της τιμής, επιτόκιο 4 %, {picks.YEARS} χρόνια. "
            "Δείχνω τη μηνιαία δόση δίπλα στο ενοίκιο."
        )
    with st.container(key="guide-budgets"):
        for row in range(0, len(BUDGETS), 2):
            cols = st.columns(2)
            for c, k in zip(cols, BUDGETS[row : row + 2], strict=True):
                with c:
                    _choice(
                        f"{k} χιλ. €",
                        f"guide-b{k}",
                        answer,
                        ("budget", k * 1000, 2),
                        g.get("budget") == k * 1000,
                    )
    with st.expander("Άλλο ποσό"):
        st.session_state.setdefault("guide_other", g.get("budget") or 300_000)
        st.number_input("Ποσό (€)", BUDGET_MIN, BUDGET_MAX, step=10_000, key="guide_other")
        st.button("Συνέχεια", key="guide-other-go", on_click=_other_budget, width="stretch")


def _step2(g: dict) -> None:
    st.markdown("### Τι σε νοιάζει πιο πολύ;")
    with st.container(key="guide-goals"):
        for k, label in GOALS.items():
            _choice(label, f"guide-g-{k}", answer, ("goal", k, 3), g.get("goal") == k)
            st.caption(GOAL_HINT[k])


def _step3(g: dict, listings: list[dict]) -> None:
    st.markdown("### Πού;")
    with st.container(key="guide-where"):
        for k, label in WHERE.items():
            _choice(label, f"guide-w-{k}", _set_where, (k,), g.get("where") == k)
    if g.get("where") == "areas":
        options = covered_areas(listings)
        count = dict(options)
        st.session_state.setdefault("guide_areas", [a for a in g.get("areas", []) if a in count])
        st.pills(
            "Διάλεξε περιοχές",
            list(count),
            selection_mode="multi",
            format_func=lambda a: f"{a} ({count[a]})",
            key="guide_areas",
            on_change=_areas_picked,
        )
        st.caption("Σε παρένθεση: ενεργές αγγελίες πώλησης.")
        with st.container(key="guide-areas-go"):
            st.button(
                "Συνέχεια",
                key="guide-areas-next",
                on_click=go,
                args=(4,),
                type="primary",
                disabled=not g.get("areas"),
                width="stretch",
            )


def _step4(g: dict) -> None:
    st.markdown("### Τι σπίτι;")
    st.session_state.setdefault("guide_age", _age_code(g.get("age")))
    st.session_state.setdefault("guide_beds", _beds_code(g.get("bedrooms")))
    for key, label, opts in (
        ("guide_age", "Ηλικία κτιρίου", AGES),
        ("guide_beds", "Υπνοδωμάτια", BEDS),
    ):
        st.segmented_control(
            label, list(opts), format_func=opts.get, key=key, on_change=_kind_changed, args=(key,)
        )
    with st.container(key="guide-finish"):
        st.button(
            "Η πρότασή μου →",
            key="guide-show",
            on_click=_finish_step4,
            type="primary",
            width="stretch",
        )


@st.cache_data(ttl=600, show_spinner=False)
def _rent_rows() -> list[dict]:
    from scout.ui import queries

    return queries.load_rent_comp_rows()


METHOD = """
- **Σειρά**: πρώτα όσες ελέγξαμε τη σελίδα, μετά όσες έχουν πάνω από 2 φωτογραφίες, μετά οι
  πόντοι του στόχου σου. Ο στόχος δεν ανεβάζει ποτέ μη ελεγμένη πάνω από ελεγμένη.
- **Πόντοι**: απόδοση = 1000 × μικτή απόδοση (4,5 % → 45)· τιμή = σε σχέση με τα παρόμοια
  (−6 έως +10), +3 αν τελείωσε πριν από φέτος, +2 αν είναι 90+ μέρες στην αγορά, −20 αν είναι
  πάνω από 35 % φθηνότερο από τα παρόμοια· σιγουριά = 6 για καθένα από: ελεγμένη σελίδα,
  πάνω από 2 φωτογραφίες, ενεργειακή κλάση, 8+ παρόμοια, 50+ αγγελίες στην περιοχή, σταθερός
  χρόνος πώλησης στην περιοχή· ανατίμηση = 12 σταθμός σήμερα, 12 μελλοντικός σταθμός Γραμμής 4
  στην περιοχή, 6 αν τα νεόδμητα της περιοχής κοστίζουν έως 15 % πάνω από τα παλιά.
- **Βάρη ανά στόχο** (απόδοση · τιμή · σιγουριά · ανατίμηση): Απόδοση ενοικίου 1 · 1 · 0,25 ·
  0,25 — Σιγουριά 0,4 · 0,6 · 1 · 0,25 — Ανατίμηση 0,4 · 0,6 · 0,25 · 1.
- **Ενοίκιο (εκτίμηση)**: διάμεσο ζητούμενο ενοίκιο €/τ.μ. των αγγελιών ενοικίασης XE.gr στη
  γειτονιά (αλλιώς στην ευρύτερη περιοχή) × τ.μ., +10 % για κτίριο έως 5 ετών. Ζητούμενα
  ενοίκια, όχι συμβόλαια.
- **Μικτή απόδοση** = 12 × ενοίκιο ÷ τιμή. **Καθαρή απόδοση**: 11 μήνες ενοίκιο, −15 % φόρος,
  −5 % συντήρηση, −ΕΝΦΙΑ ~3 €/τ.μ. τον χρόνο, διά τιμή + έξοδα αγοράς.
- **Με δάνειο**: δόση = δάνειο 70 % της τιμής, 4 %, 25 χρόνια, σταθερή μηνιαία δόση· «μένουν»
  = ενοίκιο (εκτίμηση) − δόση, πριν από φόρους και έξοδα.
- **Προσφορά**: ζητούμενη τιμή −3 %, −3 % ακόμα στις 90+ μέρες, −2 % αν πουλάει ιδιώτης.
- **Σταθμός**: από το όνομα της γειτονιάς στο XE (δεν δίνει διεύθυνση).
- **Πρόταση περιοχής**: ανάμεσα στις περιοχές της λίστας — για απόδοση η μεγαλύτερη διάμεση
  μικτή απόδοση, για σιγουριά οι περισσότερες αγγελίες, για ανατίμηση οι περισσότεροι πόντοι.
- Τιμές: ζητούμενες τιμές XE.gr, όχι τιμές πώλησης.
"""


def _card(i: int, p: picks.Pick, approved: bool, adv: dict, has_map: bool) -> None:
    d = p.listing
    e = html.escape
    shown = {**d, "est_monthly_rent": p.rent, "rent_estimated": True, "listed_rent": None}
    with st.container(border=True, key=f"pick-{d['id']}"):
        st.markdown(f"**{i}. {e(d.get('title') or '')}**" + (" · το ενέκρινες" if approved else ""))
        st.markdown(buyer.card_html(shown, adv), unsafe_allow_html=True)
        lines = [f"Καθαρή απόδοση ~{picks.gr_pct(p.net)}"]
        if p.loan:
            lines.append(p.loan_line)
        why = p.reasons.get(p.goal) if p.goal in ("safety", "growth") else None
        if why:
            lines.append(f"{GOAL_CHIP[p.goal].capitalize()}: " + " · ".join(why))
        lines.append(
            f"Πρώτη προσφορά ~{buyer.eur(p.offer)}"
            + (" (ιδιώτης πωλητής)" if d.get("is_private_seller") else "")
        )
        st.markdown(
            '<div class="hg-card">' + "".join(f"<div>{e(x)}</div>" for x in lines) + "</div>",
            unsafe_allow_html=True,
        )
        if p.risks:
            st.markdown(
                '<div class="hg-card"><b>Έλεγξε</b><ul style="margin:2px 0 0;padding-left:1.1rem">'
                + "".join(f"<li>{e(r)}</li>" for r in p.risks)
                + "</ul></div>",
                unsafe_allow_html=True,
            )
        if p.excerpt:
            with st.expander("Τι λέει η αγγελία"):
                st.markdown(e(p.excerpt))
        key = shortlist.lkey(d)
        cols = st.columns(2)
        src = SOURCES.get(d.get("source") or "xe", (d.get("source") or "").upper())
        cols[0].link_button(f"Στο {src} ↗", d["url"], width="stretch")
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
                "↺ Αναίρεση",
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
            )
        cols[1].button(
            "✗ Δεν μου κάνει",
            key=f"pick-no-{d['id']}",
            on_click=set_verdict,
            args=(key, "no"),
            width="stretch",
        )
        if has_map:
            st.button(
                "Στον χάρτη",
                key=f"pick-map-{d['id']}",
                on_click=_on_map,
                args=(d["id"],),
                width="stretch",
            )


def _relax(options: list[picks.Relax], intro: str) -> None:
    with st.container(border=True, key="guide-relax"):
        st.markdown(intro)
        for i, r in enumerate(options):
            st.button(
                r.text, key=f"relax-{i}", on_click=apply_relax, args=(r.changes,), width="stretch"
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


def _assistant_brief(facts: dict) -> None:
    a = _assistant()
    if a is None or not callable(getattr(a, "brief", None)):
        return
    try:
        text = a.brief(facts)
    except Exception:
        return
    if text:
        with st.container(border=True, key="guide-brief"):
            st.markdown("**Σημείωμα επενδυτή**")
            st.markdown(html.escape(text))


def _assistant_panel(facts: dict) -> None:
    a = _assistant()
    if a is None or not callable(getattr(a, "panel", None)):
        return
    try:
        a.panel(facts, "guide")
    except Exception:
        return


def _results(g: dict, listings: list[dict]) -> None:
    st.markdown("### Η πρότασή μου")
    st.session_state["guide_chips"] = None
    st.pills(
        "Οι απαντήσεις σου",
        answer_chips(g),
        key="guide_chips",
        on_change=_chip_jump,
        label_visibility="collapsed",
    )
    budget = int(g.get("budget") or area_insights.DEFAULT_BUDGET)
    year = date.today().year
    rents = _rent_rows()
    intel = market_intel.build(listings)
    area_facts = {x.area: x for x in area_insights.rank_areas(listings, rents, year=year)}
    where = g.get("where") or "best"
    rules = dict(
        max_age=g.get("age"),
        near_rail=where == "rail",
        areas=(g.get("areas") or None) if where == "areas" else None,
        bedrooms=g.get("bedrooms"),
        goal=g.get("goal") or "yield",
        area_facts=area_facts,
        year=year,
    )
    found = picks.find(listings, intel, rents, budget, loan=bool(g.get("loan")), top=10**6, **rules)
    review = _review()
    every, dropped = arrange(found, review)
    lo, hi = budget * (1 - picks.BUDGET_BAND), budget * (1 + picks.BUDGET_BAND)
    what = f"{buyer.eur(lo)}–{buyer.eur(hi)}, {age_text(g.get('age'))}" + (
        ", κοντά σε σταθμό" if where == "rail" else ""
    )
    relax = (
        picks.relaxations(listings, intel, rents, budget, **rules)
        if len(every) < picks.PAGE
        else []
    )
    if not every:
        st.markdown(f"Καμία αγγελία {what}.")
        if relax:
            _relax(relax, "Χαλάρωσε έναν όρο — σε παρένθεση πόσες αγγελίες προστίθενται:")
        else:
            st.info("Ούτε με έναν όρο λιγότερο βρίσκω κάτι. Άλλαξε το ποσό.")
    else:
        if sentence := recommend(every, area_facts, rules["goal"]):
            st.markdown(sentence)
        checked = sum(p.checked for p in every)
        st.markdown(
            f"**{len(every)}** αγγελίες {what}. Ελέγχθηκε η περιγραφή σε **{checked}** από αυτές."
        )
        if relax:
            _relax(
                relax,
                f"Μόνο {len(every)}. Με έναν όρο λιγότερο (σε παρένθεση πόσες προστίθενται):",
            )
        facts = facts_for(every, g, area_facts, intel)
        _assistant_brief(facts)
        n = st.session_state.setdefault("guide_shown", picks.PAGE)
        visible = every[:n]
        maplist = _maplist()
        if maplist is not None:
            st.toggle("Χάρτης", key="guide_map")
            if st.session_state.get("guide_map"):
                try:
                    maplist.render([p.listing for p in visible], key="guide")
                except Exception:
                    st.caption("Ο χάρτης δεν φορτώθηκε.")
        for i, p in enumerate(visible, start=1):
            d = p.listing
            cmp = intel.comps(d)
            adv = {"cmp": cmp, "twins": intel.twins(d)}
            ok = review.get(shortlist.lkey(d)) == "ok"
            _card(i, p, ok, adv, maplist is not None)
        if len(every) > n:
            with st.container(key="guide-more"):
                st.button(
                    f"Δείξε άλλες {min(picks.PAGE, len(every) - n)}",
                    key="guide-more-btn",
                    on_click=_more,
                    width="stretch",
                )
        st.caption(f"Βλέπεις {len(visible)} από {len(every)}.")
        _assistant_panel(facts)
    if dropped:
        _dropped(dropped)
    with st.expander("Πώς υπολογίζω"):
        st.markdown(METHOD)
    st.caption(coverage(listings))
    if _store() is None:
        st.caption("Οι απαντήσεις κρατιούνται μόνο σε αυτή τη συνεδρία.")


def page(listings: list[dict]) -> None:
    buyer._css()
    buyer._show_flash()
    st.markdown(CSS, unsafe_allow_html=True)
    g = state()
    step = int(g.get("step") or 1)
    if step > 1 and not g.get("budget"):
        step = 1
    if step > 2 and not g.get("goal"):
        step = 2
    if step > 3 and (not g.get("where") or (g["where"] == "areas" and not g.get("areas"))):
        step = 3
    st.markdown(f"## {TITLE}")
    _progress(step)
    if step == 1:
        _step1(g)
    elif step == 2:
        _step2(g)
    elif step == 3:
        _step3(g, listings)
    elif step == 4:
        _step4(g)
    else:
        _results(g, listings)
