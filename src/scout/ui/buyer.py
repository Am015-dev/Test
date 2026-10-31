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
from datetime import date, datetime

import streamlit as st

from scout import acquisition, advisor, market_intel, nl_search, picks, shortlist
from scout.market_intel import municipality
from scout.nl_search import SearchFilters

PAGE_SIZE = 12
MAX_ADVICE = 25  # AI second opinions per browser session — bounds API cost
ADVICE_TONE = {"Αξίζει": "good", "Με επιφύλαξη": "warn", "Απόφυγε": "bad"}
MAX_SEARCHES = 30  # AI-parsed searches per browser session — bounds API cost
NAV_DETAIL = "Αγγελία"  # label of the listing-detail page (cards link to it)
NAV_SEARCH = "Αναζήτηση"  # label of the search page (the listing page links back to it)
AI_LABEL = "Δεύτερη γνώμη από τεχνητή νοημοσύνη"

CONF_HELP = (
    "Πόσο σίγουρη είναι η σύγκριση. Υψηλή: 12 παρόμοια και πάνω, με τιμές κοντά μεταξύ τους "
    "(οι μισές μεσαίες απέχουν έως 25 % από τη συνηθισμένη). Χαμηλή: λιγότερα από 8 παρόμοια ή "
    "τιμές που απλώνονται πάνω από 45 %. Μέτρια σε όλες τις άλλες περιπτώσεις. Παρόμοια λέμε τα "
    "σπίτια της ίδιας περιοχής και ηλικίας και, όπου γίνεται, του ίδιου μεγέθους και ορόφου."
)
UNFINISHED_NOTE = "Υπό κατασκευή"

EXAMPLES = {
    "Δυάρι στον Χολαργό": "δυάρι στον Χολαργό έως 180Χ με ανελκυστήρα",
    "Έχω 200.000 €": "έχω 200 χιλιάδες να επενδύσω στον Χολαργό",
}


def gross_yield(d: dict) -> float | None:
    """12 × monthly rent ÷ price — the same number on the card, the sort and the listing."""
    rent = d.get("listed_rent") or d.get("est_monthly_rent")
    return 12 * rent / d["price"] if rent and d.get("price") else None


def _unfinished(d: dict) -> bool:
    return bool(d.get("is_unfinished"))


def _vs_comps(pct, adv, d) -> tuple:
    """Cheapest per m² against like-for-like listings first. Last: under construction, far
    too cheap to believe, and listings without enough comparables to tell."""
    cmp = adv.get("cmp")
    return (
        _unfinished(d),
        bool(adv.get("too_cheap")),
        cmp is None,
        cmp["pct"] if cmp else 0,
        -pct,
        d["price"],
    )


