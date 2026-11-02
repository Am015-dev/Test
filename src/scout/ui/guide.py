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

Step 0 «Τι ψάχνεις;» picks the mode (``g["mode"]``, saved as ``guide.mode``): «Να νοικιάσω»
runs ``ui.rent_guide``; «Πίσω» on step 1 and the first answer chip reopen step 0.
"""

from __future__ import annotations

import html
import statistics
from collections import Counter
from datetime import date

import streamlit as st

from scout import area_insights, market_intel, picks, shortlist
from scout.ui import buyer, derived

TITLE = "Οδηγός"
STEPS = 5
BUDGETS = (150, 200, 250, 300, 400, 500)  # χιλ. €
BUDGET_MIN, BUDGET_MAX = 50_000, 2_000_000
GOALS = {
    "yield": "Απόδοση ενοικίου",
    "safety": "Σιγουριά & εύκολη ενοικίαση",
    "growth": "Ανατίμηση (μετρό, ανάπτυξη περιοχής)",
}
GOAL_CHIP = {"yield": "απόδοση", "safety": "σιγουριά", "growth": "ανατίμηση"}
WHERE = {
    "rail": "Κοντά σε μετρό/ΗΣΑΠ",
    "areas": "Συγκεκριμένες περιοχές",
    "best": "Όπου βγαίνει ο καλύτερος αριθμός",
}
AGES = {"10": "Νεόδμητο (έως 10 ετών)", "20": "Έως 20 ετών", "any": "Οτιδήποτε"}
BEDS = {"any": "Οποιαδήποτε", "1": "1", "2": "2", "3": "3+"}
MIN_AREA = 20  # an area is offered as a chip with at least this many active listings
DEFAULTS = {
    "mode": None,  # "buy" | "rent"; None = step 0 «Τι ψάχνεις;»
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
        got = s.get("guide", None)
    except Exception:
        return None
    return dict(got) if isinstance(got, dict) else None


def _save(g: dict) -> None:
    s = _store()
    if s is None:
        return
    try:
        s.set("guide", dict(g))
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
    if step < 1:
        g["mode"] = None  # step 0; the buy answers and step stay
    else:
        g["step"] = min(STEPS, step)
    _save(g)


def answer(field: str, value, next_step: int | None = None) -> None:
    g = state()
    g[field] = value
    if next_step:
        g["step"] = next_step
    _changed(g)


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


EDIT_KEYS = ("guide_e_budget", "guide_e_loan", "guide_e_goal", "guide_e_where", "guide_e_areas",
             "guide_e_age", "guide_e_beds")  # fmt: skip
WHERE_SHORT = {"rail": "Κοντά σε μετρό", "best": "Όπου βγαίνει", "areas": "Περιοχές"}
GOAL_SHORT = {"yield": "Απόδοση", "safety": "Σιγουριά", "growth": "Ανατίμηση"}
AGES_SHORT = {"10": "Νεόδμητο", "20": "Έως 20 ετών", "any": "Οτιδήποτε"}


def _edit_sync() -> None:
    """Drop the editor's widget state so it re-reads the answers (after a relax / restart)."""
    for k in EDIT_KEYS:
        st.session_state.pop(k, None)


# The editor's options are the words on screen; these map them back to the answers.
_GOAL_OF = {v: k for k, v in GOAL_SHORT.items()}
_WHERE_OF = {v: k for k, v in WHERE_SHORT.items()}
_AGE_OF = {"Νεόδμητο": picks.NEW_YEARS, "Έως 20 ετών": 20, "Οτιδήποτε": None}
_BEDS_OF = {"Οποιαδήποτε": None, "1": 1, "2": 2, "3+": 3}


def _age_word(age: int | None) -> str:
    return {"10": "Νεόδμητο", "20": "Έως 20 ετών"}.get(_age_code(age), "Οτιδήποτε")


def _beds_word(beds: int | None) -> str:
    return BEDS[_beds_code(beds)]


def _current(key: str, g: dict):
    return {
        "guide_e_budget": int(g.get("budget") or 0),
        "guide_e_goal": GOAL_SHORT.get(g.get("goal") or "yield"),
        "guide_e_where": WHERE_SHORT.get(g.get("where") or "best"),
        "guide_e_age": _age_word(g.get("age")),
        "guide_e_beds": _beds_word(g.get("bedrooms")),
    }.get(key)


