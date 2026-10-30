"""Buyer-facing pages: plain-language search (the home page), the agent's shortlist and the
starred listings. Greek UI. Cards are native Streamlit widgets so every button is real.

Starred listings and saved searches live in a private GitHub Gist (see ``shortlist``); with no
``GITHUB_TOKEN`` they still work, for the current browser session only.
"""

from __future__ import annotations

import html
import re
import statistics
from datetime import date

import streamlit as st

from scout import advisor, nl_search, shortlist
from scout.nl_search import SearchFilters

PAGE_SIZE = 12
MAX_ADVICE = 25  # Claude reviews per browser session — bounds API cost
ADVICE_TONE = {"Αξίζει": "good", "Με επιφύλαξη": "warn", "Απόφυγε": "bad"}
ADVICE_RANK = {"Αξίζει": 0, "Με επιφύλαξη": 1, "Απόφυγε": 2}
MAX_SEARCHES = 30  # per browser session — bounds API cost
NAV_DETAIL = "🏠 Αγγελία"  # label of the listing-detail page (cards link to it)

EXAMPLES = {
    "Δυάρι στον Χολαργό": "δυάρι στον Χολαργό έως 180Χ με ανελκυστήρα",
    "Τριάρι Παπάγος": "τριάρι στο Παπάγου ή στην Αγία Παρασκευή κάτω από 250.000€ με πάρκινγκ",
    "Έχω 200.000 €": "έχω 200 χιλιάδες να επενδύσω στον Χολαργό",
    "Γκαρσονιέρα ≤ 90.000 €": "γκαρσονιέρα μέχρι 90 χιλιάδες",
}

SORTS = {
    "Καλύτερη αντιστοιχία": lambda pct, adv, d: (-pct, -adv["score"], d["price"]),
    "Σκορ αγοράς": lambda pct, adv, d: (-adv["score"], d["price"]),
    "Χαμηλότερη τιμή": lambda pct, adv, d: (d["price"], -adv["score"]),
    "Χαμηλότερο €/τ.μ.": lambda pct, adv, d: (d.get("price_per_m2") or 1e9, d["price"]),
    "Φθηνότερο από την περιοχή": lambda pct, adv, d: (
        adv["cmp"][0] if adv.get("cmp") else 9,
        d["price"],
    ),
}

BEDROOMS = {
    "Όλα": (None, None),
    "Γκαρσονιέρα": (0, 0),
    "1": (1, 1),
    "2": (2, 2),
    "3": (3, 3),
    "4+": (4, None),
}


def eur(v: float | int | None) -> str:
    return "—" if v is None else f"{v:,.0f}".replace(",", ".") + " €"


# ---- session state: starred listings -------------------------------------------------------


def watch_keys() -> set[str]:
    """Starred listing keys for this session, loaded from the Gist once."""
    if "watch" not in st.session_state:
        keys: set[str] = set()
        try:
            keys = shortlist.watch_set()
            st.session_state["watch_persisted"] = True
        except shortlist.StorageNotConfigured:
            st.session_state["watch_persisted"] = False
        except Exception as e:  # network / auth: keep working, say so once
            st.session_state["watch_persisted"] = False
            _flash("error", f"Τα αγαπημένα δεν φορτώθηκαν από το GitHub ({_reason(e)}).")
        st.session_state["watch"] = keys
    return st.session_state["watch"]


def toggle_watch(key: str) -> None:
    keys = watch_keys()
    on = key not in keys
    keys.add(key) if on else keys.discard(key)
    if st.session_state.get("watch_persisted"):
        try:
            shortlist.set_watch(key, on)
        except Exception as e:
            _flash("error", f"Δεν αποθηκεύτηκε στο GitHub ({_reason(e)}) — ισχύει μόνο τώρα.")


def open_detail(listing_id: int) -> None:
    st.session_state["page"] = NAV_DETAIL
    st.session_state["detail_id"] = listing_id