DEFAULT_SORT = "Τιμή σε σχέση με παρόμοια"
SORTS = {
    DEFAULT_SORT: _vs_comps,
    "Υψηλότερη απόδοση": lambda pct, adv, d: (
        _unfinished(d),
        bool(adv.get("too_cheap")),
        -(gross_yield(d) or 0),
        d["price"],
    ),
    "Χαμηλότερη τιμή": lambda pct, adv, d: (d["price"], d.get("price_per_m2") or 1e9),
    "Χαμηλότερο €/τ.μ.": lambda pct, adv, d: (d.get("price_per_m2") or 1e9, d["price"]),
    "Νεότερο κτίριο": lambda pct, adv, d: (-(d.get("year_built") or 0), d["price"]),
}
SORT_HELP = {
    DEFAULT_SORT: "Πρώτα όσα ζητούν λιγότερα ανά τ.μ. από τα άλλα σπίτια της γειτονιάς (ίδια "
    "περιοχή, ηλικία, μέγεθος). Στο τέλος όσα είναι υπό κατασκευή, όσα είναι πάνω από 35 % "
    "φθηνότερα από τα παρόμοια (θέλουν έλεγχο) και όσα δεν έχουν αρκετά παρόμοια.",
    "Υψηλότερη απόδοση": "Μικτή απόδοση = 12 × ενοίκιο (εκτίμηση) ÷ τιμή. Στο τέλος όσα είναι "
    "υπό κατασκευή ή ύποπτα φθηνά.",
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
    """0.0463 -> '4,6 %' (Greek decimal comma)."""
    return f"{v * 100:.1f}".replace(".", ",") + " %"


def pct_int(v: float) -> str:
    """0.331 -> '33 %'."""
    return f"{v * 100:.0f} %"


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
    return f"Δεδομένα XE.gr έως {newest:%d/%m}{late} · {n} {_noun(len(listings))}"


# ---- session state: starred listings -------------------------------------------------------

SESSION_ONLY = "Τα αγαπημένα κρατιούνται μόνο σε αυτή τη συνεδρία."


def watch_keys() -> set[str]:
    """Starred listing keys of the signed-in user (or the anonymous profile), loaded once."""
    if "watch" not in st.session_state:
        from scout.ui import account  # lazy: pages and tests may swap the account module

        store = account.storage()
        st.session_state["watch"] = set(store.get("watch", []))
        st.session_state["watch_persisted"] = store.persistent
    return st.session_state["watch"]


def toggle_watch(key: str) -> None:
    from scout.ui import account

    keys = watch_keys()
    on = key not in keys
    keys.add(key) if on else keys.discard(key)
    if st.session_state.get("watch_persisted") and not account.storage().set("watch", sorted(keys)):
        _flash("error", "Δεν αποθηκεύτηκε. Το κρατάμε μέχρι να κλείσεις τη σελίδα.")


def open_detail(listing_id: int) -> None:
    if st.session_state.get("page") != NAV_DETAIL:  # where «Πίσω» returns to
        st.session_state["detail_from"] = st.session_state.get("page")
    st.session_state["page"] = NAV_DETAIL
    st.session_state["detail_id"] = listing_id


def _back_from_detail() -> None:
    from scout.ui import guide  # lazy: guide imports this module

    st.session_state["page"] = st.session_state.pop("detail_from", None) or guide.TITLE


def _go_home() -> None:
    from scout.ui import guide

    st.session_state["page"] = guide.TITLE


def _reason(e: Exception) -> str:
    """A short, plain reason — never a URL, a service name or a traceback."""
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status in (401, 403):
        return "δεν επιτρέπεται η πρόσβαση στην αποθήκευση"
    if status == 404:
        return "δεν βρέθηκε το αρχείο αποθήκευσης"
    if status is not None:
        return "η αποθήκευση δεν έγινε, δοκίμασε ξανά σε λίγο"
    if isinstance(e, OSError | TimeoutError):
        return "δεν υπάρχει σύνδεση, δοκίμασε ξανά σε λίγο"
    return "κάτι πήγε στραβά, δοκίμασε ξανά"


def _flash(kind: str, msg: str) -> None:
    st.session_state.setdefault("flash", []).append((kind, msg))


def _show_flash() -> None:
    """Confirmations in green; a storage problem as a plain one-line note, never red."""
    for kind, msg in st.session_state.pop("flash", []):
        (st.caption if kind == "error" else st.success)(msg)


# ---- the listing card ----------------------------------------------------------------------
# One card for search, favourites and saved searches. Every line is a fact with a named source;
# the basis of every number is one tap away ("Από πού βγαίνουν"). No score number: its parts
# are arrows, not figures, so it could not be checked from the card.

CARD_CSS = """<style>
.hg-card { line-height: 1.4; font-size: .9rem; color: var(--hg-ink-soft, #1E293B); }
.hg-card > div + div { margin-top: 4px; }
.hg-l1 { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 8px; }
.hg-l1 .hg-price { font-size: 1.35rem; font-weight: 750; color: var(--hg-ink, #0F172A); }
.hg-sep { color: var(--hg-faint, #94A3B8); }
.hg-st { display: inline-block; font-size: .8rem; font-weight: 600; border-radius: 6px;
    padding: 2px 8px; }
.hg-st-bad { background: #FEE2E2; color: #991B1B; }
.hg-st-ok { background: #DCFCE7; color: #166534; }
.hg-st-unk { background: #FFEDD5; color: #9A3412; }
.hg-st-neu { background: #E2E8F0; color: #334155; }
.hg-nw { white-space: nowrap; }
.hg-hidden { font-size: .8rem; line-height: 1.35; }
.hg-st-photo { background: #FEF3C7; color: #92400E; }
.hg-more { color: var(--hg-muted, #64748B); font-size: .82rem; }
.hg-card details { margin-top: 6px; font-size: .82rem; color: var(--hg-muted, #64748B); }
.hg-card summary { cursor: pointer; color: var(--hg-accent, #0F766E); font-weight: 600; }
.hg-card details p { margin: 4px 0 0; }
.hg-desc { white-space: pre-line; font-size: .9rem; }
.hg-rank { font-size: 1rem; font-weight: 700; color: var(--hg-muted, #64748B); }
</style>"""


def _css() -> None:
    st.markdown(CARD_CSS, unsafe_allow_html=True)


def _greek_numbers(s: str) -> str:
    """'180,000' / '170000' → '180.000' (Greek thousands separator) in free text."""
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", ".", s)
    return re.sub(r"\b\d{5,}\b", lambda m: f"{int(m.group()):,}".replace(",", "."), s)


def _floor(f: float) -> str:
    if f < 0:
        return "Υπόγειο"
    return "Ισόγειο" if f == 0 else f"{f:g}ος όροφος"


def _rent(d: dict) -> float | None:
    return d.get("listed_rent") or d.get("est_monthly_rent")


def rent_text(d: dict) -> str:
    """'Ενοίκιο (εκτίμηση) ~690 €/μήνα · Μικτή απόδοση 4,6 %' — or why there is no figure."""
    gy = gross_yield(d)
    if gy is None:
        return "Ενοίκιο: χωρίς εκτίμηση (λείπουν τα τ.μ.)"
    rent = eur(_r(_rent(d), 10))
    head = "Ενοίκιο (από την αγγελία)" if d.get("listed_rent") else "Ενοίκιο (εκτίμηση)"
    return (
        f'<span class="hg-nw">{head} ~{rent}/μήνα</span> · '
        f'<span class="hg-nw">Μικτή απόδοση {pct1(gy)}</span>'
    )


def rent_basis(d: dict) -> str:
    """Where the rent figure comes from, in one sentence."""
    rent, area = _rent(d), d.get("area_m2")
    if not rent:
        return "Η αγγελία δεν γράφει τ.μ., άρα δεν βγάζουμε ενοίκιο."
    if d.get("listed_rent"):
        return "Το ενοίκιο το γράφει η αγγελία: το σπίτι είναι ήδη νοικιασμένο."
    per = (
        f": ~{f'{rent / area:.1f}'.replace('.', ',')} €/τ.μ. τον μήνα × {_m2(area)} τ.μ."
        if area
        else ""
    )
    if d.get("rent_estimated", True):
        return (
            f"Τόσο ζητούν συνήθως για ενοίκιο τα διπλανά στο XE.gr{per}. Είναι αγγελίες, όχι "
            "υπογεγραμμένα συμβόλαια."
        )
    return f"Τόσο ζητούν για ενοίκιο σπίτια σαν αυτό στη γειτονιά, στο XE.gr{per}."


def comps_text(adv: dict) -> str:
    """'Παρόμοια (12): 14 % κάτω' / '… πάνω' / 'Λίγα παρόμοια'."""
    cmp = adv.get("cmp")
    if not cmp:
        return "Λίγα παρόμοια για σύγκριση"
    pct = cmp["pct"]
    if abs(pct) < 0.005:
        where = "όσο και τα άλλα"
    else:
        where = f"{pct_int(abs(pct))} {'κάτω' if pct < 0 else 'πάνω'}"
    out = f"Παρόμοια ({cmp['n']}): {where}"
    if -pct > nl_search.TOO_CHEAP:
        out += ". Πολύ φθηνό, έλεγξε γιατί"
    return out


def comps_basis(d: dict, adv: dict) -> str:
    cmp = adv.get("cmp")
    if not cmp:
        return (
            f"Παρόμοια: βρήκαμε λιγότερα από {market_intel.MIN_COMPS} σπίτια στην ίδια περιοχή, "
            "με ίδια ηλικία και μέγεθος, άρα δεν συγκρίνουμε."
        )
    return (
        f"Παρόμοια: {cmp['n']} σπίτια ({cmp['label']}). Ζητούν συνήθως "
        f"{eur(_r(cmp['ppm'], 10))}/τ.μ., αυτό ζητά {eur(_r(d['price_per_m2'], 10))}/τ.μ. "
        "Είναι τιμές αγγελιών, όχι τιμές πώλησης."
    )


def status(d: dict) -> tuple[str, str]:
    """(tone, text): under construction / page read / not read yet — the find page's words."""
    if _unfinished(d):
        return "bad", UNFINISHED_NOTE
    return ("ok" if d.get("page_checked") else "unk"), picks.status_line(d)


def status_basis(d: dict) -> str:
    if _unfinished(d):
        return "Υπό κατασκευή: το γράφει η ίδια η αγγελία στο XE.gr, στον τίτλο ή στην περιγραφή."
    if d.get("page_checked"):
        when = d.get("page_checked_at")
        on = f" στις {when:%d/%m}" if hasattr(when, "strftime") else ""
        return (
            f"Ελέγχθηκε η περιγραφή: διαβάσαμε την αγγελία στο XE.gr{on} και δεν γράφει ότι "
            "χτίζεται ακόμα. Τις φωτογραφίες δεν τις κρίνει αυτός ο έλεγχος."
        )
    return (
        "Δεν έχει ελεγχθεί ακόμα: δεν έχουμε διαβάσει ακόμα την αγγελία, οπότε μπορεί να είναι "
        "υπό κατασκευή. Διάβασε την περιγραφή στο XE.gr."
    )


DOM_BASIS = {"listed": "από την ημερομηνία αγγελίας", "seen": "από τότε που τη βλέπουμε"}


def dom_text(d: dict) -> str:
    """'109 μέρες στην αγορά (από τότε που τη βλέπουμε) · η αγγελία ανανεώθηκε 28/10' — the
    basis when we know it, and the re-post date when the portal's date is newer than our
    first sighting (a refreshed ad is not a new flat on the market)."""
    basis = DOM_BASIS.get(d.get("dom_basis") or "")
    text = f"{_days(d['days_on_market'])} στην αγορά" + (f" ({basis})" if basis else "")
    if d.get("relisted_on"):
        text += f" · η αγγελία ανανεώθηκε {d['relisted_on']:%d/%m}"
    return text


def _year_text(d: dict) -> str:
    built, reno = d.get("year_built"), d.get("renovated_year")
    if not built:
        return "έτος: δεν δηλώνεται" + (f" (ανακαίνιση {reno})" if reno else "")
    return f"κτίριο {built}" + (f", ανακαίνιση {reno}" if reno else "")


def _m2(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _join(parts: list[str]) -> str:
    return '<span class="hg-sep" aria-hidden="true"> · </span>'.join(parts)


def _is_rent(d: dict) -> bool:
    return d.get("listing_type") == "rent"


def rent_chips(d: dict) -> list[str]:
    """A rental's line 3: «Επιπλωμένο» / «Χωρίς έπιπλα» and «Διαθέσιμο από ΗΗ/ΜΜ», when the
    ad says so."""
    out = {True: ["Επιπλωμένο"], False: ["Χωρίς έπιπλα"]}.get(d.get("furnished"), [])
    if isinstance(when := d.get("available_from"), (date, datetime)):
        out.append(f"Διαθέσιμο από {when:%d/%m}")
    return out


def short_status(d: dict) -> tuple[str, str]:
    """(tone, glossary term) for the compact card's badge; the full sentence is one tap away."""
    if _unfinished(d):
        return "bad", UNFINISHED_NOTE
    if d.get("page_checked"):
        return "ok", "Ελέγχθηκε η περιγραφή"
    return "unk", "Δεν έχει ελεγχθεί ακόμα"


def _rent_line(d: dict) -> str:
    """Line 4: rent + gross yield, or (a rental) the rent and its €/τ.μ."""
    if not _is_rent(d):
        return rent_text(d)
    rent, area = d.get("price"), d.get("area_m2")
    per = d.get("rent_per_m2") or (rent / area if rent and area else None)
    out = f'<span class="hg-nw">Ενοίκιο {eur(rent)}/μήνα</span>'
    if per:
        out += f' · <span class="hg-nw">{f"{per:.1f}".replace(".", ",")} €/τ.μ.</span>'
    return out


def _extras(d: dict, adv: dict) -> list[str]:
    """Facts beyond the five lines, as plain text (escaped where they are rendered)."""
    extras = []
    first = d.get("first_price")
    if d.get("price_dropped") and first and d.get("price") and first > d["price"]:
        extras.append(f"Μείωση από {eur(first)} (−{pct_int(1 - d['price'] / first)})")
    elif d.get("price_dropped"):
        extras.append("Μειώθηκε η τιμή")
    if d.get("is_private_seller"):
        extras.append("Ιδιώτης")
    if d.get("days_on_market"):
        extras.append(dom_text(d))
    if twins := adv.get("twins"):
        low = twins[0]["price"]
        cheaper = f", η φθηνότερη {eur(low)}" if d.get("price") and low < d["price"] else ""
        extras.append(
            f"Ίδιο σπίτι σε {len(twins)} ακόμα {'αγγελία' if len(twins) == 1 else 'αγγελίες'}"
            f"{cheaper}"
        )
    if d.get("energy_class"):
        extras.append(f"Ενεργειακή κλάση {str(d['energy_class']).strip()}")
    return extras


def _basis_lines(d: dict, adv: dict) -> list[str]:
    if _is_rent(d):  # no rental page is read, so no page-check sentence
        lines = ["Ενοίκιο: αυτό που ζητά η αγγελία, όχι συμβόλαιο."]
    else:
        lines = [status_basis(d), rent_basis(d)]
        if (gy := gross_yield(d)) is not None:
            lines.append(
                f"Μικτή απόδοση = 12 × ενοίκιο ÷ τιμή = 12 × {eur(_r(_rent(d), 10))} ÷ "
                f"{eur(d['price'])} = {pct1(gy)}, πριν από έξοδα και φόρους."
            )
    lines.append(comps_basis(d, adv))
    return lines


def card_html(
    d: dict,
    adv: dict,
    basis: bool = True,
    *,
    compact: bool = False,
    lead: str = "",
    more: list[str] | None = None,
) -> str:
    """The card body: five fixed lines, then (``basis``) the one-tap «Από πού βγαίνουν».

    ``compact`` (guide result, search, compare): exactly those five lines are visible —
    price · τ.μ. · €/τ.μ.; floor · year · area · station; status badge; rent + gross yield;
    one comparison line — and every other fact (``more``, days on market, price drop, seller,
    twins, energy class, the full status sentence) moves into the expander. The full card
    (listing page) shows the extras as a sixth line. ``lead`` prefixes line 1 (the rank)."""
    e = html.escape
    rent_row = _is_rent(d)
    price = eur(d.get("price")) + ("/μήνα" if rent_row else "")
    l1 = [f'<span class="hg-price">{price}</span>']
    if lead:
        l1[0] = f'<span class="hg-rank">{e(lead)}</span> ' + l1[0]
    if d.get("area_m2"):
        l1.append(f"{_m2(d['area_m2'])} τ.μ.")
    if d.get("price_per_m2") and not rent_row:
        l1.append(f"{eur(d['price_per_m2'])}/τ.μ.")
    floor = d.get("floor")
    l2 = [_floor(floor) if floor is not None else "όροφος: δεν δηλώνεται", _year_text(d)]
    if d.get("neighborhood"):
        l2.append(e(d["neighborhood"]))
    if stn := picks.station_text(d):
        l2.append(f"Σταθμός {e(stn)}")
    if rent_row:  # no rental page is read: line 3 = what a renter needs, or no line at all
        tone, text = "neu", ""
        l3 = " ".join(f'<span class="hg-st hg-st-neu">{e(x)}</span>' for x in rent_chips(d))
    else:
        tone, text = short_status(d) if compact else status(d)
        text, _, photos = text.partition(" · Φωτογραφίες:")  # the photo clause: its own tone
        l3 = f'<span class="hg-st hg-st-{tone}">{text}</span>'
        if photos:
            l3 += (
                '<span class="hg-sep" aria-hidden="true"> · </span>'
                f'<span class="hg-st hg-st-neu">Φωτογραφίες:{photos}</span>'
            )
    if d.get("few_photos"):
        l3 = (l3 + f' <span class="hg-st hg-st-photo">{picks.FEW_PHOTOS}</span>').strip()
    extras = _extras(d, adv)
    mark = ' data-compact="1"' if compact else ""
    rank = f' data-rank="{e(lead.rstrip("."))}"' if lead else ""  # theme: the first pick leads
    out = (
        f'<div class="hg-card"{mark}{rank} data-lid="{d.get("id")}">'
        f'<div class="hg-l1">{_join(l1)}</div>'
        f'<div class="hg-l2">{_join(l2)}</div>'
        + (f'<div class="hg-l3">{l3}</div>' if l3 else "")
        + f'<div class="hg-l4">{_rent_line(d)}</div>'
        f'<div class="hg-l5">{e(comps_text(adv))}</div>'
    )
    hidden: list[str] = []
    if compact:
        full = "" if rent_row else status(d)[1]
        hidden = [*(more or []), *extras] + ([full] if full and full != text else [])
    elif extras:
        out += f'<div class="hg-more">{_join([e(x) for x in extras])}</div>'
    if basis or hidden:
        lines = hidden + (_basis_lines(d, adv) if basis else [])
        out += (
            "<details><summary>Από πού βγαίνουν</summary>"
            + "".join(f"<p>{e(x)}</p>" for x in lines)
            + "</details>"
        )
    return out + "</div>"


def result_card(
    d: dict, adv: dict, k: str, actions: list, advice=None, *, compact: bool = False
) -> None:
    """One listing. ``actions`` = [(label, callback, args[, type])], each rendered as a button.
    The full card adds «Άνοιγμα στο …» first; the compact card has only ``actions`` (the
    portal link is on the listing page, one tap away through «Λεπτομέρειες»)."""
    key = shortlist.lkey(d)
    uid = f"{k}-{d['id']}"
    with st.container(border=True, key=f"card-{uid}"):
        st.markdown(card_html(d, adv, compact=compact), unsafe_allow_html=True)
        if advice is not None:
            st.markdown(_advice_html(advice), unsafe_allow_html=True)
        with st.container(key=f"act-{uid}"):
            first = 0 if compact else 1
            cols = st.columns(len(actions) + first, gap="small")
            if not compact:
                cols[0].link_button(f"Άνοιγμα στο {source_label(d)}", d["url"], width="stretch")
            for i, (label, cb, args, *kind) in enumerate(actions, start=1):
                cols[i - 1 + first].button(
                    label,
                    key=f"{k}-{i}-{key}",
                    on_click=cb,
                    args=args,
                    type=kind[0] if kind else "secondary",
                    width="stretch",
                )


def _advice_html(advice) -> str:
    return (
        f'<div class="hg-advice hg-advice-{ADVICE_TONE[advice.label]}">'
        f"<b>{AI_LABEL}: {html.escape(advice.label)}</b> — "
        f"{html.escape(advice.reason)}</div>"
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
        "Αφαίρεση από αγαπημένα" if on else "Αγαπημένο",
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
    for k in ("nl_filters", "nl_text", "nl_error", "q_text"):
        st.session_state.pop(k, None)
    st.session_state["limit"] = PAGE_SIZE
    st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1


def _show_all(ver: int) -> None:
    """Drop the floor and building-year filters, keeping every other filter as it is."""
    st.session_state[f"fe_floor_{ver}"] = 0
    st.session_state[f"fe_year_{ver}"] = 0


def _more() -> None:
    st.session_state["limit"] = st.session_state.get("limit", PAGE_SIZE) + PAGE_SIZE


DEFAULT_FLOOR = 1  # ground floors and basements are not what this buyer wants
DEFAULT_AGE = 40  # a 50-60-year-old block is not shown unless asked for
DEFAULT_KINDS = ["apartment"]  # a buy-to-let flat; houses only when asked for


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
    'Αθήνα'), anything else by the usual location rule of ``nl_search``."""
    if not areas:
        return True
    name, m = area_name(d), municipality(d)
    if name != m:
        return any(nl_search.area_matches(a, name) or nl_search.area_matches(a, m) for a in areas)
    return nl_search.why_hidden(d, SearchFilters(areas=areas, include_unfinished=True)) != "area"


def _strategy_excluded(d: dict) -> bool:
    """Excluded by the thesis for a reason the search filters do not cover. The ground/low
    floor exclusion is left to the floor filter, so «Όροφος: Οποιοσδήποτε» really shows them."""
    if not d.get("excluded"):
        return False
    low = d.get("floor") is not None and d["floor"] < 1
    return not (low and str(d.get("exclusion_reason") or "ground").startswith("ground"))


def hide_reason(d: dict, f: SearchFilters) -> str | None:
    """Why the search page hides ``d`` (a ``HIDE_LABEL`` key), or None when it is shown.
    A listing failing several filters counts under the first, in ``HIDE_LABEL`` order."""
    if f.areas and not _area_hit(d, f.areas):
        return "area"
    if _strategy_excluded(d):
        reason = str(d.get("exclusion_reason") or "")
        return "not_home" if "dwelling" in reason else "excluded"
    if d.get("is_suspect"):
        return "suspect"
    return nl_search.why_hidden(d, f.model_copy(update={"areas": []}))


def match(d: dict, f: SearchFilters):
    """``nl_search.match`` with the search page's own rules (``hide_reason``)."""
    if hide_reason(d, f) is not None:
        return None
    return nl_search.match(d, f.model_copy(update={"areas": []}))


def hide_labels(f: SearchFilters) -> dict[str, str]:
    """Reason code → how the "Κρύβονται" line names it, in counting order."""
    floor = f.floor_min or 0
    return {
        "area": "εκτός περιοχής",
        "not_home": "όχι κατοικία",
        "excluded": "εκτός κριτηρίων επένδυσης",
        "suspect": "με στοιχεία που δεν στέκουν",
        "price": "εκτός τιμής",
        "size": "εκτός τ.μ.",
        "bedrooms": "άλλος αριθμός υπνοδωματίων",
        "kind": (
            "μεζονέτες/μονοκατοικίες"
            if set(f.kinds) == set(DEFAULT_KINDS)
            else "άλλος τύπος ακινήτου"
        ),
        "private": "από μεσίτη",
        "unfinished": "υπό κατασκευή",
        "floor": "ισόγεια/υπόγεια" if floor <= 1 else f"κάτω από {floor:g}ο όροφο",
        "year": f"κτίριο πριν το {f.year_min}",
        "undeclared": "χωρίς όροφο/έτος",
    }


def hidden_counts(pool: list[dict], f: SearchFilters) -> dict[str, int]:
    """How many of ``pool`` each reason hides (zero reasons left out)."""
    counts: dict[str, int] = {}
    for d in pool:
        if (why := hide_reason(d, f)) is not None:
            counts[why] = counts.get(why, 0) + 1
    return {k: counts[k] for k in hide_labels(f) if counts.get(k)}


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


def _num(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _noun(n: int, one: str = "αγγελία", many: str = "αγγελίες") -> str:
    """Singular for exactly one, plural otherwise («1 αγγελία», «0/2 αγγελίες»)."""
    return one if n == 1 else many


def _days(n: int) -> str:
    """'1 μέρα' / '109 μέρες'."""
    return f"{n} {'μέρα' if n == 1 else 'μέρες'}"


def source_label(d: dict) -> str:
    """«XE.gr», «Golden Home», «RE/MAX» — the portal's display name for buttons."""
    try:
        from scout.collectors import SOURCE_LABELS
    except ImportError:  # pragma: no cover
        SOURCE_LABELS = {"xe": "XE.gr"}
    src = d.get("source") or "xe"
    return SOURCE_LABELS.get(src, src.upper())


def _editor_defaults(f: SearchFilters, ver: int, options: list[str]) -> None:
    """Pre-fill every filter widget once per search (``ver``) through session state, so the
    page can read the current filters before drawing them and buttons can set them."""
    year = date.today().year
    picked: list[str] = []  # "Παπάγος"/"Papagos" from the search → the "Παπάγου" option
    for a in f.areas:
        o = next((o for o in options if nl_search.area_matches(a, o)), a)
        if o not in picked:
            picked.append(o)
    cur = next((n for n, v in BEDROOMS.items() if v == (f.bedrooms_min, f.bedrooms_max)), "Όλα")
    defaults = {
        "areas": picked,
        "pmax": int(f.price_max or 0),
        "amin": int(f.area_min or 0),
        # The defaults apply until the buyer changes them (a new search restores them).
        "floor": int(f.floor_min if f.floor_min is not None else DEFAULT_FLOOR),
        "year": int(f.year_min or year - DEFAULT_AGE),
        "undecl": f.include_undeclared,
        "beds": cur,
        "kinds": list(f.kinds or DEFAULT_KINDS),
        "wants": list(f.wants),
        "priv": f.private_only,
        "unf": f.include_unfinished,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(f"fe_{k}_{ver}", v)


def _current(f: SearchFilters, ver: int) -> SearchFilters:
    """The filters as the widgets hold them now."""
    g = st.session_state.get
    bmin, bmax = BEDROOMS[g(f"fe_beds_{ver}", "Όλα")]
    floor, year = g(f"fe_floor_{ver}", 0), g(f"fe_year_{ver}", 0)
    return f.model_copy(
        update={
            "price_max": int(g(f"fe_pmax_{ver}", 0)) or None,
            "area_min": float(g(f"fe_amin_{ver}", 0)) or None,
            "bedrooms_min": bmin,
            "bedrooms_max": bmax,
            "areas": list(g(f"fe_areas_{ver}", [])),
            "floor_min": floor or None,
            "year_min": year or None,
            "kinds": list(g(f"fe_kinds_{ver}", [])),
            "wants": list(g(f"fe_wants_{ver}", [])),
            "private_only": bool(g(f"fe_priv_{ver}", False)),
            "include_unfinished": bool(g(f"fe_unf_{ver}", False)),
            "include_undeclared": bool(g(f"fe_undecl_{ver}", False)),
        }
    )


def _filter_editor(f: SearchFilters, pool: list[dict], stale: int = 0) -> SearchFilters:
    """Every filter in one collapsed panel whose label says what is applied."""
    ver = st.session_state.get("f_ver", 0)
    counts = _municipality_counts(pool)
    options = sorted(counts, key=lambda m: -counts[m])
    st.session_state["area_options"] = options  # for the parser without AI
    _editor_defaults(f, ver, options)
    options += [a for a in st.session_state[f"fe_areas_{ver}"] if a not in counts]
    now = _current(f, ver)
    label = "Φίλτρα · " + _greek_numbers(nl_search.describe(now))
    with st.expander(label, key="filters_box"):
        with st.container(key="filters"):
            st.multiselect(
                "Περιοχή",
                options,
                format_func=lambda m: f"{m} ({counts[m]})" if m in counts else m,
                placeholder="Όλες οι περιοχές",
                key=f"fe_areas_{ver}",
            )
            c1, c2 = st.columns(2)
            c1.number_input(
                "Τιμή έως (€)",
                0,
                5_000_000,
                step=10_000,
                key=f"fe_pmax_{ver}",
                help="0 = χωρίς όριο",
            )
            c2.number_input(
                "Από τ.μ.", 0, 1000, step=5, key=f"fe_amin_{ver}", help="0 = χωρίς όριο"
            )
            c3, c4 = st.columns(2)
            c3.number_input(
                "Από όροφο", 0, 30, step=1, key=f"fe_floor_{ver}", help="0 = χωρίς όριο"
            )
            c4.number_input(
                "Κτίριο από (έτος)",
                0,
                date.today().year,
                step=1,
                key=f"fe_year_{ver}",
                help="Έτος κατασκευής του κτιρίου, όχι της ανακαίνισης. 0 = χωρίς όριο.",
            )
            st.checkbox(
                "Και αγγελίες χωρίς δηλωμένο όροφο/έτος",
                key=f"fe_undecl_{ver}",
                help="Μετρά μόνο όταν έχεις βάλει όροφο ή έτος. Συχνά είναι ισόγεια.",
            )
            c5, c6 = st.columns(2)
            c5.selectbox("Υπνοδωμάτια", list(BEDROOMS), key=f"fe_beds_{ver}")
            c6.multiselect(
                "Τύπος",
                list(nl_search.KIND_LABEL),
                format_func=lambda k: nl_search.KIND_LABEL.get(k, k),
                placeholder="Όλοι οι τύποι",
                key=f"fe_kinds_{ver}",
            )
            st.multiselect(
                "Να έχει",
                list(nl_search.WANT_LABEL),
                format_func=lambda k: nl_search.WANT_LABEL.get(k, k),
                placeholder="π.χ. ανελκυστήρα, πάρκινγκ",
                key=f"fe_wants_{ver}",
                help="Δεν κρύβει αγγελίες: όσες το αναφέρουν στον τίτλο ανεβαίνουν.",
            )
            st.checkbox("Μόνο από ιδιώτη", key=f"fe_priv_{ver}")
            st.checkbox(
                "Και κτίρια υπό κατασκευή",
                key=f"fe_unf_{ver}",
                help="Εμφανίζονται σημειωμένα και στο τέλος: θέλουν επιπλέον κεφάλαιο πριν "
                "νοικιαστούν.",
            )
            if stale:
                st.checkbox(
                    f"Και {_num(stale)} παλαιότερ{'η αγγελία' if stale == 1 else 'ες αγγελίες'} "
                    "(μπορεί να έχουν ήδη πουληθεί)",
                    key="include_stale",
                )
    return _current(f, ver)


def _save_mandate(text: str, f: SearchFilters) -> None:
    try:
        shortlist.save_mandate(text, f)
        _flash(
            "ok",
            "Αποθηκεύτηκε. Τις νέες αγγελίες γι' αυτή την αναζήτηση θα τις βρίσκεις στις "
            "«Αποθηκευμένες αναζητήσεις».",
        )
    except shortlist.StorageNotConfigured:
        _flash("error", "Εδώ δεν μπορούμε να αποθηκεύσουμε αναζητήσεις.")
    except Exception as e:
        _flash("error", f"Δεν αποθηκεύτηκε: {_reason(e)}")


def hidden_line(counts: dict[str, int], f: SearchFilters) -> str:
    """'Κρύβονται 1.234: 800 εκτός περιοχής · 300 ισόγεια/υπόγεια · …' ('' if none)."""
    labels = hide_labels(f)
    total = sum(counts.values())
    if not total:
        return ""
    verb = "Κρύβεται" if total == 1 else "Κρύβονται"
    parts = " · ".join(f"{_num(n)} {labels[k]}" for k, n in counts.items())
    return f"{verb} {_num(total)}: {parts}"


def _apply_area_pick() -> None:
    """Another page sent the buyer here for one area (session key ``area_pick``)."""
    pick = st.session_state.pop("area_pick", None)
    if pick:
        for k in ("nl_text", "nl_error", "q_text"):
            st.session_state.pop(k, None)
        st.session_state["nl_filters"] = SearchFilters(areas=[pick])
        st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1
        st.session_state["limit"] = PAGE_SIZE


def page_search(listings: list[dict]) -> None:
    _css()
    _show_flash()
    _apply_area_pick()
    ai = has_ai()
    base = st.session_state.get("nl_filters")
    asked = base is not None
    with st.container(key="hero"):
        st.markdown("## Διαμέρισμα για επένδυση")
        with st.form("search_form", border=False):
            c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
            text = c1.text_input(
                "Τι ψάχνεις;",
                key="q_text",
                max_chars=nl_search.MAX_CHARS,
                placeholder="π.χ. δυάρι στον Χολαργό έως 180.000 €, από 60 τ.μ., με ανελκυστήρα",
                label_visibility="collapsed",
            )
            submitted = c2.form_submit_button("Αναζήτηση", type="primary", width="stretch")
        if not asked:
            with st.container(key="examples", horizontal=True, gap="small"):
                for i, (label, q) in enumerate(EXAMPLES.items()):
                    st.button(label, key=f"ex{i}", on_click=_example_clicked, args=(q,))
    if submitted:
        if text.strip():
            _run_query(text)
            st.rerun()
        else:
            st.session_state["nl_error"] = "Γράψε πρώτα τι σπίτι ψάχνεις."
    if st.session_state.get("nl_error"):
        st.error(st.session_state["nl_error"])

    if asked:
        st.button("Καθαρισμός αναζήτησης", key="clear_q", on_click=_clear_query)

    stale_ok = st.session_state.get("include_stale", False)
    pool = [d for d in listings if stale_ok or d.get("is_fresh", True)]
    stale = sum(1 for d in listings if not d.get("is_fresh", True))
    f = _filter_editor(base or SearchFilters(), pool, stale)

    intel = market_intel.build(listings)
    hits = [(m, d, buyer_view(d, intel)) for d in pool if (m := match(d, f))]
    counts = hidden_counts(pool, f)
    word = "αγγελία" if len(hits) == 1 else "αγγελίες"
    line = hidden_line(counts, f)
    st.markdown(
        f'<div class="hg-count"><b>{_num(len(hits))}</b> {word}'
        + (f'<br><small class="hg-hidden">{html.escape(line)}</small>' if line else "")
        + "</div>",
        unsafe_allow_html=True,
    )
    back = sum(counts.get(k, 0) for k in ("floor", "year", "undeclared"))
    if back:
        st.button(
            f"Δείξε όλες, χωρίς όροφο/έτος (+{_num(back)})",
            key="show_all_btn",
            on_click=_show_all,
            args=(st.session_state.get("f_ver", 0),),
            width="stretch",
        )
    sort = st.selectbox(
        "Σειρά",
        list(SORTS),
        key="sort",
        help=" ".join(f"{k}: {v}" for k, v in SORT_HELP.items()),
    )
    named = [a for a in f.areas if not a.isascii()] or f.areas  # "Χολαργός" over "Cholargos"
    for a in named if not stale_ok else []:
        if not any(_area_hit(d, [a]) for d in pool):
            seen = [d["last_seen"] for d in listings if d.get("last_seen") and _area_hit(d, [a])]
            when = f" (τελευταία ενημέρωση {max(seen):%d/%m})" if seen else ""
            st.caption(
                f"Για «{a}» δεν έχουμε πρόσφατες αγγελίες{when}. Για τις παλαιότερες, άνοιξε "
                "στα φίλτρα το «Και παλαιότερες αγγελίες»."
            )
    if not hits:
        st.info(
            "Καμία αγγελία δεν ταιριάζει. Άνοιξε λίγο ένα φίλτρο, π.χ. την τιμή, το έτος ή τον όροφο."
        )
        _market_panel(intel, named[:3])
        return
    hits.sort(key=lambda h: SORTS[sort](h[0][0], h[2], h[1]))

    verdicts = _search_advice(hits, f, intel) if ai else {}
    limit = st.session_state.get("limit", PAGE_SIZE)
    for _m, d, adv in hits[:limit]:
        result_card(
            d,
            adv,
            "s",
            [("Λεπτομέρειες", open_detail, (d["id"],)), _star_action(d)],
            advice=verdicts.get(shortlist.lkey(d)),
            compact=True,
        )
    if len(hits) > limit:
        st.button(
            f"Δείξε περισσότερες ({_num(len(hits) - limit)} ακόμα)",
            key="more",
            on_click=_more,
            width="stretch",
        )
    st.button(
        "Αποθήκευση αναζήτησης",
        key="save_mandate",
        on_click=_save_mandate,
        args=(st.session_state.get("nl_text") or nl_search.describe(f), f),
        width="stretch",
    )
    _market_panel(intel, named[:3])
    if st.toggle("Χάρτης αποτελεσμάτων", key="show_map"):
        from scout.ui import components

        rows = [{**d, "score": adv["score"]} for _, d, adv in hits]
        components.results_map(rows, key="search-map", height=380)


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
        st.caption(
            "Το σχόλιο το γράφει γλωσσικό μοντέλο από τα ίδια στοιχεία. Δεν είναι εκτίμηση αξίας."
        )
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
            st.markdown(
                "**Πόσο ζητούν συνήθως ανά τ.μ., ανάλογα με την ηλικία του κτιρίου** (σε παρένθεση οι αγγελίες)"
            )
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
    _css()
    st.markdown("## Αποθηκευμένες αναζητήσεις")
    st.caption(
        "Εδώ βλέπεις τις νέες αγγελίες για κάθε αναζήτηση που αποθήκευσες. Με την «Έγκριση» "
        "η αγγελία μπαίνει στα αγαπημένα."
    )
    _show_flash()
    try:
        mandates = shortlist.list_mandates()
    except shortlist.StorageNotConfigured:
        st.info(
            "Εδώ δεν μπορούμε να αποθηκεύσουμε αναζητήσεις. Η «Αναζήτηση» δουλεύει κανονικά, "
            "απλώς δεν τη θυμόμαστε."
        )
        return
    except Exception as e:
        st.caption(f"Δεν μπορέσαμε να φέρουμε τις αποθηκευμένες αναζητήσεις ({_reason(e)}).")
        return
    if not mandates:
        st.info(
            "Καμία αποθηκευμένη αναζήτηση. Κάνε μια αναζήτηση και πάτα «Αποθήκευση αναζήτησης»."
        )
        return
    intel = market_intel.build(listings)
    for m in mandates:
        found = shortlist.pick(m.filters, listings, m.approved | m.rejected)
        with st.expander(
            f"{m.text}  ·  εγκρίθηκαν {len(m.approved)}  ·  απορρίφθηκαν {len(m.rejected)}",
            expanded=True,
        ):
            st.caption("Αναζήτηση για: " + nl_search.describe(m.filters))
            st.button(
                "Διαγραφή αναζήτησης", key=f"del{m.id}", on_click=_delete_mandate, args=(m.id,)
            )
            if not found:
                st.write("Καμία νέα αγγελία αυτή τη στιγμή. Δες ξανά μετά την επόμενη ενημέρωση.")
            for d, _adv, _reasons in found:
                key = shortlist.lkey(d)
                result_card(
                    d,
                    buyer_view(d, intel),
                    f"m{m.id}",
                    [
                        ("Λεπτομέρειες", open_detail, (d["id"],)),
                        ("Έγκριση", _review, (m.id, key, True)),
                        ("Απόρριψη", _review, (m.id, key, False)),
                    ],
                )


# ---- starred -------------------------------------------------------------------------------


def page_watchlist(listings: list[dict]) -> None:
    _css()
    _show_flash()
    from scout.ui import rent_guide  # lazy: it imports this module

    keys = watch_keys()
    starred = [d for d in listings if shortlist.lkey(d) in keys]
    rented = rent_guide.starred(keys)
    n = len(starred) + len(rented)
    st.markdown(f"## Αγαπημένα ({n})" if n else "## Αγαπημένα")
    if not st.session_state.get("watch_persisted"):
        st.caption(SESSION_ONLY)
    if not n:
        st.info("Δεν έχεις αγαπημένα ακόμα. Πάτα «Αγαπημένο» σε μια αγγελία.")
        st.button("Οδηγός", key="watch_to_guide", on_click=_go_home)
        return
    if starred:
        if rented:
            st.markdown("### Για αγορά")
        intel = market_intel.build(listings)
        views = [(d, buyer_view(d, intel)) for d in starred]
        views.sort(key=lambda v: SORTS[DEFAULT_SORT](100, v[1], v[0]))
        st.caption("Σειρά: " + SORT_HELP[DEFAULT_SORT])
        for d, adv in views:
            result_card(d, adv, "w", [("Λεπτομέρειες", open_detail, (d["id"],)), _star_action(d)])
    if rented:
        st.markdown("### Ενοίκια")
        for p in rented:
            rent_guide.card(None, p, "wrent")


# ---- one listing ---------------------------------------------------------------------------


def _listing_lines(rows: list[dict]) -> None:
    """Other listings as one short line each (a link to the portal) — no wide table."""
    lines = []
    for d in rows:
        parts = [eur(d.get("price"))]
        if d.get("area_m2"):
            parts.append(f"{_m2(d['area_m2'])} τ.μ.")
        if d.get("price_per_m2"):
            parts.append(f"{eur(d['price_per_m2'])}/τ.μ.")
        if d.get("floor") is not None:
            parts.append(_floor(d["floor"]))
        if d.get("year_built"):
            parts.append(str(d["year_built"]))
        text = " · ".join(parts).replace("[", "(").replace("]", ")")
        lines.append(f"- [{text}]({d['url']})" if d.get("url") else f"- {text}")
    st.markdown("\n".join(lines))


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
        f'<span><i class="hg-pos-k-band"></i>οι μισές μεσαίες τιμές των παρόμοιων: {eur(_r(cmp["p25"], 10))[:-2]}–'
        f'{eur(_r(cmp["p75"], 10))}/τ.μ.</span>'
        f'<span><i class="hg-pos-k-med"></i>συνήθως {eur(_r(cmp["ppm"], 10))}/τ.μ.</span>'
        f'<span><i class="hg-pos-k-dot"></i>αυτό {eur(_r(ppm, 10))}/τ.μ.</span>'
        "</div></div>"
    )


def _comparison_section(d: dict, adv: dict) -> None:
    cmp = adv.get("cmp")
    st.markdown("#### " + comps_text(adv))
    if not cmp:
        st.caption(comps_basis(d, adv))
        return
    st.markdown(position_bar(d["price_per_m2"], cmp), unsafe_allow_html=True)
    st.caption(
        f"{comps_basis(d, adv)} Πόσο σίγουρη είναι η σύγκριση: {confidence(cmp)}.",
        help=CONF_HELP,
    )
    with st.expander(f"Δες τα παρόμοια ({cmp['n']})"):
        _listing_lines(cmp["rows"])


def _description_section(d: dict) -> None:
    """«Τι λέει η αγγελία»: the listing's own text when we have read it."""
    st.markdown("#### Τι λέει η αγγελία")
    if cut := picks.excerpt(d.get("description"), 600):
        st.markdown(f'<div class="hg-desc">{html.escape(cut)}</div>', unsafe_allow_html=True)
        st.caption("Αυτά γράφει η ίδια η αγγελία στο XE.gr.")
    elif d.get("page_checked"):
        st.caption(
            "Διαβάσαμε την αγγελία μόνο για να δούμε αν είναι υπό κατασκευή και δεν κρατήσαμε "
            "το κείμενο. Διάβασέ το στο XE.gr."
        )
    else:
        st.caption("Δεν έχουμε διαβάσει ακόμα την αγγελία.")


def _rent_section(d: dict) -> None:
    """Rent basis, gross yield with its formula, and a net-yield calculator."""
    st.markdown("#### Ενοίκιο και απόδοση")
    gy = gross_yield(d)
    if gy is None:
        st.caption(rent_basis(d))
        return
    price = d["price"]
    rent = _rent(d)
    area = d.get("area_m2")
    st.markdown(rent_text(d), unsafe_allow_html=True)
    st.caption(
        f"{rent_basis(d)} Μικτή απόδοση = 12 × ενοίκιο ÷ τιμή = 12 × {eur(_r(rent, 10))} ÷ "
        f"{eur(price)} = {pct1(gy)}."
    )

    private = bool(d.get("is_private_seller"))
    acq = acquisition.acquisition_costs(
        price, agent_fee_pct=0.0 if private else acquisition.DEFAULT_AGENT_FEE_PCT
    )
    lid = d["id"]
    with st.container(border=True, key=f"netcalc-{lid}"):
        st.markdown("**Καθαρή απόδοση** — άλλαξε τις παραδοχές")
        r1 = st.columns(2)
        rent_in = r1[0].number_input(
            "Ενοίκιο (€/μήνα)", 0, 20_000, _r(rent, 10), 10, key=f"nc_rent_{lid}"
        )
        common = r1[1].number_input(
            "Κοινόχρηστα που πληρώνεις εσύ (€/μήνα)",
            0,
            2_000,
            0,
            5,
            key=f"nc_common_{lid}",
            help="Συνήθως τα πληρώνει ο ενοικιαστής.",
        )
        r2 = st.columns(2)
        enfia = r2[0].number_input(
            "ΕΝΦΙΑ (€/έτος)",
            0,
            20_000,
            _r(4 * (area or 0), 10),
            10,
            key=f"nc_enfia_{lid}",
            help="Περίπου 4 €/τ.μ. τον χρόνο. Το ακριβές ποσό το γράφει το εκκαθαριστικό.",
        )
        vacant = r2[1].number_input("Μήνες κενό ανά έτος", 0, 12, 1, 1, key=f"nc_vac_{lid}")
        r3 = st.columns(2)
        tax = r3[0].number_input(
            "Φόρος ενοικίου (%)",
            0,
            60,
            15,
            1,
            key=f"nc_tax_{lid}",
            help="15 % έως 12.000 €/έτος, 35 % για 12.001–35.000 €, 45 % πάνω από 35.000 €.",
        )
        upkeep = r3[1].number_input(
            "Συντήρηση (% του ενοικίου)", 0, 50, 8, 1, key=f"nc_upkeep_{lid}"
        )
        income = rent_in * (12 - vacant)
        net = income * (1 - tax / 100 - upkeep / 100) - common * 12 - enfia
        total = price + acq["total_fees"]
        st.markdown(
            f"Καθαρό ετήσιο ~**{eur(_r(net, 100))}** · Καθαρή απόδοση ~**{pct1(net / total)}** "
            f"στο συνολικό κόστος αγοράς {eur(_r(total, 100))}"
        )
        st.caption(
            "Καθαρό = ενοίκιο × (12 − μήνες κενό) × (1 − φόρος − συντήρηση) − κοινόχρηστα × 12 "
            "− ΕΝΦΙΑ. Καθαρή απόδοση = καθαρό ÷ (τιμή + έξοδα αγοράς). Δεν μετράμε δάνειο ούτε ασφάλιση."
        )
    lines = [
        ("Φόρος μεταβίβασης 3,09 %", acq["transfer_tax"]),
        ("Συμβολαιογράφος ~1,5 %", acq["notary"]),
        ("Κτηματολόγιο ~0,5 %", acq["land_registry"]),
        ("Δικηγόρος ~1 %", acq["legal"]),
        ("Μεσίτης ~2,48 %" if not private else "Μεσίτης (ιδιώτης: 0)", acq["agent"]),
    ]
    st.markdown(
        f"**Έξοδα αγοράς ~{eur(_r(acq['total_fees'], 100))}** "
        f"({pct1(acq['fees_pct_of_price'])} της τιμής): "
        + " · ".join(f"{name} {eur(_r(v, 10))}" for name, v in lines)
    )


def _go_area(area: str) -> None:
    st.session_state["nl_filters"] = SearchFilters(areas=[area])
    st.session_state["f_ver"] = st.session_state.get("f_ver", 0) + 1
    st.session_state["limit"] = PAGE_SIZE
    st.session_state["page"] = NAV_SEARCH


def _checks_section(d: dict, intel, listings: list[dict]) -> None:
    """The six checks of a buy-to-let investor for this flat (area_insights.investor_checks):
    each with its number, its basis and a verdict word; «άγνωστο» where the data is missing."""
    from scout import area_insights as ai
    from scout.ui import areas

    st.markdown("#### Έξι έλεγχοι επενδυτή")
    try:
        ranked = areas._ranked(listings, areas._stamp(listings), ai.DEFAULT_BUDGET)
    except Exception:  # the checks still render, with the area parts unknown
        ranked = []
    name = ai.area_name(d.get("neighborhood"))
    insight = next((x for x in ranked if x.area == name), None)
    areas.render_checks(ai.investor_checks(d, intel, insight))
    st.caption(
        "Τα όρια για «καλό», «μέτριο» και «προσοχή» είναι στο «Πώς βαθμολογούμε», στη σελίδα "
        "«Πού να αγοράσω». «Άγνωστο» σημαίνει ότι δεν το ξέρουμε ακόμα."
    )


def _area_line(d: dict, listings: list[dict]) -> None:
    """One concise line about the area, with a link to its listings."""
    m = area_name(d)
    if not m:
        return
    vals = [x["price_per_m2"] for x in listings if x.get("price_per_m2") and area_name(x) == m]
    if len(vals) >= 5:
        st.caption(
            f"Στην περιοχή {m} ζητούν συνήθως {eur(_r(statistics.median(vals), 10))}/τ.μ. "
            f"({_num(len(vals))} αγγελίες στο XE.gr)."
        )
    st.button(f"Αγγελίες στην περιοχή {m}", key="area_link", on_click=_go_area, args=(m,))


def page_listing(listings: list[dict]) -> None:
    """One flat, top to bottom on a phone: facts and status, what the listing says, rent and
    yield, how it prices against like-for-like flats, price history, then the actions."""
    from scout.ui import queries

    _css()
    _show_flash()
    by_id = {d["id"]: d for d in listings}
    wanted = st.session_state.get("detail_id")
    starred = watch_keys()
    options = [d for d in listings if shortlist.lkey(d) in starred and d["id"] != wanted]
    if wanted in by_id:
        options.insert(0, by_id[wanted])
    st.markdown(f"## {NAV_DETAIL}")
    st.button("Πίσω", key="listing-back", on_click=_back_from_detail)
    if not options:
        st.info("Άνοιξε μια αγγελία με «Λεπτομέρειες» από την Αναζήτηση ή τα Αγαπημένα.")
        return
    labels = {
        f"{eur(d['price'])} · {_m2(d['area_m2']) if d.get('area_m2') else '—'} τ.μ. · "
        f"{d.get('neighborhood') or ''}": d["id"]
        for d in options
    }
    choice = st.selectbox(  # the page title above already says «Αγγελία»
        "Αγγελία", list(labels), key=f"listing_pick_{wanted}", label_visibility="collapsed"
    )
    d = by_id[labels[choice]]
    intel = market_intel.build(listings)
    adv = buyer_view(d, intel)
    with st.container(border=True, key=f"card-l-{d['id']}"):
        st.markdown(card_html(d, adv, basis=False), unsafe_allow_html=True)
        st.caption(status_basis(d))

    _description_section(d)
    _rent_section(d)
    _comparison_section(d, adv)
    _checks_section(d, intel, listings)

    if twins := adv.get("twins"):
        st.markdown(
            f"#### Το ίδιο σπίτι σε {len(twins)} ακόμα "
            f"{'αγγελία' if len(twins) == 1 else 'αγγελίες'}"
        )
        st.caption(
            "Ίδια περιοχή, τ.μ., όροφος και έτος, με τιμή που διαφέρει έως 10 %. Μάλλον είναι "
            "το ίδιο διαμέρισμα από άλλο μεσίτη. Ξεκίνα από τη χαμηλότερη τιμή."
        )
        _listing_lines(twins)

    st.markdown("#### Ιστορικό τιμής")
    history = queries.load_price_history(d["id"])
    if len({p for _, p in history}) > 1:
        st.markdown("  \n".join(f"{when:%d/%m/%Y}: **{eur(price)}**" for when, price in history))
    elif history:
        st.caption(
            f"Η τιμή δεν έχει αλλάξει από τις {history[0][0]:%d/%m/%Y}, που την πρωτοείδαμε στο XE.gr."
        )
    _area_line(d, listings)

    review = st.session_state.get("listing_advice", {}).get(shortlist.lkey(d))
    actions = [(AI_LABEL, _ask_listing, (d, adv, intel))] if has_ai() else []
    with st.container(key=f"act-l-{d['id']}"):
        cols = st.columns(len(actions) + 2, gap="small")
        cols[0].link_button(f"Άνοιγμα στο {source_label(d)}", d["url"], width="stretch")
        for i, (label, cb, args, *kind) in enumerate([_star_action(d), *actions], start=1):
            cols[i].button(
                label,
                key=f"l-{i}-{shortlist.lkey(d)}",
                on_click=cb,
                args=args,
                type=kind[0] if kind else "secondary",
                width="stretch",
            )
    if review is not None and review.verdicts:
        st.markdown(_advice_html(review.verdicts[0]), unsafe_allow_html=True)
        st.caption(
            "Το σχόλιο το γράφει γλωσσικό μοντέλο από τα ίδια στοιχεία. Δεν είναι εκτίμηση αξίας."
        )
    elif st.session_state.get("advice_err") and has_ai():
        st.caption(st.session_state["advice_err"])