def _edited(key: str) -> None:
    """One answer changed on the result screen: apply it at once (the list reruns)."""
    g = state()
    v = st.session_state.get(key)
    if v is None and key not in ("guide_e_loan", "guide_e_areas"):
        st.session_state[key] = _current(key, g)  # tapping the chosen option: keep it
        return
    if key == "guide_e_budget":
        g["budget"] = int(v)
    elif key == "guide_e_loan":
        g["loan"] = bool(v)
    elif key == "guide_e_goal":
        g["goal"] = _GOAL_OF[v]
    elif key == "guide_e_where":
        g["where"] = _WHERE_OF[v]
    elif key == "guide_e_areas":
        g["areas"] = list(v or [])
    elif key == "guide_e_age":
        g["age"] = _AGE_OF[v]
    elif key == "guide_e_beds":
        g["bedrooms"] = _BEDS_OF[v]
    _resync()
    _changed(g)


def _restart() -> None:
    """«Από την αρχή»: clear the buy answers and go back to the first question."""
    st.session_state["guide"] = {**DEFAULTS, "mode": "buy"}
    _resync()
    _edit_sync()
    _changed(st.session_state["guide"])


def edit_answers(g: dict, listings: list[dict]) -> None:
    """The answers as one panel on the result screen: change any of them and the list updates
    at once; no going back through the questions. Closed it is one line with the answers."""
    summary = " · ".join(answer_chips(g)[1:])
    with st.expander(f"Οι απαντήσεις σου: {summary}", expanded=False):
        budgets = sorted({k * 1000 for k in BUDGETS} | {int(g.get("budget") or 0)} - {0})
        st.session_state.setdefault("guide_e_budget", _current("guide_e_budget", g) or budgets[0])
        st.selectbox(
            "Ποσό", budgets, format_func=thousands, key="guide_e_budget",
            on_change=_edited, args=("guide_e_budget",),
        )  # fmt: skip
        st.session_state.setdefault("guide_e_loan", bool(g.get("loan")))
        st.toggle("Με δάνειο", key="guide_e_loan", on_change=_edited, args=("guide_e_loan",))
        for key, label, opts in (
            ("guide_e_goal", "Στόχος", list(GOAL_SHORT.values())),
            ("guide_e_where", "Πού", list(WHERE_SHORT.values())),
            ("guide_e_age", "Ηλικία κτιρίου", list(_AGE_OF)),
            ("guide_e_beds", "Υπνοδωμάτια", list(_BEDS_OF)),
        ):
            st.session_state.setdefault(key, _current(key, g))
            st.segmented_control(label, opts, key=key, on_change=_edited, args=(key,))
            if key == "guide_e_where" and st.session_state.get(key) == WHERE_SHORT["areas"]:
                count = dict(covered_areas(listings))
                st.session_state.setdefault(
                    "guide_e_areas", [a for a in g.get("areas", []) if a in count]
                )
                st.pills(
                    "Περιοχές", list(count), selection_mode="multi", key="guide_e_areas",
                    on_change=_edited, args=("guide_e_areas",), label_visibility="collapsed",
                )  # fmt: skip
        st.button("Από την αρχή", key="guide-restart", on_click=_restart, width="stretch")


def apply_relax(changes: dict) -> None:
    """A tapped relaxation (``picks.Relax.changes``) → the guide's answers."""
    _resync()
    _edit_sync()
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
        "να αγοράσω",
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


RECOMMEND_MIN = 3  # an area needs this many of the list's flats to be recommended

# The accusative after «Σου προτείνω …» for every area name the guide can recommend; only
# masculine names change. «Αττικής» is a genitive qualifier and never declines.
ACCUSATIVE = {
    "Άγιοι Ανάργυροι": "Αγίους Αναργύρους",
    "Άγιος Δημήτριος Αττικής": "Άγιο Δημήτριο Αττικής",
    "Άγιος Δημήτριος": "Άγιο Δημήτριο",
    "Άγιος Ιωάννης Ρέντης": "Άγιο Ιωάννη Ρέντη",
    "Άλιμος": "Άλιμο",
    "Αμπελόκηποι": "Αμπελόκηπους",
    "Βύρωνας": "Βύρωνα",
    "Κορυδαλλός": "Κορυδαλλό",
    "Νέος Κόσμος": "Νέο Κόσμο",
    "Πειραιάς": "Πειραιά",
    "Πρασάς": "Πρασά",
    "Ταύρος Αττικής": "Ταύρο Αττικής",
    "Χολαργός": "Χολαργό",
}
_ACC = (("ος", "ο"), ("ός", "ό"), ("ας", "α"), ("άς", "ά"))  # fallback, masculine singular


