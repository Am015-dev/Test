"""Buyer-facing pages: search (the home page), saved searches, favourites and one listing.
Greek UI for a private buyer who will let the flat out. Cards are native Streamlit widgets so
every button is real.

Favourites and saved searches are stored privately when storage is configured (see
``shortlist``); otherwise they last until the page is closed.
"""

from __future__ import annotations

import html
import re
import statistics
from datetime import date

import streamlit as st

from scout import acquisition, advisor, market_intel, nl_search, shortlist
from scout.market_intel import municipality
from scout.nl_search import SearchFilters

PAGE_SIZE = 12
MAX_ADVICE = 25  # AI second opinions per browser session — bounds API cost
ADVICE_TONE = {"Αξίζει": "good", "Με επιφύλαξη": "warn", "Απόφυγε": "bad"}
MAX_SEARCHES = 30  # AI-parsed searches per browser session — bounds API cost
NAV_DETAIL = "Αγγελία"  # label of the listing-detail page (cards link to it)
NAV_SEARCH = "Αναζήτηση"  # label of the search page (the listing page links back to it)
AI_LABEL = "Δεύτερη γνώμη (AI)"

# One scale for every score on screen (cards, map colours and legend): see components.
SCORE_GOOD, SCORE_MID = 50, 30
SCORE_LEGEND = (
    f"Σκορ 0–100: ζητούμενη τιμή σε σχέση με παρόμοια, ηλικία κτιρίου, απόδοση ενοικίου, "
    f"μετρό, ενεργειακή κλάση. {SCORE_GOOD}+ καλό · {SCORE_MID}–{SCORE_GOOD - 1} μέτριο · "
    f"κάτω από {SCORE_MID} αδύναμο."
)
SCORE_HELP = (
    "Σκορ = 60% βασικό σκορ (απόδοση ενοικίου, ενεργειακή κλάση, μετρό, μείωση τιμής, "
    "ιδιώτης) + 40% τιμή σε σχέση με παρόμοια (20% φθηνότερο = πλήρεις μονάδες). "
    "Μετά × ηλικία κτιρίου (έως 15 ετών ×1, 16–30 ×0,95, 31–40 ×0,8, 41–50 ×0,6, πάνω από 50 "
    "×0,45, άγνωστη ×0,9). Υπό παράδοση ×0,6, ημιτελές ×0,25. "
    "▲ βοηθά · ▼ ρίχνει · ≈ ουδέτερο · ? άγνωστο."
)
CONF_HELP = (
    "Αξιοπιστία σύγκρισης: Υψηλή = 12+ παρόμοια και το μεσαίο 50% των τιμών τους απέχει έως "
    "25% του διάμεσου· Χαμηλή = λιγότερα από 8 παρόμοια ή εύρος πάνω από 45%· αλλιώς Μέτρια. "
    "Παρόμοια = ίδια περιοχή, ηλικία κτιρίου και (όπου γίνεται) μέγεθος και όροφος."
)
UNFINISHED_NOTE = "Ημιτελές / υπό κατασκευή — χρειάζεται επιπλέον κεφάλαιο πριν νοικιαστεί"

EXAMPLES = {
    "Δυάρι στον Χολαργό": "δυάρι στον Χολαργό έως 180Χ με ανελκυστήρα",
    "Τριάρι Παπάγου": "τριάρι στο Παπάγου ή στην Αγία Παρασκευή κάτω από 250.000€ με πάρκινγκ",
    "Έχω 200.000 €": "έχω 200 χιλιάδες να επενδύσω στον Χολαργό",
    "Γκαρσονιέρα έως 90.000 €": "γκαρσονιέρα μέχρι 90 χιλιάδες",
}


def gross_yield(d: dict) -> float | None:
    """12 × monthly rent ÷ price — the same number on the card, the sort and the listing."""
    rent = d.get("listed_rent") or d.get("est_monthly_rent")
    return 12 * rent / d["price"] if rent and d.get("price") else None


def _unfinished(d: dict) -> bool:
    return bool(d.get("is_unfinished"))


