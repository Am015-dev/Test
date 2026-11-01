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
    for i, label in enumerate(answer_chips(state())):
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


_ACC = (  # nominative → accusative, unaccented and accented endings
    ("ος", "ο"), ("ός", "ό"), ("ας", "α"), ("άς", "ά"), ("ης", "η"), ("ής", "ή"),
    ("οι", "ους"), ("οί", "ούς"),
)  # fmt: skip


def accusative(name: str) -> str:
    """The area name after «Σου προτείνω …»: masculine endings move to the accusative
    (Χολαργός → Χολαργό, Αμπελόκηποι → Αμπελόκηπους, Άγιος Δημήτριος → Άγιο Δημήτριο);
    feminine and neuter names (Νέα Σμύρνη, Γαλάτσι, Παπάγου) stay as they are."""
    words = []
    for w in name.split():
        for end, acc in _ACC:
            if len(w) > len(end) + 1 and w.endswith(end):
                w = w[: -len(end)] + acc
                break
        words.append(w)
    return " ".join(words)


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
    area = max(by, key=keys.get(goal, keys["yield"]))
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


def counts_line(exact: int, near: int, what: str, checked: int, wide: int = 0) -> str:
    """C7's result sentence with the three counts: «**2** αγγελίες … ακριβώς όπως ζήτησες,
    **55** κοντινές (…) και **410** ευρύτερα (…)», or «Καμία ακριβώς όπως ζήτησες· …». What
    each card is outside of is written on the card."""
    rest = tier_text(near, wide)
    if exact:
        joint = ", " if near and wide else " και "
        head = f"**{buyer._num(exact)}** {buyer._noun(exact)} {what} ακριβώς όπως ζήτησες{joint}{rest}."
    else:
        head = f"Καμία ακριβώς όπως ζήτησες ({what})· {rest}."
    return head  # C17: what each card is outside of is on the card; ``checked`` → «Πώς υπολογίζω»


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
    """The result's header row (C6): «Πίσω» small and secondary next to the title, which is
    the page title here (C17: the «Οδηγός» heading is not repeated above it); no step line
    or bar — the answer chips below reopen any question."""
    with st.container(key="guide-result-head"):
        c = st.columns([1, 3], vertical_alignment="center")
        c[0].button("Πίσω", key="guide-back", on_click=back, args=(STEPS - 1,))
        c[1].markdown("## Η πρότασή μου")


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


def _progress(step: int) -> None:
    if step >= STEPS:
        return result_head(go)
    with st.container(key="guide-progress"):
        c = st.columns([1, 2], vertical_alignment="center")
        c[0].button("Πίσω", key="guide-back", on_click=go, args=(step - 1,))
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
            "Η πρότασή μου",
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
  γειτονιά (αλλιώς σε όλη την περιοχή), επί τα τ.μ., και 10 % παραπάνω για κτίριο έως 5 ετών.
  Είναι αγγελίες, όχι συμβόλαια.
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
    Under it the link to the ad, full width, then exactly two buttons, «Λεπτομέρειες» and
    «Αγαπημένο» (C17: «Εγκρίνω» / «Δεν μου κάνει» live on the saved-searches page only).
    ``approved`` and ``has_map`` are kept for the caller."""
    d = p.listing
    shown = {**d, "est_monthly_rent": p.rent, "rent_estimated": True, "listed_rent": None}
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
        buyer.ad_link(d, f"pick-{d['id']}")
        star, toggle, args, kind = buyer._star_action(d)
        cols = st.columns(2)
        cols[0].button(
            "Λεπτομέρειες",
            key=f"pick-det-{d['id']}",
            on_click=buyer.open_detail,
            args=(d["id"],),
            width="stretch",
        )
        cols[1].button(
            star, key=f"pick-fav-{d['id']}", on_click=toggle, args=args, type=kind, width="stretch"
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
    lo, hi = budget * (1 - picks.BUDGET_BAND), budget * (1 + picks.BUDGET_BAND)
    what = f"{buyer.eur(lo)}–{buyer.eur(hi)}, {age_text(g.get('age'))}" + (
        ", κοντά σε σταθμό" if where == "rail" else ""
    )
    relax = (
        picks.relaxations(listings, intel, rents, budget, **rules)
        if len(exact) < picks.PAGE
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
        st.caption(f"Βλέπεις {buyer._num(len(visible))} από {buyer._num(len(every))}.")
        # Below the list: the budget note, the loan line, the map, the relaxations, the
        # assistant's brief and «Ρώτα με».
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
        _assistant_brief(facts)
        _assistant_panel(facts)
    if dropped:
        _dropped(dropped)
    with st.expander("Πώς υπολογίζω"):
        if every:
            st.markdown(checked_line(checked, len(every)))
        st.markdown(METHOD)
    st.caption(derived.memo(listings, "coverage", lambda: coverage(listings)))  # C13: per data
    if _store() is None:
        st.caption("Οι απαντήσεις κρατιούνται μόνο σε αυτή τη συνεδρία.")


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
    step = int(g.get("step") or 1)
    if step > 1 and not g.get("budget"):
        step = 1
    if step > 2 and not g.get("goal"):
        step = 2
    if step > 3 and (not g.get("where") or (g["where"] == "areas" and not g.get("areas"))):
        step = 3
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