def accusative(name: str) -> str:
    """The area name after «Σου προτείνω …»: Χολαργός → Χολαργό, Αμπελόκηποι → Αμπελόκηπους,
    Δάφνη Αττικής stays. Known names come from ``ACCUSATIVE``; an unknown single masculine
    word falls back to the ending rule; anything else is left as it is (never guessed)."""
    if name in ACCUSATIVE:
        return ACCUSATIVE[name]
    if " " not in name:
        for end, acc in _ACC:
            if len(name) > len(end) + 1 and name.endswith(end):
                return name[: -len(end)] + acc
    return name


def recommend(
    found: list[picks.Pick], facts: dict, goal: str, budget: int | None = None
) -> str | None:
    """One spoken sentence: «Σου προτείνω Αμπελόκηπους: εκεί βγαίνει 3,6 % και 17 από τα 35
    σπίτια είναι εκεί.» The area is the one the list points to for ``goal``: yield → highest
    median gross yield of the flats there; safety → most active listings in the area
    (``AreaInsight.n_fresh``, else the flats listed); growth → highest median growth points,
    then yield. ``budget`` is kept for the caller (see ``over_budget``)."""
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
    # An area with one flat is no recommendation: among areas with at least three of the
    # list's flats (or as many as the fullest area has), the best for the goal.
    floor = min(RECOMMEND_MIN, max(len(ps) for ps in by.values()))
    pool = [a for a, ps in by.items() if len(ps) >= floor]
    area = max(pool, key=keys.get(goal, keys["yield"]))
    ps, x = by[area], facts.get(area)
    why = f"εκεί βγαίνει {picks.gr_pct(med(ps, lambda p: p.gross))}"
    if goal == "safety" and x is not None and x.n_fresh:
        why = f"εκεί πουλιούνται τα περισσότερα σπίτια ({buyer._num(x.n_fresh)})"
    elif goal == "growth":
        if l4 := picks.line4_stations(area):
            why = f"εκεί έρχεται η Γραμμή 4 ({l4[0]})"
        elif stations := sorted({p.station for p in ps if p.station}):
            why = f"εκεί έχει σταθμό ({stations[0]})"
    where = (
        "είναι το μόνο σπίτι που βρήκα"
        if len(found) == 1
        else f"{len(ps)} από τα {len(found)} σπίτια είναι εκεί"
    )
    return f"Σου προτείνω {html.escape(accusative(area))}: {why} και {where}."


def over_budget(found: list[picks.Pick], budget: int | None) -> str | None:
    """Why the first of the list costs more than the budget (below the list, C17)."""
    if not found or not budget:
        return None
    top = found[0].listing
    if not top.get("price") or top["price"] <= budget:
        return None
    return (
        f"Η 1η της λίστας ({buyer.eur(top['price'])}) είναι {buyer.eur(top['price'] - budget)} "
        f"πάνω από τα {buyer.eur(budget)} που είπες. Δείχνουμε έως "
        f"{round(picks.BUDGET_BAND * 100)} % πάνω από το ποσό σου."
    )