SORTS = {
    # Unfinished shells (only shown when asked for) always rank last on the score/yield sorts.
    "Σκορ αγοράς": lambda pct, adv, d: (_unfinished(d), -pct, -adv["score"], d["price"]),
    "Υψηλότερη απόδοση": lambda pct, adv, d: (_unfinished(d), -(gross_yield(d) or 0), d["price"]),
    "Χαμηλότερη τιμή": lambda pct, adv, d: (d["price"], -adv["score"]),
    "Χαμηλότερο €/τ.μ.": lambda pct, adv, d: (d.get("price_per_m2") or 1e9, d["price"]),
    "Φθηνότερο από παρόμοια": lambda pct, adv, d: (
        adv["cmp"]["pct"] if adv.get("cmp") else 9,
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


def _r(v: float, step: int) -> int:
    """Round to ``step`` (10 €, 100 €…): no fake precision on estimates."""
    return int(round(v / step) * step)


def pct1(v: float) -> str:
    """0.0463 -> '4,6%' (Greek decimal comma)."""
    return f"{v * 100:.1f}".replace(".", ",") + "%"


def _signed_pct(v: float) -> str:
    """-0.331 -> '−33%' with a real minus sign, for display (not for st.metric deltas)."""
    return f"{v:+.0%}".replace("-", "−")


def has_ai() -> bool:
    """Whether the optional AI features (text parsing, second opinion) are configured."""
    from scout.config import get_settings

    return bool(get_settings().anthropic_api_key)


def confidence(cmp: dict) -> str:
    """Υψηλή/Μέτρια/Χαμηλή from how many comparables there are and how spread their €/m² is."""
    spread = (cmp["p75"] - cmp["p25"]) / cmp["ppm"] if cmp.get("ppm") else 1.0
    if cmp["n"] >= 12 and spread <= 0.25:
        return "Υψηλή"
    if cmp["n"] < 8 or spread > 0.45:
        return "Χαμηλή"
    return "Μέτρια"


def data_line(listings: list[dict]) -> str:
    """Sidebar data line: the real date of the newest data, e.g. 'Δεδομένα XE.gr έως 30/10'."""
    seen = [d["last_seen"] for d in listings if d.get("last_seen")]
    if not seen:
        return "Δεν υπάρχουν δεδομένα ακόμα."
    newest = max(seen)
    days = (date.today() - newest.date()).days
    late = f" (πριν {days} μέρες)" if days >= 3 else ""
    n = f"{len(listings):,}".replace(",", ".")
    return f"Δεδομένα XE.gr έως {newest:%d/%m}{late} · {n} αγγελίες"


# ---- session state: starred listings -------------------------------------------------------

SESSION_ONLY = "Τα αγαπημένα κρατιούνται μέχρι να κλείσεις τη σελίδα."


def watch_keys() -> set[str]:
    """Starred listing keys for this session, loaded from storage once."""
    if "watch" not in st.session_state:
        keys: set[str] = set()
        try:
            keys = shortlist.watch_set()
            st.session_state["watch_persisted"] = True
        except shortlist.StorageNotConfigured:
            st.session_state["watch_persisted"] = False
        except Exception as e:  # network / auth: keep working, say so once
            st.session_state["watch_persisted"] = False
            _flash("error", f"Τα αγαπημένα δεν φορτώθηκαν ({_reason(e)}). {SESSION_ONLY}")
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
            _flash(
                "error", f"Δεν αποθηκεύτηκε ({_reason(e)}) — ισχύει μέχρι να κλείσεις τη σελίδα."
            )


def open_detail(listing_id: int) -> None:
    st.session_state["page"] = NAV_DETAIL
    st.session_state["detail_id"] = listing_id


def _reason(e: Exception) -> str:
    """A short, plain reason — never a URL, a service name or a traceback."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status in (401, 403):
        return "δεν επιτρέπεται η πρόσβαση στην αποθήκευση"
    if status == 404:
        return "δεν βρέθηκε το αρχείο αποθήκευσης"
    if status is not None:
        return "σφάλμα αποθήκευσης — δοκίμασε ξανά σε λίγο"
    if isinstance(e, OSError | TimeoutError):
        return "δεν υπάρχει σύνδεση — δοκίμασε ξανά σε λίγο"
    return "απρόσμενο σφάλμα"


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


def rent_html(d: dict) -> str:
    """'Ενοίκιο ~980 €/μήνα · μικτή απόδοση 4,6% (εκτίμηση περιοχής)', or '' without rent."""
    gy = gross_yield(d)
    if gy is None:
        return ""
    rent = d.get("listed_rent") or d.get("est_monthly_rent")
    note = (
        ""
        if d.get("listed_rent")
        else " <span>(εκτίμηση περιοχής)</span>" if d.get("rent_estimated", True) else ""
    )
    return (
        f'<div class="hg-rent">Ενοίκιο ~<b>{eur(_r(rent, 10))}</b>/μήνα · '
        f"μικτή απόδοση <b>{pct1(gy)}</b>{note}</div>"
    )


def comps_badge(cmp: dict) -> tuple[str, str]:
    """(tone, '−33% vs 5 παρόμοια · χαμηλή αξιοπιστία') — the short card version."""
    pct = cmp["pct"]
    tone = "good" if pct <= -0.1 else "bad" if pct >= 0.1 else "muted"
    conf = confidence(cmp).lower()
    return tone, f"{_signed_pct(pct)} €/τ.μ. vs {cmp['n']} παρόμοια · {conf} αξιοπιστία"


def _card_html(d: dict, adv: dict) -> str:
    """Title/location, the key facts in a fixed order, rent line and badges — one block."""
    e = html.escape
    title = e(d.get("title") or "Αγγελία")
    loc = f'<span class="hg-loc">{e(d["neighborhood"])}</span>' if d.get("neighborhood") else ""
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
    # Only past the default age filter (shown when the buyer relaxes it) — same 40-year line.
    if age is not None and age > DEFAULT_AGE and not d.get("renovated_year"):
        badges.append(("bad" if age >= 50 else "warn", f"Παλιό κτίριο — {age} ετών"))
    if (d.get("year_built") or 0) >= date.today().year:
        badges.append(("warn", "Νεόδμητο — έλεγξε ότι έχει παραδοθεί"))
    elif age is None:
        badges.append(("muted", "Έτος κατασκευής: δεν δηλώνεται"))
    for flag in advisor.red_flags(d):
        if not flag.startswith(("Κτίριο", "Χωρίς έτος", "Ημιτελές")):
            badges.append(("warn", flag))
    if cmp := adv.get("cmp"):
        badges.append(comps_badge(cmp))
    if twins := adv.get("twins"):
        low = twins[0]["price"]
        cheaper = f", φθηνότερη {eur(low)}" if low < d["price"] else ""
        badges.append(("warn", f"Ίδιο σπίτι σε {len(twins)} ακόμα αγγελίες{cheaper}"))
    first = d.get("first_price")
    if d.get("price_dropped") and first and first > d["price"]:
        badges.append(("drop", f"Μείωση από {eur(first)} (−{1 - d['price'] / first:.0%})"))
    elif d.get("price_dropped"):
        badges.append(("drop", "Μειώθηκε η τιμή"))
    if d.get("is_private_seller"):
        badges.append(("priv", "Ιδιώτης"))
    if d.get("days_on_market"):
        badges.append(("muted", f"{d['days_on_market']} μέρες στην αγορά"))
    out = f'<div class="hg-head"><span class="hg-title">{title}</span>{loc}</div>'
    if facts:
        out += '<div class="hg-facts">' + "".join(f"<span>{f}</span>" for f in facts) + "</div>"
    out += rent_html(d)
    if _unfinished(d):
        out += f'<div class="hg-note-bad">{UNFINISHED_NOTE}</div>'
    if badges:
        out += (
            '<div class="hg-badges">'
            + "".join(f'<span class="hg-b hg-b-{c}">{e(t)}</span>' for c, t in badges)
            + "</div>"
        )
    return out


def _score_html(adv: dict) -> str:
    s = adv["score"]
    tone = "hi" if s >= SCORE_GOOD else "mid" if s >= SCORE_MID else "lo"
    return (
        f'<span class="hg-score hg-score-{tone}" title="{html.escape(SCORE_HELP)}">'
        f"<small>Σκορ</small><b>{s}</b></span>"
    )


ARROWS = {1: ("▲", "up"), -1: ("▼", "down"), 0: ("≈", "flat"), None: ("?", "flat")}


def parts_html(adv: dict) -> str:
    """The visible score breakdown: 'τιμή vs παρόμοια ▲ · ηλικία ▼ · απόδοση ▲'."""
    spans = [
        f'<span class="hg-p-{ARROWS[sign][1]}">{html.escape(label)} {ARROWS[sign][0]}</span>'
        for label, sign in adv.get("parts", [])
    ]
    return '<div class="hg-parts">' + "".join(spans) + "</div>" if spans else ""


def result_card(d: dict, adv: dict, k: str, actions: list, advice=None) -> None:
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
            st.markdown(_score_html(adv), unsafe_allow_html=True, width="content")
        if parts := parts_html(adv):
            st.markdown(parts, unsafe_allow_html=True)
        st.markdown(_card_html(d, adv), unsafe_allow_html=True)
        if advice is not None:
            st.markdown(
                f'<div class="hg-advice hg-advice-{ADVICE_TONE[advice.label]}">'
                f"<b>{AI_LABEL}: {html.escape(advice.label)}</b> — "
                f"{html.escape(advice.reason)}</div>",
                unsafe_allow_html=True,
            )
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


def buyer_view(d: dict, intel) -> dict:
    """Score + like-for-like comparables + same-flat twins for one listing."""
    cmp = intel.comps(d)
    adv = nl_search.advise(d, cmp["pct"] if cmp else None)
    return {**adv, "cmp": cmp, "twins": intel.twins(d)}


def buyer_scores(listings: list[dict], intel=None) -> dict[int, int]:
    """The buyer score (the one on the cards) for every listing, by id."""
    intel = intel or market_intel.build(listings)
    out = {}
    for d in listings:
        cmp = intel.comps(d)
        out[d["id"]] = nl_search.advise(d, cmp["pct"] if cmp else None)["score"]
    return out


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

_BEDROOM_WORDS = {"γκαρσονιερ": 0, "studio": 0, "δυαρι": 1, "τριαρι": 2, "τεσσαρι": 3}
_AMOUNT = re.compile(r"(\d[\d.]*)(?:,\d+)?\s*(χιλ|χ(?![α-ω])|k(?![a-z]))?")


def local_parse(text: str, areas: list[str]) -> SearchFilters:
    """Without the AI parser: read area names, price and flat size words from the text."""
    t = nl_search._norm(text)
    found = [a for a in areas if nl_search._area_in(a, t)]
    beds = next((n for w, n in _BEDROOM_WORDS.items() if w in t), None)
    wants = [w for w, words in nl_search.WANT_WORDS.items() if any(k in t for k in words)]
    price = area_min = None
    for m in _AMOUNT.finditer(t):
        n = int(m.group(1).replace(".", "") or 0) * (1000 if m.group(2) else 1)
        if t[m.end() : m.end() + 4].lstrip().startswith(("τ.μ", "τμ", "m2", "τετρ")):
            area_min = n
        elif n >= 20_000:
            price = max(price or 0, n)
    invest = "επενδυ" in t
    return SearchFilters(
        areas=found,
        price_max=None if invest else price,
        budget=price if invest else None,
        area_min=area_min,
        bedrooms_min=beds,
        bedrooms_max=beds,
        wants=wants,
    )


def _run_query(text: str) -> None:
    text = text.strip()
    if not text:
        return
    st.session_state.pop("show_all", None)
    if not has_ai():
        options = st.session_state.get("area_options", [])
        _set_query(text, local_parse(text, options))
        return
    used = st.session_state.get("nl_calls", 0)
    if used >= MAX_SEARCHES:
        st.session_state["nl_error"] = (
            "Έφτασες το όριο αναζητήσεων με κείμενο για αυτή τη συνεδρία — χρησιμοποίησε τα "
            "φίλτρα ή ανανέωσε τη σελίδα."
        )
        return
    try:
        _set_query(text, nl_search.parse_query(text))
        st.session_state["nl_calls"] = used + 1
    except nl_search.SearchParseError:
        st.session_state["nl_error"] = (
            "Δεν μπόρεσα να διαβάσω την αναζήτηση — δοκίμασε άλλη διατύπωση ή τα φίλτρα."
        )


def _set_query(text: str, f: SearchFilters) -> None:
    st.session_state["nl_filters"] = f
    st.session_state["nl_text"] = text
    st.session_state["nl_error"] = ""
    st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1
    st.session_state["limit"] = PAGE_SIZE


def _example_clicked(text: str) -> None:
    st.session_state["q_text"] = text
    _run_query(text)


def _clear_query() -> None:
    for k in ("nl_filters", "nl_text", "nl_error", "q_text", "show_all"):
        st.session_state.pop(k, None)
    st.session_state["limit"] = PAGE_SIZE
    st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1


def _show_all() -> None:
    """Drop the floor and age filters (the defaults or what the search set)."""
    st.session_state["show_all"] = True
    f = st.session_state.get("nl_filters")
    if f is not None:
        st.session_state["nl_filters"] = f.model_copy(update={"floor_min": None, "year_min": None})
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


ATHENS = {"Αθήνα", "Athina", "Athens"}


def area_name(d: dict) -> str:
    """The area a listing is in: its municipality, except central Athens, where the quarter in
    brackets is the area ('Αθήνα (Αμπελόκηποι)' → 'Αμπελόκηποι'). Same rule as
    ``area_insights.area_name`` (the "where to buy" page links here with these names)."""
    n = d.get("neighborhood") or ""
    m = municipality(d)
    if m in ATHENS and "(" in n:
        return n.split("(", 1)[1].rstrip(") ").strip() or m
    return m


def _area_hit(d: dict, areas: list[str]) -> bool:
    """Whether ``d`` is in one of ``areas``: a central-Athens quarter by its own name (or by
    'Αθήνα'), anything else by the usual location rule of ``nl_search.match``."""
    if not areas:
        return True
    name, m = area_name(d), municipality(d)
    if name != m:
        return any(nl_search.area_matches(a, name) or nl_search.area_matches(a, m) for a in areas)
    probe = SearchFilters(areas=areas, include_unfinished=True)
    return nl_search.match(d, probe) is not None


def match(d: dict, f: SearchFilters):
    """``nl_search.match`` with the area part done by ``_area_hit`` (Athens quarters)."""
    hit = nl_search.match(d, f.model_copy(update={"areas": []}))
    return hit if hit is not None and _area_hit(d, f.areas) else None


def _municipality_counts(pool: list[dict]) -> dict[str, int]:
    """Listings per area (see ``area_name``), Latin spellings folded into the Greek name."""
    raw: dict[str, int] = {}
    for d in pool:
        if (m := area_name(d)) and m != "Select":
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
    """Every filter on screen, pre-filled from the search (or the defaults)."""
    ver = st.session_state.get("f_ver", 0)
    year = date.today().year
    counts = _municipality_counts(pool)
    options = sorted(counts, key=lambda m: -counts[m])
    st.session_state["area_options"] = options  # for the parser without AI
    picked: list[str] = []  # "Παπάγος"/"Papagos" from the search → the "Παπάγου" option
    for a in f.areas:
        o = next((o for o in options if nl_search.area_matches(a, o)), a)
        if o not in picked:
            picked.append(o)
    options += [a for a in picked if a not in counts]
    relaxed = st.session_state.get("show_all", False)
    floor = f.floor_min if f.floor_min is not None else (None if relaxed else DEFAULT_FLOOR)
    age = year - f.year_min if f.year_min else (None if relaxed else DEFAULT_AGE)
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
        c4, c5, c6 = st.columns(3)
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
        more = bool(f.kinds or f.wants or f.private_only or f.include_unfinished)
        with st.expander("Περισσότερα φίλτρα", expanded=more):
            c7, c8 = st.columns(2)
            kinds = c7.multiselect(
                "Τύπος",
                list(nl_search.KIND_LABEL),
                default=f.kinds,
                format_func=lambda k: nl_search.KIND_LABEL.get(k, k),
                placeholder="Όλοι",
                key=f"fe_kinds_{ver}",
            )
            wants = c8.multiselect(
                "Να έχει",
                list(nl_search.WANT_LABEL),
                default=f.wants,
                format_func=lambda k: nl_search.WANT_LABEL.get(k, k),
                placeholder="π.χ. ανελκυστήρα, πάρκινγκ",
                key=f"fe_wants_{ver}",
            )
            c9, c10 = st.columns(2)
            priv = c9.checkbox("Μόνο από ιδιώτη", f.private_only, key=f"fe_priv_{ver}")
            unfinished = c10.checkbox(
                "Και ημιτελή κτίρια",
                f.include_unfinished,
                key=f"fe_unf_{ver}",
                help="Εμφανίζονται σημειωμένα και με χαμηλό σκορ: θέλουν επιπλέον κεφάλαιο "
                "πριν νοικιαστούν.",
            )
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
        _flash(
            "ok",
            "Αποθηκεύτηκε — νέες αγγελίες γι' αυτή την αναζήτηση θα βρίσκεις στη σελίδα "
            "«Αποθηκευμένες αναζητήσεις».",
        )
    except shortlist.StorageNotConfigured:
        _flash("error", "Η αποθήκευση αναζητήσεων δεν είναι διαθέσιμη σε αυτή την εγκατάσταση.")
    except Exception as e:
        _flash("error", f"Δεν αποθηκεύτηκε: {_reason(e)}")


def _understood_html(f: SearchFilters) -> str:
    chips = "".join(
        f"<span>{html.escape(p)}</span>" for p in _greek_numbers(nl_search.describe(f)).split(" · ")
    )
    return f'<div class="hg-understood"><b>Αναζήτηση για:</b>{chips}</div>'


def _hidden_note(f: SearchFilters) -> str:
    """What the floor/age filters hide, in words: '(ισόγεια ή χωρίς όροφο, πάνω από 40 ετών…)'."""
    why = []
    if f.floor_min is not None:
        low = "ισόγεια/υπόγεια" if f.floor_min <= 1 else f"κάτω από {f.floor_min:g}ο όροφο"
        why.append(f"{low} ή χωρίς δηλωμένο όροφο")
    if f.year_min:
        why.append(f"πάνω από {date.today().year - f.year_min} ετών ή χωρίς έτος")
    return ", ".join(why)


def _apply_area_pick() -> None:
    """Another page sent the buyer here for one area (session key ``area_pick``)."""
    pick = st.session_state.pop("area_pick", None)
    if pick:
        for k in ("nl_text", "nl_error", "q_text", "show_all"):
            st.session_state.pop(k, None)
        st.session_state["nl_filters"] = SearchFilters(areas=[pick])
        st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1
        st.session_state["limit"] = PAGE_SIZE


def page_search(listings: list[dict]) -> None:
    _show_flash()
    _apply_area_pick()
    ai = has_ai()
    with st.container(key="hero"):
        st.markdown("## Διαμέρισμα για επένδυση και ενοικίαση")
        st.caption(
            "Αγγελίες πώλησης από το XE.gr. Για κάθε σπίτι: ζητούμενη τιμή σε σχέση με παρόμοια, "
            "εκτίμηση ενοικίου και τι κοστίζει η αγορά. Δεν είναι εκτίμηση αξίας."
        )
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
        if not ai:
            st.caption(
                "Το κείμενο διαβάζεται απλά: περιοχή, τιμή, τ.μ., δυάρι/τριάρι. Τα υπόλοιπα "
                "ρύθμισέ τα στα φίλτρα από κάτω."
            )
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
        c2.button("Καθαρισμός", key="clear_q", on_click=_clear_query, width="stretch")
    f = _filter_editor(base or SearchFilters(), pool)
    if asked:
        understood.markdown(_understood_html(f), unsafe_allow_html=True)

    intel = market_intel.build(listings)
    hits = [(m, d, buyer_view(d, intel)) for d in pool if (m := match(d, f))]
    n = f"{len(hits):,}".replace(",", ".")
    top = st.columns([4, 3, 3], vertical_alignment="center")
    top[0].markdown(
        f'<div class="hg-count"><b>{n}</b> {"αγγελία" if len(hits) == 1 else "αγγελίες"}</div>',
        unsafe_allow_html=True,
    )
    sort = top[1].selectbox("Ταξινόμηση", list(SORTS), key="sort", label_visibility="collapsed")
    top[2].button(
        "Αποθήκευση αναζήτησης",
        key="save_mandate",
        on_click=_save_mandate,
        args=(st.session_state.get("nl_text") or nl_search.describe(f), f),
        width="stretch",
    )
    st.caption(SCORE_LEGEND, help=SCORE_HELP)
    if f.floor_min is not None or f.year_min:
        loose = f.model_copy(update={"floor_min": None, "year_min": None})
        hidden = sum(1 for d in pool if match(d, loose)) - len(hits)
        if hidden > 0:
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            num = f"{hidden:,}".replace(",", ".")
            c1.caption(f"Κρύβονται {num} αγγελίες ({_hidden_note(f)}).")
            c2.button("Δείξε όλες", key="show_all_btn", on_click=_show_all, width="stretch")
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
        if not any(_area_hit(d, [a]) for d in pool):
            seen = [d["last_seen"] for d in listings if d.get("last_seen") and _area_hit(d, [a])]
            when = f" (τελευταία ενημέρωση {max(seen):%d/%m})" if seen else ""
            st.warning(
                f"Για «{a}» δεν υπάρχουν πρόσφατες αγγελίες{when}. Τσέκαρε «Δείξε και "
                "παλαιότερες αγγελίες» για τις προηγούμενες."
            )
    _market_panel(intel, named[:3])
    if not hits:
        st.info("Καμία αγγελία δεν ταιριάζει. Χαλάρωσε κάποιο φίλτρο (π.χ. τιμή, ηλικία ή όροφο).")
        return
    hits.sort(key=lambda h: SORTS[sort](h[0][0], h[2], h[1]))

    verdicts = _search_advice(hits, f, intel) if ai else {}
    if st.toggle("Χάρτης αποτελεσμάτων", key="show_map"):
        from scout.ui import components

        rows = [{**d, "score": adv["score"]} for _, d, adv in hits]  # the card score
        components.results_map(rows, key="search-map", height=380)
    limit = st.session_state.get("limit", PAGE_SIZE)
    for _m, d, adv in hits[:limit]:
        result_card(
            d,
            adv,
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


def _search_advice(hits: list, f: SearchFilters, intel) -> dict:
    """The optional AI second opinion on the first 12 results (only when asked for)."""
    ver = st.session_state.get("f_ver", 0)
    store = st.session_state.setdefault("advice_v", {})
    if st.session_state.pop("advice_force", False):
        rows = [advisor.with_market(d, adv, intel) for _, d, adv in hits[:12]]
        store[ver] = _call_advisor(st.session_state.get("nl_text") or nl_search.describe(f), rows)
    review = store.get(ver)
    if review is None:
        if st.session_state.get("advice_err"):
            st.caption(st.session_state["advice_err"])
        st.button(
            f"{AI_LABEL} για τις 12 πρώτες",
            key="advice_again",
            on_click=_advice_again,
            help="Προαιρετικό. Ένα γλωσσικό μοντέλο διαβάζει τα ίδια στοιχεία και σχολιάζει.",
        )
        return {}
    with st.container(border=True, key="advice-box"):
        st.markdown(f"**{AI_LABEL}**")
        st.write(review.summary)
        st.caption("Σχόλιο γλωσσικού μοντέλου πάνω στα ίδια δεδομένα — όχι εκτίμηση αξίας.")
        st.button(
            "Νέα γνώμη για τα τρέχοντα αποτελέσματα", key="advice_again", on_click=_advice_again
        )
    return {v.key: v for v in review.verdicts}


def _market_panel(intel, areas: list[str]) -> None:
    """Median asking €/m² by building age for the chosen areas, with how many listings each."""
    lines = []
    for a in areas:
        table = intel.age_table(a)
        if len(table) < 2:
            continue
        cells = [f"{r['band']} **{eur(_r(r['ppm'], 10))}** ({r['n']})" for r in table]
        lines.append(f"**{a}** · " + " · ".join(cells))
    if lines:
        with st.container(border=True, key="market-panel"):
            st.markdown("**Διάμεσο €/τ.μ. ζητούμενης τιμής ανά ηλικία κτιρίου** (πλήθος αγγελιών)")
            st.markdown("  \n".join(lines))


def _call_advisor(query: str, rows: list[dict]):
    """One AI review of ``rows`` (errors and the per-session cap become a caption)."""
    if st.session_state.get("advice_calls", 0) >= MAX_ADVICE:
        st.session_state["advice_err"] = "Έφτασες το όριο γνωμών για αυτή τη συνεδρία."
        return None
    st.session_state["advice_calls"] = st.session_state.get("advice_calls", 0) + 1
    with st.spinner("Ετοιμάζεται η δεύτερη γνώμη…"):
        try:
            result = advisor.review(query, rows)
            st.session_state["advice_err"] = ""
            return result
        except advisor.AdvisorError:
            st.session_state["advice_err"] = "Η δεύτερη γνώμη δεν είναι διαθέσιμη αυτή τη στιγμή."
            return None


def _advice_again() -> None:
    st.session_state["advice_force"] = True


# ---- saved searches ------------------------------------------------------------------------


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
    st.markdown("## Αποθηκευμένες αναζητήσεις")
    st.caption(
        "Για κάθε αναζήτηση που αποθήκευσες, οι νέες αγγελίες με το καλύτερο σκορ. Η έγκριση "
        "τη βάζει στα αγαπημένα."
    )
    _show_flash()
    try:
        mandates = shortlist.list_mandates()
    except shortlist.StorageNotConfigured:
        st.info("Η αποθήκευση αναζητήσεων δεν είναι διαθέσιμη σε αυτή την εγκατάσταση.")
        return
    except Exception as e:
        st.error(f"Δεν μπόρεσα να διαβάσω τις αναζητήσεις: {_reason(e)}")
        return
    if not mandates:
        st.info(
            "Καμία αποθηκευμένη αναζήτηση. Κάνε μια αναζήτηση και πάτα «Αποθήκευση αναζήτησης»."
        )
        return
    intel = market_intel.build(listings)
    for m in mandates:
        picks = shortlist.pick(m.filters, listings, m.approved | m.rejected)
        with st.expander(
            f"{m.text}  ·  εγκρίθηκαν {len(m.approved)}  ·  απορρίφθηκαν {len(m.rejected)}",
            expanded=True,
        ):
            st.caption("Αναζήτηση για: " + nl_search.describe(m.filters))
            st.button(
                "Διαγραφή αναζήτησης", key=f"del{m.id}", on_click=_delete_mandate, args=(m.id,)
            )
            if not picks:
                st.write("Καμία νέα αγγελία αυτή τη στιγμή.")
            for d, _adv, _reasons in picks:
                key = shortlist.lkey(d)
                result_card(
                    d,
                    buyer_view(d, intel),  # the same score as everywhere else
                    f"m{m.id}",
                    [
                        ("Λεπτομέρειες", open_detail, (d["id"],)),
                        ("Έγκριση", _review, (m.id, key, True)),
                        ("Απόρριψη", _review, (m.id, key, False)),
                    ],
                )


# ---- starred -------------------------------------------------------------------------------


def page_watchlist(listings: list[dict]) -> None:
    st.markdown("## Αγαπημένα")
    _show_flash()
    keys = watch_keys()
    if not st.session_state.get("watch_persisted"):
        st.caption(SESSION_ONLY)
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
    st.caption(SCORE_LEGEND, help=SCORE_HELP)
    intel = market_intel.build(listings)
    views = [(d, buyer_view(d, intel)) for d in starred]
    for d, adv in sorted(views, key=lambda v: (_unfinished(v[0]), -v[1]["score"])):
        result_card(d, adv, "w", [("Λεπτομέρειες", open_detail, (d["id"],)), _star_action(d)])


# ---- one listing ---------------------------------------------------------------------------


def _listing_link_table(rows: list[dict]) -> None:
    import pandas as pd

    table = pd.DataFrame(
        {
            "Αγγελία": d.get("url") or "",
            "Τιμή": eur(d.get("price")),
            "€/τ.μ.": eur(d.get("price_per_m2")),
            "τ.μ.": f"{d['area_m2']:g}" if d.get("area_m2") else "—",
            "Όροφος": _floor(d["floor"]) if d.get("floor") is not None else "—",
            "Έτος": str(d.get("year_built") or "—"),
            "Περιοχή": d.get("neighborhood") or "—",
        }
        for d in rows
    )
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={"Αγγελία": st.column_config.LinkColumn("Αγγελία", display_text="Άνοιγμα ↗")},
    )


def _ask_listing(d: dict, adv: dict, intel) -> None:
    rows = [advisor.with_market(d, adv, intel)]
    review = _call_advisor("Αξιολόγησε αυτή την αγγελία για αγορά και ενοικίαση.", rows)
    st.session_state.setdefault("listing_advice", {})[shortlist.lkey(d)] = review


def position_bar(ppm: float, cmp: dict) -> str:
    """This flat's €/m² on a line against the comparables' p25–median–p75 (plain HTML/CSS)."""
    lo, hi = min(ppm, cmp["p25"]), max(ppm, cmp["p75"])
    pad = (hi - lo) * 0.15 or hi * 0.1
    lo, hi = lo - pad, hi + pad

    def x(v: float) -> str:
        return f"{(v - lo) / (hi - lo) * 100:.1f}%"

    band_w = (cmp["p75"] - cmp["p25"]) / (hi - lo) * 100
    return (
        '<div class="hg-pos"><div class="hg-pos-track">'
        f'<div class="hg-pos-band" style="left:{x(cmp["p25"])};width:{band_w:.1f}%"></div>'
        f'<div class="hg-pos-med" style="left:{x(cmp["ppm"])}"></div>'
        f'<div class="hg-pos-dot" style="left:{x(ppm)}"></div></div>'
        '<div class="hg-pos-legend">'
        f'<span><i class="hg-pos-k-band"></i>μεσαίο 50% παρόμοιων: {eur(_r(cmp["p25"], 10))[:-2]}–'
        f'{eur(_r(cmp["p75"], 10))}/τ.μ.</span>'
        f'<span><i class="hg-pos-k-med"></i>διάμεσος {eur(_r(cmp["ppm"], 10))}/τ.μ.</span>'
        f'<span><i class="hg-pos-k-dot"></i>αυτό {eur(_r(ppm, 10))}/τ.μ.</span>'
        "</div></div>"
    )


def _comparison_section(d: dict, cmp: dict | None) -> None:
    st.markdown("#### Σε σύγκριση με παρόμοια σπίτια")
    if not cmp:
        st.caption("Δεν υπάρχουν αρκετά παρόμοια (ίδια περιοχή και ηλικία) για σύγκριση.")
        return
    ppm = d["price_per_m2"]
    c = st.columns(3)
    # ASCII minus so st.metric reads the sign; inverse: cheaper = green, pointing down.
    c[0].metric(
        "Αυτό (ζητούμενη)",
        f"{eur(_r(ppm, 10))}/τ.μ.",
        delta=f"{cmp['pct']:+.0%} vs διάμεσο",
        delta_color="inverse",
    )
    c[1].metric("Διάμεσος παρόμοιων", f"{eur(_r(cmp['ppm'], 10))}/τ.μ.")
    c[2].metric(
        "Μεσαίο 50% παρόμοιων",
        f"{eur(_r(cmp['p25'], 10))}–{eur(_r(cmp['p75'], 10))}/τ.μ.".replace(" €–", "–"),
    )
    st.markdown(position_bar(ppm, cmp), unsafe_allow_html=True)
    st.caption(
        f"Βάση: {cmp['n']} παρόμοια ({cmp['label']}) · αξιοπιστία {confidence(cmp)}. "
        "Ζητούμενες τιμές αγγελιών, όχι τιμές πώλησης.",
        help=CONF_HELP,
    )
    with st.expander(f"Τα {cmp['n']} παρόμοια"):
        _listing_link_table(cmp["rows"])


def _rent_section(d: dict) -> None:
    """Rent basis, gross yield with its formula, and a net-yield calculator."""
    st.markdown("#### Απόδοση ενοικίου")
    gy = gross_yield(d)
    if gy is None:
        st.caption("Δεν υπάρχει εκτίμηση ενοικίου για αυτή την αγγελία (λείπουν τα τ.μ.).")
        return
    price = d["price"]
    rent = d.get("listed_rent") or d.get("est_monthly_rent")
    area = d.get("area_m2")
    if d.get("listed_rent"):
        basis = "Ενοίκιο που αναφέρει η αγγελία (το ακίνητο είναι νοικιασμένο)."
    elif d.get("rent_estimated", True):
        per = f" (~{rent / area:.0f} €/τ.μ. τον μήνα × {area:g} τ.μ.)" if area else ""
        basis = f"Εκτίμηση από το διάμεσο ενοίκιο της περιοχής{per} — όχι πραγματικό ενοίκιο."
    else:
        basis = "Εκτίμηση από αγγελίες ενοικίασης παρόμοιων σπιτιών της περιοχής."
    c = st.columns(2)
    c[0].metric("Ενοίκιο", f"~{eur(_r(rent, 10))}/μήνα")
    c[1].metric("Μικτή απόδοση", pct1(gy), help="12 × ενοίκιο ÷ τιμή, πριν από έξοδα και φόρους.")
    st.caption(
        f"{basis} Μικτή απόδοση = 12 × ενοίκιο ÷ τιμή = 12 × {eur(rent)} ÷ {eur(price)} "
        f"= {pct1(gy)}."
    )

    private = bool(d.get("is_private_seller"))
    acq = acquisition.acquisition_costs(
        price, agent_fee_pct=0.0 if private else acquisition.DEFAULT_AGENT_FEE_PCT
    )
    lid = d["id"]
    with st.container(border=True, key=f"netcalc-{lid}"):
        st.markdown("**Καθαρή απόδοση** — άλλαξε τις παραδοχές")
        r1 = st.columns(3)
        rent_in = r1[0].number_input(
            "Ενοίκιο €/μήνα", 0, 20_000, _r(rent, 10), 10, key=f"nc_rent_{lid}"
        )
        common = r1[1].number_input(
            "Κοινόχρηστα €/μήνα",
            0,
            2_000,
            0,
            5,
            key=f"nc_common_{lid}",
            help="Συνήθως τα πληρώνει ο ενοικιαστής· βάλε ποσό αν τα καλύπτεις εσύ.",
        )
        enfia = r1[2].number_input(
            "ΕΝΦΙΑ €/έτος",
            0,
            20_000,
            _r(4 * (area or 0), 10),
            10,
            key=f"nc_enfia_{lid}",
            help="Πρόχειρα ~4 €/τ.μ. τον χρόνο· το πραγματικό ποσό είναι στο εκκαθαριστικό.",
        )
        r2 = st.columns(3)
        vacant = r2[0].number_input("Μήνες κενό/έτος", 0, 12, 1, 1, key=f"nc_vac_{lid}")
        tax = r2[1].number_input(
            "Φόρος ενοικίου %",
            0,
            60,
            15,
            1,
            key=f"nc_tax_{lid}",
            help="15% έως 12.000 €/έτος, 35% για 12.001–35.000 €, 45% πάνω από 35.000 €.",
        )
        upkeep = r2[2].number_input("Συντήρηση % ενοικίου", 0, 50, 8, 1, key=f"nc_upkeep_{lid}")
        income = rent_in * (12 - vacant)
        net = income * (1 - tax / 100 - upkeep / 100) - common * 12 - enfia
        total = price + acq["total_fees"]
        st.markdown(
            f"Καθαρό ετήσιο ≈ **{eur(_r(net, 100))}** · καθαρή απόδοση ≈ **{pct1(net / total)}** "
            f"στο συνολικό κόστος αγοράς {eur(_r(total, 100))}"
        )
        st.caption(
            "Καθαρό = ενοίκιο × (12 − μήνες κενό) × (1 − φόρος − συντήρηση) − κοινόχρηστα × 12 "
            "− ΕΝΦΙΑ. Καθαρή απόδοση = καθαρό ÷ (τιμή + έξοδα αγοράς). Χωρίς δάνειο και ασφάλιση."
        )
    lines = [
        ("Φόρος μεταβίβασης 3,09%", acq["transfer_tax"]),
        ("Συμβολαιογράφος ~1,5%", acq["notary"]),
        ("Κτηματολόγιο ~0,5%", acq["land_registry"]),
        ("Δικηγόρος ~1%", acq["legal"]),
        ("Μεσίτης ~2,48%" if not private else "Μεσίτης (ιδιώτης: 0)", acq["agent"]),
    ]
    st.markdown(
        f"**Έξοδα αγοράς ≈ {eur(_r(acq['total_fees'], 100))}** "
        f"({pct1(acq['fees_pct_of_price'])} της τιμής): "
        + " · ".join(f"{name} {eur(_r(v, 10))}" for name, v in lines)
    )


def _go_area(area: str) -> None:
    st.session_state["nl_filters"] = SearchFilters(areas=[area])
    st.session_state.pop("show_all", None)
    st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1
    st.session_state["limit"] = PAGE_SIZE
    st.session_state["page"] = NAV_SEARCH


def _area_line(d: dict, listings: list[dict]) -> None:
    """One concise line about the area, with a link to its listings."""
    m = area_name(d)
    if not m:
        return
    vals = [x["price_per_m2"] for x in listings if x.get("price_per_m2") and area_name(x) == m]
    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    if len(vals) >= 5:
        c1.caption(
            f"Περιοχή {m}: διάμεσο {eur(_r(statistics.median(vals), 10))}/τ.μ. ζητούμενης τιμής "
            f"σε {len(vals):,} αγγελίες.".replace(",", ".")
        )
    else:
        c1.caption(f"Περιοχή {m}.")
    c2.button("Αγγελίες της περιοχής", key="area_link", on_click=_go_area, args=(m,))


def page_listing(listings: list[dict]) -> None:
    """Everything a buyer needs about one flat: facts, rent and yield, how it prices against
    like-for-like flats, the same flat at other agents, its price history and time on market."""
    from scout.ui import queries

    _show_flash()
    by_id = {d["id"]: d for d in listings}
    wanted = st.session_state.get("detail_id")
    starred = watch_keys()
    picks = [d for d in listings if shortlist.lkey(d) in starred and d["id"] != wanted]
    if wanted in by_id:
        picks.insert(0, by_id[wanted])
    if not picks:
        st.markdown("## Αγγελία")
        st.info("Άνοιξε μια αγγελία με «Λεπτομέρειες» από την Αναζήτηση ή τα Αγαπημένα.")
        return
    labels = {
        f"{eur(d['price'])} · {d.get('title') or ''} · {d.get('neighborhood') or ''}": d["id"]
        for d in picks
    }
    choice = st.selectbox("Αγγελία", list(labels), key=f"listing_pick_{wanted}")
    d = by_id[labels[choice]]
    intel = market_intel.build(listings)
    adv = buyer_view(d, intel)
    review = st.session_state.get("listing_advice", {}).get(shortlist.lkey(d))
    actions = [(AI_LABEL, _ask_listing, (d, adv, intel))] if has_ai() else []
    result_card(
        d,
        adv,
        "l",
        [*actions, _star_action(d)],
        advice=review.verdicts[0] if review and review.verdicts else None,
    )
    if review is None and st.session_state.get("advice_err") and has_ai():
        st.caption(st.session_state["advice_err"])
    st.caption(SCORE_LEGEND, help=SCORE_HELP)
    if d.get("energy_class"):
        st.markdown(f"Ενεργειακή κλάση: **{html.escape(str(d['energy_class']).strip())}**")

    _rent_section(d)
    _comparison_section(d, adv.get("cmp"))

    if twins := adv.get("twins"):
        st.markdown("#### Το ίδιο σπίτι από άλλους μεσίτες")
        st.caption(
            "Ίδια περιοχή, τ.μ., όροφος και έτος, τιμή έως 10% διαφορά — πιθανότατα το ίδιο "
            "διαμέρισμα. Η χαμηλότερη τιμή είναι το σημείο εκκίνησης της διαπραγμάτευσης."
        )
        _listing_link_table(twins)

    st.markdown("#### Ιστορικό τιμής και χρόνος στην αγορά")
    history = queries.load_price_history(d["id"])
    if len({p for _, p in history}) > 1:
        st.markdown("  \n".join(f"{when:%d/%m/%Y}: **{eur(price)}**" for when, price in history))
    elif history:
        st.caption(f"Τιμή αμετάβλητη από {history[0][0]:%d/%m/%Y} που την πρωτοείδαμε.")
    if d.get("days_on_market"):
        since = d.get("listed_date") or d.get("first_seen")
        src = "ημερομηνία αγγελίας" if d.get("listed_date") else "πρώτη φορά που την είδαμε"
        when = f" (από {since:%d/%m/%Y}, {src})" if since else ""
        st.caption(f"Στην αγορά περίπου {d['days_on_market']} μέρες{when}.")
    _area_line(d, listings)