def _reason(e: Exception) -> str:
    """A short, friendly reason — never a raw URL or traceback."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status in (401, 403):
        return "το GitHub αρνήθηκε την πρόσβαση — έλεγξε ότι το token έχει δικαίωμα Gists"
    if status == 404:
        return "το GitHub δεν βρήκε το αρχείο αποθήκευσης"
    if status is not None:
        return f"σφάλμα GitHub ({status}) — δοκίμασε ξανά σε λίγο"
    if isinstance(e, OSError | TimeoutError):
        return "δεν υπάρχει σύνδεση με το GitHub — δοκίμασε ξανά σε λίγο"
    return type(e).__name__


def _flash(kind: str, msg: str) -> None:
    st.session_state.setdefault("flash", []).append((kind, msg))


def _show_flash() -> None:
    for kind, msg in st.session_state.pop("flash", []):
        (st.error if kind == "error" else st.success)(msg)


# ---- the listing card ----------------------------------------------------------------------


def _greek_numbers(s: str) -> str:
    """'180,000' / '170000' → '180.000' (Greek thousands separator) in free text."""
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", ".", s)
    return re.sub(r"\b\d{5,}\b", lambda m: f"{int(m.group()):,}".replace(",", "."), s)


def _floor(f: float) -> str:
    if f < 0:
        return "Υπόγειο"
    return "Ισόγειο" if f == 0 else f"{f:g}ος όροφος"


def _ppm_medians(pool: list[dict]) -> dict[str, tuple[float, int]]:
    """Median asking €/m² per municipality (only where at least 5 listings back it)."""
    by: dict[str, list[float]] = {}
    for d in pool:
        if d.get("price_per_m2") and (m := municipality(d)):
            by.setdefault(m, []).append(d["price_per_m2"])
    return {m: (statistics.median(v), len(v)) for m, v in by.items() if len(v) >= 5}


def _vs_median(d: dict, medians: dict) -> tuple[float, str, int] | None:
    """(this €/m² vs the municipality median, municipality, how many listings) or None."""
    m = municipality(d)
    if not d.get("price_per_m2") or m not in medians:
        return None
    med, n = medians[m]
    return d["price_per_m2"] / med - 1, m, n


def _card_html(d: dict, adv: dict) -> str:
    """Title/location, the key facts in a fixed order and coloured badges — one small block."""
    e = html.escape
    title = e(d.get("title") or "Αγγελία")
    loc = f'<span class="hg-loc">📍 {e(d["neighborhood"])}</span>' if d.get("neighborhood") else ""
    facts = []
    if d.get("area_m2"):
        facts.append(f"<b>{d['area_m2']:g}</b> τ.μ.")
    if d.get("bedrooms") is not None:
        facts.append("Γκαρσονιέρα" if d["bedrooms"] == 0 else f"<b>{d['bedrooms']}</b> υ/δ")
    if d.get("floor") is not None:
        facts.append(_floor(d["floor"]))
    if d.get("price_per_m2"):
        facts.append(f"{eur(d['price_per_m2'])}/τ.μ.")
    age = adv.get("age")
    if d.get("renovated_year"):
        facts.append(f"ανακαίνιση <b>{d['renovated_year']}</b>")
    elif d.get("year_built"):
        facts.append(f"κατασκευή <b>{d['year_built']}</b>" + (f" ({age} ετών)" if age else ""))
    badges = []
    if d.get("is_unfinished"):
        badges.append(("bad", "Ημιτελές"))
    if age is not None and age >= 40 and not d.get("renovated_year"):
        badges.append(("bad" if age >= 50 else "warn", f"Παλιό κτίριο — {age} ετών"))
    if (d.get("year_built") or 0) >= date.today().year:
        badges.append(("warn", "Νεόδμητο — έλεγξε ότι έχει παραδοθεί"))
    elif age is None:
        badges.append(("muted", "Έτος κατασκευής: δεν δηλώνεται"))
    for flag in advisor.red_flags(d):
        if not flag.startswith(("Κτίριο", "Χωρίς έτος", "Ημιτελές")):
            badges.append(("warn", flag))
    if cmp := adv.get("cmp"):
        pct, m, n = cmp
        tone = "good" if pct <= -0.1 else "bad" if pct >= 0.1 else "muted"
        word = "κάτω" if pct < 0 else "πάνω"
        badges.append(
            (tone, f"€/τ.μ. {abs(pct):.0%} {word} από τη διάμεση τιμή {m} ({n} αγγελίες)")
        )
    if d.get("price_dropped"):
        badges.append(("drop", "Μειώθηκε η τιμή"))
    if d.get("is_private_seller"):
        badges.append(("priv", "Ιδιώτης"))
    if d.get("days_on_market"):
        badges.append(("muted", f"{d['days_on_market']} μέρες στην αγορά"))
    out = f'<div class="hg-head"><span class="hg-title">{title}</span>{loc}</div>'
    if facts:
        out += '<div class="hg-facts">' + "".join(f"<span>{f}</span>" for f in facts) + "</div>"
    if badges:
        out += (
            '<div class="hg-badges">'
            + "".join(f'<span class="hg-b hg-b-{c}">{e(t)}</span>' for c, t in badges)
            + "</div>"
        )
    return out


def _score_html(adv: dict, grade: str | None) -> str:
    s = adv["score"]
    tone = "hi" if s >= 70 else "mid" if s >= 50 else "lo"
    g = f"<i>{html.escape(str(grade))}</i>" if grade else ""
    return (
        f'<span class="hg-score hg-score-{tone}" '
        f'title="Σκορ 0–100: στρατηγική + αξία, μειωμένο για παλιά κτίρια">'
        f"<small>Σκορ</small><b>{s}</b>{g}</span>"
    )


def result_card(d: dict, adv: dict, reasons: list[str], k: str, actions: list, advice=None) -> None:
    """One listing. ``actions`` = [(label, callback, args[, type])], each rendered as a button."""
    key = shortlist.lkey(d)
    uid = f"{k}-{d['id']}"
    with st.container(border=True, key=f"card-{uid}"):
        if d.get("image_url"):
            st.markdown(
                f'<img class="hg-photo" src="{html.escape(d["image_url"])}" alt="" '
                'loading="lazy">',
                unsafe_allow_html=True,
            )
        with st.container(horizontal=True, vertical_alignment="center", wrap=False):
            st.markdown(f"### {eur(d['price'])}", width="stretch")
            st.markdown(
                _score_html(adv, d.get("deal_grade")), unsafe_allow_html=True, width="content"
            )
        st.markdown(_card_html(d, adv), unsafe_allow_html=True)
        if advice is not None:
            st.markdown(
                f'<div class="hg-advice hg-advice-{ADVICE_TONE[advice.label]}">'
                f"<b>🤖 {html.escape(advice.label)}</b> — {html.escape(advice.reason)}</div>",
                unsafe_allow_html=True,
            )
        if reasons:
            st.caption("✓ Ταιριάζει: " + _greek_numbers(", ".join(reasons)))
        with st.container(key=f"act-{uid}"):
            cols = st.columns(len(actions) + 1, gap="small")
            cols[0].link_button(f"Άνοιγμα στο {d['source'].upper()} ↗", d["url"], width="stretch")
            for i, (label, cb, args, *kind) in enumerate(actions, start=1):
                cols[i].button(
                    label,
                    key=f"{k}-{i}-{key}",
                    on_click=cb,
                    args=args,
                    type=kind[0] if kind else "secondary",
                    width="stretch",
                )


def _star_action(d: dict) -> tuple:
    key = shortlist.lkey(d)
    on = key in watch_keys()
    return (
        "★ Αφαίρεση" if on else "☆ Αγαπημένο",
        toggle_watch,
        (key,),
        "primary" if on else "secondary",
    )


# ---- search (home) -------------------------------------------------------------------------


def _run_query(text: str) -> None:
    text = text.strip()
    if not text:
        return
    used = st.session_state.get("nl_calls", 0)
    if used >= MAX_SEARCHES:
        st.session_state["nl_error"] = (
            "Έφτασες το όριο αναζητήσεων για αυτή τη συνεδρία — κάνε refresh."
        )
        return
    try:
        st.session_state["nl_filters"] = nl_search.parse_query(text)
        st.session_state["nl_text"] = text
        st.session_state["nl_calls"] = used + 1
        st.session_state["nl_error"] = ""
        st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1
        st.session_state["limit"] = PAGE_SIZE
    except nl_search.SearchParseError as e:
        st.session_state["nl_error"] = str(e)


def _example_clicked(text: str) -> None:
    st.session_state["q_text"] = text
    _run_query(text)


def _clear_query() -> None:
    for k in ("nl_filters", "nl_text", "nl_error", "q_text"):
        st.session_state.pop(k, None)
    st.session_state["limit"] = PAGE_SIZE
    st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1


def _more() -> None:
    st.session_state["limit"] = st.session_state.get("limit", PAGE_SIZE) + PAGE_SIZE


FLOORS = {"Οποιοσδήποτε": None, "Από 1ο": 1, "Από 2ο": 2, "Από 3ο": 3, "Από 4ο": 4}
AGES = {
    "Οποιαδήποτε": None,
    "Έως 10 ετών": 10,
    "Έως 20 ετών": 20,
    "Έως 30 ετών": 30,
    "Έως 40 ετών": 40,
}
DEFAULT_FLOOR = 1  # ground floors and basements are not what this buyer wants
DEFAULT_AGE = 40  # a 50-60-year-old block is not shown unless asked for


def municipality(d: dict) -> str:
    """'Αργυρούπολη (Κέντρο)' → 'Αργυρούπολη'."""
    return (d.get("neighborhood") or "").split(" (")[0].strip()


def _municipality_counts(pool: list[dict]) -> dict[str, int]:
    """Listings per municipality, Latin spellings ('Nea Ionia') folded into the Greek name."""
    raw: dict[str, int] = {}
    for d in pool:
        if (m := municipality(d)) and m != "Select":
            raw[m] = raw.get(m, 0) + 1
    greek = [m for m in raw if not m.isascii()]
    counts = {m: raw[m] for m in greek}
    for m in raw:
        if m.isascii():
            g = next((g for g in greek if nl_search.area_matches(m, g)), m)
            counts[g] = counts.get(g, 0) + raw[m]
    return counts


def _key_of(options: dict, value) -> str:
    return next((k for k, v in options.items() if v == value), next(iter(options)))


def _filter_editor(f: SearchFilters, pool: list[dict]) -> SearchFilters:
    """Every filter on screen, pre-filled from what the search understood (or the defaults)."""
    ver = st.session_state.get("f_ver", 0)
    year = date.today().year
    counts = _municipality_counts(pool)
    options = sorted(counts, key=lambda m: -counts[m])
    picked: list[str] = []  # "Παπάγος"/"Papagos" from the search → the "Παπάγου" option
    for a in f.areas:
        o = next((o for o in options if nl_search.area_matches(a, o)), a)
        if o not in picked:
            picked.append(o)
    options += [a for a in picked if a not in counts]
    floor = f.floor_min if f.floor_min is not None else DEFAULT_FLOOR
    age = year - f.year_min if f.year_min else DEFAULT_AGE
    with st.container(border=True, key="filters"):
        c1, c2, c3 = st.columns([3, 1, 1])
        areas = c1.multiselect(
            "Περιοχή",
            options,
            default=picked,
            format_func=lambda m: f"{m} ({counts[m]})" if m in counts else m,
            placeholder="Όλες οι περιοχές",
            key=f"fe_areas_{ver}",
        )
        pmax = c2.number_input(
            "Τιμή έως (€)",
            0,
            5_000_000,
            int(f.price_max or 0),
            10_000,
            key=f"fe_pmax_{ver}",
            help="0 = χωρίς όριο",
        )
        amin = c3.number_input(
            "Από τ.μ.",
            0,
            1000,
            int(f.area_min or 0),
            5,
            key=f"fe_amin_{ver}",
            help="0 = χωρίς όριο",
        )
        c4, c5, c6, c7 = st.columns(4)
        cur = next((n for n, v in BEDROOMS.items() if v == (f.bedrooms_min, f.bedrooms_max)), "Όλα")
        beds = c4.selectbox(
            "Υπνοδωμάτια", list(BEDROOMS), index=list(BEDROOMS).index(cur), key=f"fe_beds_{ver}"
        )
        floor_lbl = c5.selectbox(
            "Όροφος",
            list(FLOORS),
            index=list(FLOORS).index(_key_of(FLOORS, floor)),
            key=f"fe_floor_{ver}",
            help="Αγγελίες χωρίς δηλωμένο όροφο (συνήθως ισόγεια) κρύβονται όταν βάλεις όροφο.",
        )
        age_lbl = c6.selectbox(
            "Ηλικία κτιρίου",
            list(AGES),
            index=list(AGES).index(_key_of(AGES, age)),
            key=f"fe_age_{ver}",
            help="Από το έτος κατασκευής ή ανακαίνισης. Αγγελίες χωρίς έτος κρύβονται.",
        )
        kinds = c7.multiselect(
            "Τύπος",
            list(nl_search.KIND_LABEL),
            default=f.kinds,
            format_func=lambda k: nl_search.KIND_LABEL.get(k, k),
            placeholder="Όλοι",
            key=f"fe_kinds_{ver}",
        )
        c8, c9, c10 = st.columns([2, 1, 1], vertical_alignment="bottom")
        wants = c8.multiselect(
            "Να έχει",
            list(nl_search.WANT_LABEL),
            default=f.wants,
            format_func=lambda k: nl_search.WANT_LABEL.get(k, k),
            placeholder="π.χ. ανελκυστήρα, πάρκινγκ",
            key=f"fe_wants_{ver}",
        )
        priv = c9.checkbox("Μόνο από ιδιώτη", f.private_only, key=f"fe_priv_{ver}")
        unfinished = c10.checkbox("Και ημιτελή κτίρια", f.include_unfinished, key=f"fe_unf_{ver}")
    bmin, bmax = BEDROOMS[beds]
    max_age = AGES[age_lbl]
    return f.model_copy(
        update={
            "price_max": int(pmax) or None,
            "area_min": float(amin) or None,
            "bedrooms_min": bmin,
            "bedrooms_max": bmax,
            "areas": areas,
            "floor_min": FLOORS[floor_lbl],
            "year_min": year - max_age if max_age else None,
            "kinds": kinds,
            "wants": wants,
            "private_only": priv,
            "include_unfinished": unfinished,
        }
    )


def _save_mandate(text: str, f: SearchFilters) -> None:
    try:
        shortlist.save_mandate(text, f)
        _flash("ok", "Αποθηκεύτηκε — ο agent θα σου προτείνει αγγελίες στη σελίδα Shortlist.")
    except shortlist.StorageNotConfigured as e:
        _flash("error", f"Δεν αποθηκεύτηκε: {e}")
    except Exception as e:
        _flash("error", f"Δεν αποθηκεύτηκε: {_reason(e)}")


def _understood_html(f: SearchFilters) -> str:
    chips = "".join(
        f"<span>{html.escape(p)}</span>" for p in _greek_numbers(nl_search.describe(f)).split(" · ")
    )
    return f'<div class="hg-understood"><b>Κατάλαβα:</b>{chips}</div>'


def page_search(listings: list[dict]) -> None:
    _show_flash()
    with st.container(key="hero"):
        st.markdown("## Βρες το σπίτι που ψάχνεις")
        st.caption("Γράψε το όπως το λες. Θα βρω τις πιο αξιόλογες αγγελίες και θα σου πω γιατί.")
        with st.form("search_form", border=False):
            c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
            text = c1.text_input(
                "Τι ψάχνεις;",
                key="q_text",
                max_chars=nl_search.MAX_CHARS,
                placeholder="π.χ. δυάρι στον Χολαργό έως 180.000€, από 60 τ.μ., με ανελκυστήρα",
                label_visibility="collapsed",
            )
            submitted = c2.form_submit_button("Αναζήτηση", type="primary", width="stretch")
        with st.container(key="examples", horizontal=True, gap="small"):
            st.markdown(
                '<span class="hg-try">Δοκίμασε:</span>', unsafe_allow_html=True, width="content"
            )
            for i, (label, q) in enumerate(EXAMPLES.items()):
                st.button(label, key=f"ex{i}", on_click=_example_clicked, args=(q,))
    if submitted:
        if text.strip():
            _run_query(text)
        else:
            st.session_state["nl_error"] = "Γράψε πρώτα τι σπίτι ψάχνεις."
    if st.session_state.get("nl_error"):
        st.error(st.session_state["nl_error"])

    base = st.session_state.get("nl_filters")
    asked = base is not None
    stale_ok = st.session_state.get("include_stale", False)
    pool = nl_search.candidates(listings, include_stale=stale_ok)
    if asked:
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        understood = c1.empty()
        c2.button("✖ Καθαρισμός", key="clear_q", on_click=_clear_query, width="stretch")
    f = _filter_editor(base or SearchFilters(), pool)
    if asked:
        understood.markdown(_understood_html(f), unsafe_allow_html=True)

    hits = [(m, d, nl_search.advise(d)) for d in pool if (m := nl_search.match(d, f))]
    medians = _ppm_medians(pool)
    for _, d, adv in hits:
        adv["cmp"] = _vs_median(d, medians)
    n = f"{len(hits):,}".replace(",", ".")
    top = st.columns([4, 3, 3], vertical_alignment="center")
    top[0].markdown(
        f'<div class="hg-count"><b>{n}</b> {"αγγελία" if len(hits) == 1 else "αγγελίες"}</div>',
        unsafe_allow_html=True,
    )
    sort = top[1].selectbox("Ταξινόμηση", list(SORTS), key="sort", label_visibility="collapsed")
    top[2].button(
        "🤖 Ο agent να ψάχνει γι' αυτό",
        key="save_mandate",
        on_click=_save_mandate,
        args=(st.session_state.get("nl_text") or nl_search.describe(f), f),
        width="stretch",
    )
    stale = sum(1 for d in listings if not d.get("is_fresh", True))
    if stale:
        st.checkbox(
            f"Δείξε και {stale:,} παλαιότερες αγγελίες (μπορεί να έχουν ήδη πουληθεί)".replace(
                ",", "."
            ),
            key="include_stale",
        )
    named = [a for a in f.areas if not a.isascii()] or f.areas  # "Χολαργός" over "Cholargos"
    for a in named if not stale_ok else []:
        if not any(nl_search.area_matches(a, municipality(d)) for d in pool):
            seen = [
                d["last_seen"]
                for d in listings
                if d.get("last_seen") and nl_search.area_matches(a, municipality(d))
            ]
            when = f" (τελευταία ενημέρωση {max(seen):%d/%m})" if seen else ""
            st.warning(
                f"Για «{a}» δεν έχω πρόσφατες αγγελίες{when} — ανανεώνεται στο επόμενο "
                "κατέβασμα δεδομένων. Μέχρι τότε τσέκαρε «Δείξε και παλαιότερες αγγελίες»."
            )
    if not hits:
        st.info("Καμία αγγελία δεν ταιριάζει. Χαλάρωσε κάποιο φίλτρο (π.χ. τιμή, ηλικία ή όροφο).")
        return
    hits.sort(key=lambda h: SORTS[sort](h[0][0], h[2], h[1]))

    verdicts = {}
    # One review per typed search (not per sort/filter tweak — each call takes ~15 s): the 12 best
    # matches. Tweaks keep the verdicts of listings already reviewed; the button re-runs it on
    # what is on screen now. Without a typed search the review runs only on that button.
    ver = st.session_state.get("f_ver", 0)
    store = st.session_state.setdefault("advice_v", {})
    force = st.session_state.pop("advice_force", False)
    if (asked and ver not in store) or force:
        best = sorted(hits, key=lambda h: SORTS["Καλύτερη αντιστοιχία"](h[0][0], h[2], h[1]))
        rows = [
            (
                {**d, "area_median_ppm2": round(medians[m][0])}
                if (m := municipality(d)) in medians
                else d
            )
            for _, d, _ in best[:12]
        ]
        store[ver] = _call_advisor(
            st.session_state.get("nl_text") or nl_search.describe(f), f, rows
        )
    review = store.get(ver)
    if review is not None:
        verdicts = {v.key: v for v in review.verdicts}
        with st.container(border=True, key="advice-box"):
            st.markdown("**🤖 Γνώμη συμβούλου**")
            st.write(review.summary)
            st.button(
                "🔄 Νέα γνώμη για τα τρέχοντα αποτελέσματα",
                key="advice_again",
                on_click=_advice_again,
            )
        if sort == "Καλύτερη αντιστοιχία":
            hits.sort(
                key=lambda h: ADVICE_RANK.get(
                    getattr(verdicts.get(shortlist.lkey(h[1])), "label", ""), 3
                )
            )
    else:
        if st.session_state.get("advice_err"):
            st.caption(f"🤖 {st.session_state['advice_err']}")
        st.button(
            "🤖 Γνώμη AI για τις 12 καλύτερες",
            key="advice_again",
            on_click=_advice_again,
        )
    if st.toggle("🗺 Χάρτης αποτελεσμάτων", key="show_map"):
        from scout.ui import components

        components.results_map([h[1] for h in hits], key="search-map", height=380)
    limit = st.session_state.get("limit", PAGE_SIZE)
    for (_pct, reasons), d, adv in hits[:limit]:
        result_card(
            d,
            adv,
            reasons,
            "s",
            [("Λεπτομέρειες", open_detail, (d["id"],)), _star_action(d)],
            advice=verdicts.get(shortlist.lkey(d)),
        )
    if len(hits) > limit:
        st.button(
            f"Δείξε περισσότερες ({len(hits) - limit} ακόμα)",
            key="more",
            on_click=_more,
            width="stretch",
        )


def _call_advisor(query: str, f: SearchFilters, rows: list[dict]):
    """One Claude review of ``rows`` (errors and the per-session cap become a caption)."""
    if st.session_state.get("advice_calls", 0) >= MAX_ADVICE:
        st.session_state["advice_err"] = "Έφτασες το όριο γνωμών για αυτή τη συνεδρία."
        return None
    st.session_state["advice_calls"] = st.session_state.get("advice_calls", 0) + 1
    with st.spinner(f"🤖 Ο σύμβουλος εξετάζει τις {len(rows)} καλύτερες αγγελίες…"):
        try:
            result = advisor.review(query or nl_search.describe(f), rows)
            st.session_state["advice_err"] = ""
            return result
        except advisor.AdvisorError as e:
            st.session_state["advice_err"] = str(e)
            return None


def _advice_again() -> None:
    st.session_state["advice_force"] = True


# ---- shortlist -----------------------------------------------------------------------------


def _review(mandate_id: int, key: str, approve: bool) -> None:
    try:
        shortlist.decide(mandate_id, key, approve)
        if approve:
            watch_keys().add(key)
    except Exception as e:
        _flash("error", f"Δεν αποθηκεύτηκε: {_reason(e)}")


def _delete_mandate(mandate_id: int) -> None:
    try:
        shortlist.delete_mandate(mandate_id)
    except Exception as e:
        _flash("error", f"Δεν διαγράφηκε: {_reason(e)}")


def page_shortlist(listings: list[dict]) -> None:
    st.markdown("## 🤖 Shortlist του agent")
    st.caption(
        "Ο agent κρατά τις αναζητήσεις σου και διαλέγει τις καλύτερες αγγελίες. Εσύ εγκρίνεις ή απορρίπτεις."
    )
    _show_flash()
    try:
        mandates = shortlist.list_mandates()
    except shortlist.StorageNotConfigured as e:
        st.warning(
            f"{e} Πρόσθεσέ το στα Secrets του Streamlit για να αποθηκεύονται οι αναζητήσεις."
        )
        return
    except Exception as e:
        st.error(f"Δεν μπόρεσα να διαβάσω τις αναζητήσεις: {_reason(e)}")
        return
    if not mandates:
        st.info(
            "Καμία αποθηκευμένη αναζήτηση. Γράψε τι ψάχνεις στην Αναζήτηση και πάτα «🤖 Ο agent να ψάχνει γι' αυτό»."
        )
        return
    for m in mandates:
        picks = shortlist.pick(m.filters, listings, m.approved | m.rejected)
        with st.expander(
            f"{m.text}  ·  ✅ {len(m.approved)}  ·  ❌ {len(m.rejected)}", expanded=True
        ):
            st.caption("Κατάλαβα: " + nl_search.describe(m.filters))
            st.button("🗑 Διαγραφή", key=f"del{m.id}", on_click=_delete_mandate, args=(m.id,))
            if not picks:
                st.write("Καμία νέα πρόταση αυτή τη στιγμή.")
            for d, adv, reasons in picks:
                key = shortlist.lkey(d)
                result_card(
                    d,
                    adv,
                    reasons,
                    f"m{m.id}",
                    [
                        ("Λεπτομέρειες", open_detail, (d["id"],)),
                        ("✅ Έγκριση", _review, (m.id, key, True)),
                        ("❌ Απόρριψη", _review, (m.id, key, False)),
                    ],
                )


# ---- starred -------------------------------------------------------------------------------


def page_watchlist(listings: list[dict]) -> None:
    st.markdown("## ⭐ Αγαπημένα")
    _show_flash()
    keys = watch_keys()
    if not st.session_state.get("watch_persisted"):
        st.caption(
            "ℹ️ Τα αγαπημένα ισχύουν μόνο για αυτή τη συνεδρία (λείπει το GITHUB_TOKEN στα Secrets)."
        )
    starred = [d for d in listings if shortlist.lkey(d) in keys]
    if not starred:
        st.info("Δεν έχεις αγαπημένα ακόμα. Πάτα «☆ Αγαπημένο» σε μια αγγελία.")
        return
    prices = [d["price"] for d in starred if d.get("price")]
    ppm = [d["price_per_m2"] for d in starred if d.get("price_per_m2")]
    c = st.columns(3)
    c[0].metric("Αγαπημένα", len(starred))
    c[1].metric("Σύνολο τιμών", eur(sum(prices)) if prices else "—")
    c[2].metric("Διάμεσο €/τ.μ.", eur(statistics.median(ppm)) if ppm else "—")
    for d in sorted(starred, key=lambda d: -(d.get("score") or 0)):
        result_card(
            d,
            nl_search.advise(d),
            [],
            "w",
            [("Λεπτομέρειες", open_detail, (d["id"],)), _star_action(d)],
        )