def loan_summary(found: list[picks.Pick]) -> str | None:
    """The «με δάνειο» answer for the whole list: how many flats' rent covers the instalment,
    and the range of the monthly gap."""
    if not found:
        return None
    gaps = sorted(p.cashflow for p in found)
    cover = sum(c >= 0 for c in gaps)
    if cover == 0:
        lo, hi = buyer.eur(-gaps[-1]), buyer.eur(-gaps[0])
        span = lo if lo == hi else f"{lo}–{hi}"
        return (
            f"Με δάνειο: **καμία από τις {len(found)} δεν καλύπτει τη δόση** με το ενοίκιο — "
            f"λείπουν {span}/μήνα."
        )
    return (
        f"Με δάνειο: το ενοίκιο καλύπτει τη δόση σε **{cover} από τις {len(found)}** "
        f"(στην καλύτερη μένουν {buyer.eur(gaps[-1])}/μήνα)."
    )


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
                "γραμμή_4": picks.line4_station(d),
                "προσφορά_αφετηρία": p.offer,
                "δόση_δανείου_€/μήνα": p.instalment if g.get("loan") else None,
                "ενοίκιο_μείον_δόση": p.cashflow if g.get("loan") else None,
                "κίνδυνοι": p.risks,
                "περιοχή_απόδοση": x.gross_yield if x is not None else None,
                "περιοχή_αγγελίες": x.n_fresh if x is not None else None,
                "περιοχή_διάμεσες_μέρες": x.median_dom if x is not None else None,
                "περιοχή_premium_νεόδμητων": x.new_premium if x is not None else None,
                "βαθμολογία": p.buyer_score,
                "ακριβώς_όπως_ζήτησε": not p.relaxed,
                "χαλαρωμένος_όρος": p.relaxed or None,
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
    names = {SOURCES.get(d.get("source") or "", d.get("source") or "") for d in listings}
    srcs = sorted(names, key=lambda s: (s != "XE.gr", s))  # XE first, as in the status line
    active = sum(1 for d in listings if d.get("is_fresh", True))
    checked = sum(1 for d in listings if d.get("page_checked"))
    return (
        f"Πηγές: {', '.join(s for s in srcs if s) or 'XE.gr'} · "
        f"{buyer._num(active)} αγγελίες ενεργές · {buyer._num(checked)} ελεγμένες σελίδες"
    )


# ---- verdicts (✓ / ✗) ----------------------------------------------------------------------


def tier_text(near: int, wide: int) -> str:
    """«**55** κοντινές (με έναν όρο πιο χαλαρό) και **410** ευρύτερα (πιο μακριά από αυτό που ζήτησες)»."""
    parts = []
    if near:
        noun = "κοντινή" if near == 1 else "κοντινές"
        parts.append(f"**{buyer._num(near)}** {noun} (με έναν όρο πιο χαλαρό)")
    if wide:
        noun = "ευρύτερη" if wide == 1 else "ευρύτερα"
        parts.append(f"**{buyer._num(wide)}** {noun} (πιο μακριά από αυτό που ζήτησες)")
    return " και ".join(parts)


def short_counts(exact: int, near: int, wide: int) -> str:
    """One line, numbers only (round 6): «**154** ακριβώς, **80** κοντινές, **2.338**
    ευρύτερα.» The answers are the chips above it; what each card is outside of is on the
    card."""
    parts = [f"**{buyer._num(exact)}** ακριβώς" if exact else "Καμία ακριβώς"]
    if near:
        parts.append(f"**{buyer._num(near)}** {'κοντινή' if near == 1 else 'κοντινές'}")
    if wide:
        parts.append(f"**{buyer._num(wide)}** ευρύτερα")
    return ", ".join(parts) + "."


def counts_line(exact: int, near: int, what: str, checked: int, wide: int = 0) -> str:
    """The result's counts line (kept signature; ``what`` and ``checked`` live elsewhere)."""
    return short_counts(exact, near, wide)


def checked_line(checked: int, total: int) -> str:
    """«Ελέγχθηκε η περιγραφή σε **12** από τις 35.» — behind «Πώς υπολογίζω» (C17)."""
    if total == 1:
        return (
            "Ελέγχθηκε η περιγραφή της." if checked else "Η περιγραφή της δεν έχει ελεγχθεί ακόμα."
        )
    return f"Ελέγχθηκε η περιγραφή σε **{buyer._num(checked)}** από τις {buyer._num(total)}."


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


def result_head(back) -> None:
    """The result's title (C17: the «Οδηγός» heading is not repeated above it). No «Πίσω» and
    no step bar: the answers are changed in place right below it (``edit_answers``)."""
    with st.container(key="guide-result-head"):
        st.markdown("## Η πρότασή μου")


def at_result(g: dict) -> bool:
    """True on the screen that shows the list (buy or rent), where the title is the result's."""
    if g.get("mode") == "buy":
        return int(g.get("step") or 1) >= STEPS and all(
            g.get(k) for k in ("budget", "goal", "where")
        )
    if g.get("mode") == "rent":
        r = g.get("rent") or {}
        return int(r.get("step") or 1) >= STEPS and all(
            r.get(k) for k in ("budget", "beds", "where")
        )
    return False


def _choice(label: str, key: str, cb, args: tuple, on: bool) -> None:
    kind = "primary" if on else "secondary"
    st.button(label, key=key, on_click=cb, args=args, type=kind, width="stretch")


def _row(key: str, options: dict, field: str, chosen, per_row: int = 3) -> None:
    """One question's answers as buttons in rows; the chosen one is filled. A tap only selects
    (no next screen): every question is on the same screen."""
    items = list(options.items())
    with st.container(key=key):
        for i in range(0, len(items), per_row):
            cols = st.columns(per_row)
            for c, (k, label) in zip(cols, items[i : i + per_row], strict=False):
                with c:
                    _choice(label, f"{key.removesuffix('s')}-{k}", answer, (field, k), chosen == k)


def _finish() -> None:
    """«Η πρότασή μου»: the unanswered questions keep their shown default, then the list."""
    g = state()
    g["goal"] = g.get("goal") or "yield"
    g["where"] = g.get("where") or "best"
    g["step"] = STEPS
    _changed(g)


def _questions(g: dict, listings: list[dict]) -> None:
    """Every question on one screen, each with its answer already chosen except the amount;
    change any, then «Η πρότασή μου»."""
    st.button("Πίσω", key="guide-back", on_click=go, args=(0,))
    st.markdown("### Πόσα θες να βάλεις;")
    st.session_state.setdefault("guide_loan", bool(g.get("loan")))
    st.toggle("Με δάνειο", key="guide_loan", on_change=_loan_toggled)
    with st.container(key="guide-budgets"):
        for row in range(0, len(BUDGETS), 3):
            cols = st.columns(3)
            for c, k in zip(cols, BUDGETS[row : row + 3], strict=True):
                with c:
                    _choice(
                        f"{k} χιλ.",
                        f"guide-b{k}",
                        answer,
                        ("budget", k * 1000),
                        g.get("budget") == k * 1000,
                    )
    with st.expander("Άλλο ποσό"):
        st.session_state.setdefault("guide_other", g.get("budget") or 300_000)
        st.number_input("Ποσό (€)", BUDGET_MIN, BUDGET_MAX, step=10_000, key="guide_other")
        st.button("Αυτό το ποσό", key="guide-other-go", on_click=_other_budget, width="stretch")
    st.markdown("### Τι σε νοιάζει πιο πολύ;")
    _row("guide-gs", GOAL_SHORT, "goal", g.get("goal") or "yield")
    st.markdown("### Πού;")
    _row("guide-ws", WHERE_SHORT, "where", g.get("where") or "best")
    if g.get("where") == "areas":
        count = dict(covered_areas(listings))
        st.session_state.setdefault("guide_areas", [a for a in g.get("areas", []) if a in count])
        st.pills(
            "Διάλεξε περιοχές",
            list(count),
            selection_mode="multi",
            key="guide_areas",
            on_change=_areas_picked,
            label_visibility="collapsed",
        )
    st.markdown("### Τι σπίτι;")
    st.session_state.setdefault("guide_age", _age_code(g.get("age")))
    st.session_state.setdefault("guide_beds", _beds_code(g.get("bedrooms")))
    for key, label, opts in (
        ("guide_age", "Ηλικία κτιρίου", AGES_SHORT),
        ("guide_beds", "Υπνοδωμάτια", BEDS),
    ):
        st.segmented_control(
            label, list(opts), format_func=opts.get, key=key, on_change=_kind_changed, args=(key,)
        )
    ready = bool(g.get("budget")) and (g.get("where") != "areas" or bool(g.get("areas")))
    with st.container(key="guide-finish"):
        st.button(
            (
                "Η πρότασή μου"
                if ready
                else "Διάλεξε πρώτα ποσό" if not g.get("budget") else "Διάλεξε περιοχές"
            ),
            key="guide-show",
            on_click=_finish,
            type="primary",
            disabled=not ready,
            width="stretch",
        )


@st.cache_data(ttl=600, show_spinner=False)
def _rent_rows() -> list[dict]:
    from scout.ui import queries

    return queries.load_rent_comp_rows()


METHOD = """
Πρώτα όσα έχουν ελεγμένη περιγραφή, μετά όσα έχουν αληθινές φωτογραφίες, και μέσα σε κάθε ομάδα
με τη Βαθμολογία· όσα ζητούν πάνω από 30 % λιγότερα από τα παρόμοια πάνε τελευταία στην ομάδα
τους, γιατί θέλουν έλεγχο.

- **Ισοπαλίες**: όταν δύο έχουν ίδια Βαθμολογία, μετράει ο στόχος σου. Ο στόχος διαλέγει και
  την περιοχή που προτείνουμε.
- **Πόντοι**: για την απόδοση 1000 × μικτή απόδοση (4,5 % δίνει 45). Για την τιμή, από −6
  έως +10 ανάλογα με τα παρόμοια, +3 αν το κτίριο τελείωσε πριν από φέτος, +2 αν είναι 90
  μέρες και πάνω στην αγορά, −20 αν ζητά πάνω από 35 % λιγότερα από τα παρόμοια. Για τη
  σιγουριά 6 πόντοι για καθένα: ελέγξαμε την αγγελία, έχει πάνω από 2 φωτογραφίες, γράφει
  ενεργειακή κλάση, έχει 8 παρόμοια και πάνω, η περιοχή έχει 50 αγγελίες και πάνω, στην
  περιοχή πουλάνε σε σταθερό χρόνο. Για την ανατίμηση 12 για σταθμό σήμερα, 12 για σταθμό
  της Γραμμής 4 που έρχεται, 6 αν τα νεόδμητα της περιοχής ζητούν έως 15 % παραπάνω από τα
  παλιά.
- **Βάρη ανά στόχο** (απόδοση · τιμή · σιγουριά · ανατίμηση): Απόδοση ενοικίου 1 · 1 · 0,25 ·
  0,25. Σιγουριά 0,4 · 0,6 · 1 · 0,25. Ανατίμηση 0,4 · 0,6 · 0,25 · 1.
- **Ενοίκιο (εκτίμηση)**: όσο ζητούν συνήθως ανά τ.μ. οι αγγελίες ενοικίασης του XE.gr στη
  γειτονιά (αλλιώς σε όλη την περιοχή), επί τα τ.μ. Το ίδιο ποσό που βλέπεις στην αναζήτηση,
  στον χάρτη, στη σύγκριση και στη σελίδα της αγγελίας. Είναι αγγελίες, όχι συμβόλαια.
- **Μικτή απόδοση** = 12 × ενοίκιο ÷ τιμή. **Καθαρή απόδοση**: 11 μήνες ενοίκιο, μείον 15 %
  φόρο, 5 % συντήρηση και ΕΝΦΙΑ ~3 €/τ.μ. τον χρόνο, διά την τιμή μαζί με τα έξοδα αγοράς.
- **Με δάνειο**: δάνειο 70 % της τιμής, επιτόκιο 4 %, 25 χρόνια, ίδια δόση κάθε μήνα. Το
  «περισσεύουν» είναι το ενοίκιο (εκτίμηση) μείον τη δόση, πριν από φόρους και έξοδα.
- **Προσφορά**: 3 % κάτω από την τιμή, άλλο 3 % στις 90 μέρες και πάνω, άλλο 2 % αν πουλά
  ιδιώτης.
- **Σταθμός**: τον βγάζουμε από το όνομα της γειτονιάς στο XE.gr, γιατί δεν δίνει διεύθυνση.
- **Πρόταση περιοχής**: ανάμεσα στις περιοχές της λίστας. Για απόδοση, όπου βγάζουν συνήθως
  τη μεγαλύτερη μικτή απόδοση. Για σιγουριά, όπου έχει τις περισσότερες αγγελίες. Για
  ανατίμηση, όπου μαζεύουν τους περισσότερους πόντους.
- Οι τιμές είναι όσα ζητούν οι αγγελίες στο XE.gr, όχι τιμές πώλησης.
"""


def _card(i: int, p: picks.Pick, approved: bool, adv: dict, has_map: bool) -> None:
    """The compact card (five lines, C3): everything else — the title, net yield, loan,
    offer, the risks to check and the listing's own words — sits in «Από πού βγαίνουν».
    Under it one row: «Αγγελία» (the ad on the portal), «Λεπτομέρειες», «Αγαπημένο»
    («Εγκρίνω» / «Δεν μου κάνει» live on the saved-searches page only).
    ``approved`` and ``has_map`` are kept for the caller."""
    d = p.listing
    shown = d  # one rent, one yield, one score: the row's own fields, as on every other page
    more = [d["title"]] if d.get("title") else []
    more.append(f"Καθαρή απόδοση ~{picks.gr_pct(p.net)}")
    if p.loan:
        more.append(p.loan_line)
    why = p.reasons.get(p.goal) if p.goal in ("safety", "growth") else None
    if why:
        more.append(f"{GOAL_CHIP[p.goal].capitalize()}: " + " · ".join(why))
    more.append(
        f"Πρώτη προσφορά ~{buyer.eur(p.offer)}"
        + (" (πουλά ιδιώτης)" if d.get("is_private_seller") else "")
    )
    more += [f"Έλεγξε: {r}" for r in p.risks]
    if p.excerpt:
        more.append(f"Τι λέει η αγγελία: «{p.excerpt}»")
    with st.container(border=True, key=f"pick-{d['id']}"):
        st.markdown(
            buyer.card_html(shown, adv, compact=True, lead=f"{i}.", more=more),
            unsafe_allow_html=True,
        )
        star, toggle, args, kind = buyer._star_action(d)
        cols = st.columns(3, gap="small")  # one row: the ad, the details, the favourite
        cols[0].link_button(buyer.AD_SHORT, d["url"], width="stretch")
        cols[1].button(
            buyer.DETAILS,
            key=f"pick-det-{d['id']}",
            on_click=buyer.open_detail,
            args=(d["id"],),
            width="stretch",
        )
        cols[2].button(
            buyer.short_label(star),
            key=f"pick-fav-{d['id']}",
            on_click=toggle,
            args=args,
            type=kind,
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


def assistant_facts(
    every: list[picks.Pick],
    g: dict,
    area_facts: dict,
    intel,
    rents: list[dict],
    budget: int,
    goal: str,
) -> dict:
    """The facts the assistant reads: ``assistant.facts_for`` (its own contract, English keys,
    up to 10 picks, the areas they are in, the buyer's answers) when that module exists, else
    this page's own summary. The brief and the panel only render on the assistant's format."""
    a = _assistant()
    if a is not None and callable(getattr(a, "facts_for", None)):
        answers = {
            "budget": budget,
            "goal": goal,
            "loan": bool(g.get("loan")),
            "where": g.get("where"),
            "areas": g.get("areas"),
            "max_age": g.get("age"),
            "bedrooms": g.get("bedrooms"),
        }
        try:
            facts = a.facts_for(every, intel, list(area_facts.values()), answers, rent_rows=rents)
        except Exception:
            facts = None
        if isinstance(facts, dict):
            return mark_near(facts, every)
    return facts_for(every, g, area_facts, intel)


NEAR_NOTE = (
    "Listings with exact_match=false do not match every answer of the buyer: relaxed names "
    "the answer(s) they are outside of (one = near match, several = wider). Never call them "
    "exact matches."
)


def mark_near(facts: dict, picks_: list) -> dict:
    """C7: every listing row says whether it matches the answers exactly and, if not, the one
    loosened answer (``relaxed``), plus its buyer score; rows are in the order of ``picks_``."""
    rows = facts.get("listings") or []
    for row, p in zip(rows, picks_, strict=False):
        if isinstance(row, dict):
            row["exact_match"] = not getattr(p, "relaxed", "")
            row["relaxed"] = getattr(p, "relaxed", "") or None
            if (sc := getattr(p, "buyer_score", None) or getattr(p, "score", None)) is not None:
                row["score_0_100"] = sc
    if any(isinstance(r, dict) and not r.get("exact_match", True) for r in rows):
        facts["near_matches_note"] = NEAR_NOTE
    return facts


def _assistant_panel(facts: dict) -> None:
    a = _assistant()
    if a is None or not callable(getattr(a, "panel", None)):
        return
    try:
        a.panel(facts, "guide")
    except Exception:
        return


def _results(g: dict, listings: list[dict]) -> None:
    edit_answers(g, listings)
    budget = int(g.get("budget") or area_insights.DEFAULT_BUDGET)
    year = date.today().year
    rents = _rent_rows()
    intel = market_intel.build(listings)
    # C13: built once per data version and shared (scout/ui/derived.py), same values.
    area_facts, find_memo = derived.guide_context(listings, rents, year)
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
    found = picks.find(
        listings,
        intel,
        rents,
        budget,
        loan=bool(g.get("loan")),
        top=10**6,
        near=True,
        memo=find_memo,
        **rules,
    )
    review = _review()
    every, dropped = arrange(found, review)
    exact = [p for p in every if not p.relaxed]
    near = sum(p.tier == 1 for p in every)
    wide = sum(p.tier == 2 for p in every)
    hi = budget * (1 + picks.BUDGET_BAND)  # C15: a ceiling, no floor under the budget
    what = f"έως {buyer.eur(hi)}, {age_text(g.get('age'))}" + (
        ", κοντά σε σταθμό" if where == "rail" else ""
    )
    relax = (
        picks.relaxations(listings, intel, rents, budget, memo=find_memo, **rules)
        if len(exact) < picks.NEAR_MIN
        else []
    )
    if not every:
        st.markdown(f"Καμία αγγελία {what}.")
        if relax:
            _relax(relax, "Χαλάρωσε έναν όρο — σε παρένθεση πόσες αγγελίες προστίθενται:")
        else:
            st.info("Ούτε με έναν όρο λιγότερο βρίσκω κάτι. Άλλαξε το ποσό.")
    else:
        # C17: above the first card only the counts line and the recommendation.
        checked = sum(p.checked for p in every)
        if near or wide:
            st.markdown(counts_line(len(exact), near, what, checked, wide))
        else:
            st.markdown(f"**{len(every)}** {buyer._noun(len(every))} {what}.")
        if sentence := recommend(exact or every, area_facts, rules["goal"], budget):
            st.markdown(sentence)
        n = st.session_state.setdefault("guide_shown", picks.PAGE)
        visible = every[:n]
        maplist = _maplist()
        for i, p in enumerate(visible, start=1):
            d = p.listing
            cmp = intel.comps(d)
            adv = {"cmp": cmp, "twins": intel.twins(d), "score": p.buyer_score}
            adv["relaxed"] = p.relaxed
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
        # Below the list: the budget note, the loan line, the map, the relaxations, the
        # «Ρώτα με» (no model-written brief on the result, C18).
        if note := over_budget(exact or every, budget):
            st.caption(note)
        if g.get("loan") and (loan := loan_summary(every)):
            st.markdown(loan)
        if maplist is not None:
            st.toggle("Χάρτης", key="guide_map")
            if st.session_state.get("guide_map"):
                try:
                    maplist.render([p.listing for p in visible], key="guide")
                except Exception:
                    st.caption("Ο χάρτης δεν φορτώθηκε.")
        if relax:
            _relax(
                relax,
                f"Μόνο {len(exact)} ακριβώς όπως ζήτησες. Βγάλε έναν όρο για να δεις "
                "περισσότερες (σε παρένθεση πόσες προστίθενται):",
            )
        facts = assistant_facts(every, g, area_facts, intel, rents, budget, rules["goal"])
        _assistant_panel(facts)
    if dropped:
        _dropped(dropped)
    with st.expander("Πώς υπολογίζω"):
        if every:
            st.markdown(checked_line(checked, len(every)))
        st.markdown(METHOD)
    st.caption(derived.memo(listings, "coverage", lambda: coverage(listings)))  # C13: per data


def page(listings: list[dict]) -> None:
    buyer._css()
    buyer._show_flash()
    st.markdown(CSS, unsafe_allow_html=True)
    g = state()
    if not at_result(g):
        st.markdown(f"## {TITLE}")
    if g.get("mode") != "buy":
        from scout.ui import rent_guide

        if g.get("mode") == "rent" and not rent_guide.rentals():
            # No rentals stored yet (the first weekly run with rentals has not happened): a
            # saved «rent» mode must not strand the visitor on an empty flow. Back to step 0.
            rent_guide.set_mode(None)
            g = state()
        return rent_guide.page(g) if g.get("mode") == "rent" else rent_guide.mode_step(g)
    if not at_result(g):
        return _questions(g, listings)
    result_head(go)
    _results(g, listings)
