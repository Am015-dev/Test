"""«Πού να αγοράσω» — which NE-Athens area suits a flat bought to rent out, and why.

A plain report in the style of Idealista's neighbourhood price reports / PropertyData's
yield tables: every number carries its n, prices are labelled as ASKING prices, the
formulas and weights are on the page, and each area gets an honest confidence label. The
numbers come from ``area_insights.rank_areas`` (pure, tested); this module only formats
and lays them out.

Hand-off to search: «Δες τις αγγελίες» sets ``st.session_state["page"]`` to the search
page and ``st.session_state[AREA_KEY]`` to the area name exactly as shown here (an
``area_insights.area_name`` value, e.g. "Χαλάνδρι", "Αμπελόκηποι").
"""

from __future__ import annotations

import math
import statistics

import pandas as pd
import streamlit as st
from sqlalchemy import select

from .. import area_insights as ai
from ..db import session_scope
from ..metro_line4 import OPENING, SOURCE_NOTE
from ..models import ListingRow
from ..nl_search import area_matches
from . import components, queries

# The citation names the English-language source article; say so in Greek.
SOURCE_NOTE_GR = SOURCE_NOTE.replace(
    "Wikipedia «Line 4 (Athens Metro)»", "το αγγλικό άρθρο της Βικιπαίδειας για τη Γραμμή 4"
)

SEARCH_PAGE = "Αναζήτηση"
AREA_KEY = "area_pick"

# The buyer's 15 areas, by municipality name (matched with nl_search.area_matches, so case
# endings and Greek/Latin spellings meet: "Νέα Φιλαδέλφεια Αττικής", "Νέο Ψυχικό" …).
NE_AREAS = (
    "Χολαργός", "Παπάγου", "Αγία Παρασκευή", "Χαλάνδρι", "Βριλήσσια", "Μαρούσι", "Ζωγράφου",
    "Ψυχικό", "Φιλοθέη", "Ηράκλειο", "Νέα Φιλαδέλφεια", "Πεύκη", "Γαλάτσι", "Αμπελόκηποι",
    "Μεταμόρφωση",
)  # fmt: skip

# Confidence: how far the area's numbers can be trusted (listing count + rent samples).
HIGH_LISTINGS = 100
HIGH_RENT_SAMPLES = 20
CONF_HIGH, CONF_MID, CONF_LOW = "Υψηλή", "Μέτρια", "Χαμηλή"

# Human-readable scales of area_insights._components (kept next to the weights on screen).
SCALES = {
    "yield": ("Μικτή απόδοση", "από 3 % έως 7 %"),
    "affordability": (
        "Προσιτότητα",
        "από 20 % ακριβότερα έως 20 % φθηνότερα από τη ΒΑ Αθήνα",
    ),
    "stock": ("Καλό απόθεμα", "από 0 έως 30 διαμερίσματα"),
    "negotiability": ("Περιθώριο διαπραγμάτευσης", "από 0 % έως 40 % των αγγελιών με μείωση τιμής"),
    "momentum": ("Τάση τιμών", "από −5 % έως +5 % από τον Ιούλιο"),
}


# ---- pure helpers ------------------------------------------------------------------------


def is_ne(area: str) -> bool:
    """Whether an area name is one of the buyer's 15 NE-Athens areas."""
    return any(area_matches(a, area) for a in NE_AREAS)


def confidence(x: ai.AreaInsight) -> str:
    """Υψηλή / Μέτρια / Χαμηλή from the listing count and the rent sample count.

    No rent, under 50 listings or under 10 recorded rent samples → Χαμηλή. An unrecorded
    rent sample count can never be Υψηλή (we cannot say what the median rests on)."""
    if (
        x.gross_yield is None
        or x.n_fresh < ai.SMALL_SAMPLE
        or (x.rent_samples is not None and x.rent_samples < ai.FEW_RENT_SAMPLES)
    ):
        return CONF_LOW
    if x.rent_samples is None or x.n_fresh < HIGH_LISTINGS or x.rent_samples < HIGH_RENT_SAMPLES:
        return CONF_MID
    return CONF_HIGH


def _missing(v) -> bool:
    """None, NaN or ±inf (the table's stand-in for "not available", see ``_table``)."""
    return v is None or (isinstance(v, float) and not math.isfinite(v))


def gr_num(v, digits: int = 0) -> str:
    """Greek number: 2922 → '2.922', 5.43 (digits=1) → '5,4'; None/NaN → '—'."""
    if _missing(v):
        return "—"
    s = f"{v:,.{digits}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def gr_ppm(v) -> str:
    return "—" if _missing(v) else f"{gr_num(v)} €/τ.μ."


def gr_rent(v) -> str:
    return "—" if _missing(v) else f"{gr_num(v, 1)} €/τ.μ."


def gr_pct(fraction, digits: int = 1, sign: bool = False) -> str:
    """0.054 → '5,4 %' (sign=True: '+5,4 %')."""
    if _missing(fraction):
        return "—"
    s = gr_num(fraction * 100, digits)
    return f"+{s} %" if sign and fraction > 0 else f"{s} %"


def samples_text(x: ai.AreaInsight) -> str:
    return str(x.rent_samples) if x.rent_samples else "—"


def trend_text(x: ai.AreaInsight) -> str:
    n = ai.n_words(x.trend_early_n, x.trend_late_n)
    return f"— ({n})" if x.trend_pct is None else f"{gr_pct(x.trend_pct, sign=True)} ({n})"


def yield_text(x: ai.AreaInsight) -> str:
    """Yield at the all-stock median, and at the new-build median when there is one."""
    if x.gross_yield_new is None:
        return gr_pct(x.gross_yield)
    return f"{gr_pct(x.gross_yield)} στα παλιά · {gr_pct(x.gross_yield_new)} στα νεόδμητα"


def uc_text(x: ai.AreaInsight) -> str:
    """Under-construction share among new builds whose page was read: '2/5 με ελεγμένη περιγραφή'."""
    if not x.uc_checked:
        return "δεν έχει ελεγχθεί ακόμα κανένα νεόδμητο"
    return f"{x.uc_unfinished} από τα {x.uc_checked} νεόδμητα που ελέγξαμε"


def confidence_text(x: ai.AreaInsight) -> str:
    """Confidence word + what it rests on; says so when the rent sample count is unknown."""
    if confidence(x) == CONF_MID and x.rent_samples is None:
        return f"{CONF_MID}: δεν ξέρουμε από πόσες αγγελίες βγαίνει το ενοίκιο"
    return f"{confidence(x)}, με {ai.n_words(x.n_fresh)}"


def new_old_text(x: ai.AreaInsight) -> str:
    if x.new_premium is None:
        return (
            f"δεν το ξέρουμε ακόμα: θέλουμε {ai.MIN_BAND} νεόδμητα και {ai.MIN_BAND} παλιά, "
            f"έχουμε {ai.n_words(x.n_new, x.n_old)}"
        )
    return (
        f"τα νεόδμητα ζητούν {gr_pct(abs(x.new_premium), 0)} "
        f"{'περισσότερα' if x.new_premium >= 0 else 'λιγότερα'}: {gr_ppm(x.ppm_new)}, ενώ τα "
        f"παλιά {gr_ppm(x.ppm_old)} Μετρήσαμε {x.n_new} νεόδμητα και {x.n_old} παλιά"
    )


def trend_line(x: ai.AreaInsight) -> str:
    """Price trend of the area with its basis, or why there is none."""
    t = ai.exit_trend(x)
    if t is None:
        return f"δεν το ξέρουμε ακόμα: έχουμε μόνο {ai.n_words(x.trend_early_n, x.trend_late_n)}"
    return (
        f"{'ανέβηκε' if t[0] >= 0 else 'έπεσε'} {gr_pct(abs(t[0]))} {t[1]}, μετρώντας τις νέες "
        f"αγγελίες κάθε μήνα: {t[2]}"
    )


def supply_line(x: ai.AreaInsight) -> str:
    if x.supply_per_rent is None:
        return "δεν την ξέρουμε ακόμα"
    return (
        f"εδώ για κάθε σπίτι που νοικιάζεται πωλούνται {gr_num(x.supply_per_rent, 1)} "
        f"({x.rent_samples} ενοικιάσεις, {x.n_fresh} πωλήσεις)"
    )


_MONTHS = ("Ιαν", "Φεβ", "Μαρ", "Απρ", "Μάι", "Ιουν", "Ιουλ", "Αυγ", "Σεπ", "Οκτ", "Νοε", "Δεκ")
_BARS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    """One block character per value, scaled between the series' own min and max (flat
    series → middle bar). Text, so it renders at any phone width."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return _BARS[3] * len(values)
    return "".join(_BARS[round((v - lo) / (hi - lo) * 7)] for v in values)


def series_text(x: ai.AreaInsight) -> str:
    """«Ιουλ 2.589 (178 αγγελίες) · Αυγ 2.376 (18 αγγελίες)» — the monthly medians behind the trend."""
    return " · ".join(
        f"{_MONTHS[int(k[5:]) - 1]} {gr_num(p)} ({ai.n_words(n)})" for k, p, n in x.trend_series
    )


def render_series(x: ai.AreaInsight) -> None:
    """€/τ.μ. by month of first sighting (≥ 2 months): sparkline + the numbers with n."""
    if len(x.trend_series) < 2:
        return
    st.markdown(f"`{sparkline([p for _, p, _ in x.trend_series])}`  \n{series_text(x)}")


_VERDICT_TONE = {ai.GOOD: "good", ai.MID: "mid", ai.WARN: "warn", ai.UNKNOWN: "unk"}


def render_checks(checks: list[tuple[str, str, str]]) -> None:
    """The six investor checks as a phone-width list: label, value with its basis, verdict
    word (coloured text, no icons). Used by the listing page and the guide."""
    for label, value, verdict in checks:
        tone = _VERDICT_TONE.get(verdict, "unk")  # colours: theme.py .hg-v-* (status tokens)
        st.markdown(
            f'**{label}:** <span class="hg-v hg-v-{tone}">{verdict}</span>  \n'
            f"{value[:1].upper()}{value[1:]}",
            unsafe_allow_html=True,
        )


FILTERS_CAPTION = (
    "Μετράμε διαμερίσματα από τον 1ο όροφο και πάνω, όσα είδαμε στην αγορά τις τελευταίες "
    f"{queries.FRESH_DAYS} μέρες. Νεόδμητα είναι τα έως 5 ετών, παλιά τα 16 ετών και πάνω."
)


def verdicts(ranked: list[ai.AreaInsight], budget: int) -> list[str]:
    """The decision box's four one-line verdicts for the first screen: the area first in bold,
    one number each. The same picks as ``ai.decision`` (best yield; deepest market without
    falling prices; strongest €/τ.μ. trend; most new flats within budget near a station), whose
    full sentences with their basis go behind one tap (``test_where_to_buy`` keeps them equal)."""
    solid = [x for x in ranked if x.n_fresh >= ai.SMALL_SAMPLE] or ranked
    out = []
    ys = [x for x in solid if x.gross_yield is not None]
    if ys:
        x = max(ys, key=lambda a: a.gross_yield)
        out.append(f"**{x.area}** · απόδοση {ai._pct(x.gross_yield, 1)}")
    ok = [x for x in solid if x.trend_pct is None or x.trend_pct > ai.FALLING_TREND]
    if ok:
        known = [a for a in ok if a.gone_60 is not None or a.gone_30 is not None]
        if known:
            x = max(known, key=lambda a: (a.gone_60 if a.gone_60 is not None else a.gone_30))
            days, gone = (60, x.gone_60) if x.gone_60 is not None else (30, x.gone_30)
            out.append(f"**{x.area}** · ρευστότητα: {ai._pct(gone)} έφυγαν σε {days} μέρες")
        else:
            x = max(ok, key=lambda a: a.n_fresh)
            out.append(f"**{x.area}** · ρευστότητα: {x.n_fresh} αγγελίες")
    grow = [(t, x) for x in solid if (t := ai.exit_trend(x)) is not None]
    if grow:
        t, x = max(grow, key=lambda p: p[0][0])
        out.append(f"**{x.area}** · ανατίμηση {ai._signed(t[0])} €/τ.μ. {t[1]}")
    else:
        out.append("Ανατίμηση: δεν υπάρχει αρκετό ιστορικό τιμών ακόμα.")
    near = max(ranked, key=lambda a: a.near_station_in_budget, default=None)
    if near is not None and near.near_station_in_budget:
        out.append(f"**{near.area}** · {near.near_station_in_budget} νεόδμητα κοντά σε σταθμό")
    else:
        out.append("Νεόδμητο κοντά σε σταθμό: κανένα στο ποσό σου.")
    return out


def coverage_line(insights: list[ai.AreaInsight], listings: list[dict]) -> str:
    seen = [d["last_seen"] for d in listings if d.get("last_seen") is not None]
    when = f" έως {max(seen):%d/%m}" if seen else ""
    return (
        f"Τιμές που ζητούν στο XE.gr{when}. {len(insights)} περιοχές έχουν "
        f"τουλάχιστον {ai.MIN_FRESH} πρόσφατες αγγελίες"
    )


def table_frame(insights: list[ai.AreaInsight]) -> pd.DataFrame:
    """One numeric row per area (percentages as % numbers), so columns sort by value."""
    rows = []
    for x in insights:
        rows.append(
            {
                "Περιοχή": x.area,
                "Βαθμολογία": x.score,
                "Εμπιστοσύνη": confidence(x),
                "Πρόσφατες αγγελίες": x.n_fresh,
                "€/τ.μ. (όλα)": x.median_ppm,
                "€/τ.μ. (έως 30 ετών)": x.median_ppm_recent,
                "Αγγελίες (έως 30 ετών)": x.n_recent,
                "Ενοίκιο €/τ.μ./μήνα": x.rent_ppm,
                "Αγγελίες ενοικίασης": x.rent_samples or None,
                "Μικτή απόδοση": None if x.gross_yield is None else 100 * x.gross_yield,
                "Τάση από Ιούλιο": None if x.trend_pct is None else 100 * x.trend_pct,
                "Αγγελίες τάσης": f"{x.trend_early_n} και {x.trend_late_n}",
                "Με μείωση τιμής": 100 * x.cut_share,
                "Καλό απόθεμα": x.good_stock,
                "Νεόδμητα έναντι παλιών": None if x.new_premium is None else 100 * x.new_premium,
            }
        )
    return pd.DataFrame(rows)


_TABLE_FORMAT = {
    "Βαθμολογία": lambda v: gr_num(v, 1),
    "Πρόσφατες αγγελίες": gr_num,
    "€/τ.μ. (όλα)": gr_ppm,
    "€/τ.μ. (έως 30 ετών)": gr_ppm,
    "Αγγελίες (έως 30 ετών)": gr_num,
    "Ενοίκιο €/τ.μ./μήνα": gr_rent,
    "Αγγελίες ενοικίασης": gr_num,
    "Μικτή απόδοση": lambda v: gr_pct(None if _missing(v) else v / 100),
    "Τάση από Ιούλιο": lambda v: gr_pct(None if _missing(v) else v / 100, sign=True),
    "Με μείωση τιμής": lambda v: gr_pct(v / 100, 0),
    "Καλό απόθεμα": gr_num,
    "Νεόδμητα έναντι παλιών": lambda v: gr_pct(None if _missing(v) else v / 100, 0, sign=True),
}
PHONE_COLUMNS = ["Περιοχή", "Μικτή απόδοση", "€/τ.μ. (όλα)", "Πρόσφατες αγγελίες"]


def area_points(listings: list[dict], names: set[str]) -> dict[str, tuple[float, float, bool]]:
    """(lat, lng, approximate?) per area. Most listings carry only their SEARCH area's
    centroid, so: the median of 3+ exact listing points; else the area's own municipality
    centroid (matched by name); else the median of whatever points its listings have."""
    from ..enrich import MUNICIPALITY_CENTROIDS

    exact: dict[str, list[tuple[float, float]]] = {}
    anyp: dict[str, list[tuple[float, float]]] = {}
    for d in listings:
        if not (d.get("lat") and d.get("lng") and d.get("is_fresh", True)):
            continue
        name = ai.area_name(d.get("neighborhood"))
        if name not in names or not ai._eligible(d):
            continue
        p = (float(d["lat"]), float(d["lng"]))
        anyp.setdefault(name, []).append(p)
        if d.get("location_precision") == "exact":
            exact.setdefault(name, []).append(p)

    def med(pts: list[tuple[float, float]]) -> tuple[float, float]:
        return statistics.median(p[0] for p in pts), statistics.median(p[1] for p in pts)

    out = {}
    for name, pts in anyp.items():
        if len(exact.get(name, [])) >= 3:
            out[name] = (*med(exact[name]), False)
            continue
        own = next((c for k, c in MUNICIPALITY_CENTROIDS.items() if area_matches(k, name)), None)
        out[name] = (*(own or med(pts)), True)
    return out


# ---- data --------------------------------------------------------------------------------


@st.cache_data(ttl=10800, show_spinner=False)
def _lifecycle(stamp: tuple) -> list[dict]:
    """Every listing of every status (active AND gone) with only the fields liquidity needs
    — the page's own listings are active-only, so "went gone within N days" cannot be read
    from them. Lean query: no scoring, no annotation."""
    try:
        with session_scope() as session:
            return [
                {
                    "title": r.title,
                    "neighborhood": r.neighborhood,
                    "search_area": r.search_area,
                    "floor": r.floor,
                    "lat": r.lat,
                    "price_per_m2": r.price_per_m2,
                    "excluded": bool(r.excluded),
                    "status": r.status,
                    "first_seen": r.first_seen,
                    "last_seen": r.last_seen,
                }
                for r in session.scalars(
                    select(ListingRow).where(ListingRow.listing_type == "sale")
                ).all()
            ]
    except Exception:  # liquidity then reads «άγνωστη»; the page must still render
        return []


@st.cache_data(ttl=10800, show_spinner=False)
def _ranked(_listings: list[dict], stamp: tuple, budget: int) -> list[ai.AreaInsight]:
    """Ranked over the 15 NE-Athens SEARCHES (so the reference median is NE Athens and a
    score does not change with the toggle). ``stamp`` keys the cache on the data."""
    try:
        rents = queries.load_rent_comp_rows()
    except Exception:  # a missing rent table must not take the page down
        rents = []
    life = _lifecycle(stamp) or None
    return ai.rank_areas(_listings, rents, areas=ai.NE_ATHENS_AREAS, budget=budget, lifecycle=life)


def _stamp(listings: list[dict]) -> tuple:
    seen = [d["last_seen"] for d in listings if d.get("last_seen") is not None]
    return len(listings), str(max(seen)) if seen else ""


def _go_to_listings(area: str) -> None:
    st.session_state["page"] = SEARCH_PAGE
    st.session_state[AREA_KEY] = area


# ---- page --------------------------------------------------------------------------------


def _method() -> None:
    with st.expander("Πώς βαθμολογούμε"):
        rows = "\n".join(
            f"| {SCALES[k][0]} | {gr_num(100 * w)} % | {SCALES[k][1]} |"
            for k, w in ai.WEIGHTS.items()
        )
        st.markdown(
            "Δίνουμε πόντους σε κάθε περιοχή για την απόδοση, την τιμή, τα σπίτια που "
            "υπάρχουν, το περιθώριο για παζάρι και την τάση των τιμών, και τους προσθέτουμε. "
            "Πιο πολύ μετράει η απόδοση.\n\n"
            "**Βαθμολογία (0–100) = 100 × Σ βάρος × συνιστώσα.** Κάθε συνιστώσα παίρνει τιμή "
            "από 0 έως 1 σε σταθερή κλίμακα, όχι σε σύγκριση με τις άλλες περιοχές. Έτσι η ίδια "
            "βαθμολογία σημαίνει το ίδιο κάθε εβδομάδα. Όπου λείπει κάτι (ενοίκιο, τάση), η "
            "συνιστώσα παίρνει 0,5 και το γράφουμε στην «Προσοχή».\n\n"
            "| Συνιστώσα | Βάρος | Κλίμακα (από 0 έως 1) |\n|---|---|---|\n" + rows + "\n\n"
            "**Πώς βγαίνει κάθε αριθμός**\n"
            "- «Συνήθως» λέμε τη μεσαία τιμή: οι μισές αγγελίες ζητούν λιγότερα και οι μισές "
            "περισσότερα.\n"
            "- Μικτή απόδοση = 12 × το ενοίκιο που ζητούν συνήθως ανά τ.μ. τον μήνα ÷ την τιμή "
            "που ζητούν συνήθως ανά τ.μ. για αγορά. Είναι πριν από έξοδα, φόρους και μήνες "
            "χωρίς ενοικιαστή.\n"
            "- Τάση από Ιούλιο = όσο ζητούν συνήθως ανά τ.μ. οι αγγελίες που μπήκαν 16–31/10 ÷ "
            "όσο ζητούσαν αρχικά οι αγγελίες που μπήκαν τον Ιούλιο − 1. "
            f"Θέλουμε τουλάχιστον {ai.MIN_TREND} αγγελίες σε κάθε ομάδα, αλλιώς «—».\n"
            "- Καλό απόθεμα = διαμερίσματα έως 30 ετών, από 1ο όροφο, που ζητούν λιγότερα από "
            "τα άλλα σπίτια της ίδιας ηλικίας στην ίδια περιοχή.\n"
            "- Προσιτότητα = πόσο ζητούν εδώ σε σύγκριση με όλες τις πρόσφατες αγγελίες των 15 "
            "περιοχών της ΒΑ Αθήνας.\n"
            f"- Πρόσφατες αγγελίες = όσες βρήκαμε την τελευταία φορά που διαβάσαμε το XE.gr "
            f"(έως {queries.FRESH_DAYS} μέρες πριν). Περιοχή με "
            f"λιγότερες από {ai.MIN_FRESH} δεν βαθμολογείται. Ισόγεια, υπό κατασκευή και "
            "ύποπτες αγγελίες δεν μετράνε.\n\n"
            f"**Εμπιστοσύνη**: {CONF_HIGH} με τουλάχιστον {HIGH_LISTINGS} αγγελίες και "
            f"{HIGH_RENT_SAMPLES} αγγελίες ενοικίασης. {CONF_LOW} χωρίς ενοίκιο ή με "
            f"λιγότερες από {ai.SMALL_SAMPLE} αγγελίες ή {ai.FEW_RENT_SAMPLES} αγγελίες ενοικίασης. "
            f"{CONF_MID} σε όλες τις άλλες περιπτώσεις, και πάντα όταν δεν ξέρουμε από πόσες "
            "αγγελίες βγαίνει το ενοίκιο.\n\n"
            "**Τι δεν ξέρουμε**\n"
            "- Οι τιμές είναι όσα ζητούν οι αγγελίες στο XE.gr, όχι τιμές συμβολαίου. Συνήθως "
            "κλείνει χαμηλότερα.\n"
            "- Το ενοίκιο είναι όσο ζητούν οι αγγελίες ενοικίασης, όχι υπογεγραμμένα "
            "μισθωτήρια.\n"
            f"- **Τάση €/τ.μ.** = όσο ζητούσαν συνήθως ανά τ.μ. οι αγγελίες που μπήκαν τον "
            f"τελευταίο μήνα ÷ το ίδιο 6 μήνες πριν − 1. Θέλουμε τουλάχιστον {ai.MIN_MONTH} "
            "αγγελίες σε κάθε μήνα, αλλιώς γράφουμε «δεν το ξέρουμε ακόμα». Μετράνε μόνο "
            "αγγελίες που είναι ακόμα ενεργές. Συγκρίνουμε τις νέες αγγελίες κάθε μήνα, όχι τα "
            "ίδια διαμερίσματα.\n"
            f"- **Ρευστότητα** = πόσες αγγελίες κατέβηκαν μέσα σε 30 και 60 μέρες από τότε που "
            f"τις πρωτοείδαμε. Τη μετράμε μόνο όταν διαβάζουμε το XE.gr τακτικά (κενό έως "
            f"{ai.GAP_MAX} μέρες) και με τουλάχιστον {ai.MIN_LIQ} αγγελίες: "
            f"{ai.LIQUIDITY_THRESHOLDS}. Αγγελία που κατέβηκε δεν σημαίνει σπίτι που πουλήθηκε. "
            "Μπορεί να αποσύρθηκε ή να ξαναμπήκε.\n"
            "- **Ζήτηση ενοικίου** = αγγελίες πώλησης ÷ αγγελίες ενοικίασης που δίνουν το "
            "ενοίκιο της περιοχής.\n"
            f"- **Μετρό Γραμμή 4**: {SOURCE_NOTE_GR} Η χρονιά είναι εκτίμηση, όχι ημερομηνία "
            "παράδοσης. Τη συνδέουμε με αγγελία μόνο από το όνομα της γειτονιάς.\n"
            "- Οι μέρες στην αγορά μετράνε από τότε που είδαμε πρώτη φορά την αγγελία. Μέχρι να "
            "διαβάζουμε το XE.gr κάθε εβδομάδα δεν είναι αξιόπιστες, γι' αυτό δεν μπαίνουν στη "
            "βαθμολογία.\n"
            "- Η τάση συγκρίνει μόνο αγγελίες που είναι ακόμα ενεργές. Όσες πουλήθηκαν ή "
            "αποσύρθηκαν από τον Ιούλιο δεν μετράνε.\n"
            "- Διαβάζουμε μία μόνο πηγή, το XE.gr. Είναι μέρος της αγοράς, όχι κάθε αγγελία."
        )


def _liquidity_rows(x: ai.AreaInsight) -> list[tuple[str, str]]:
    """Liquidity and rent demand: both unknown → one short row; else only the known one."""
    liq = (
        [("Ρευστότητα", ai.liquidity_text(x) + f" ({ai.LIQUIDITY_THRESHOLDS})")]
        if x.liquidity
        else []
    )
    sup = [] if x.supply_per_rent is None else [("Ζήτηση ενοικίου", supply_line(x))]
    if liq or sup:
        return liq + sup
    return [
        (
            "Ρευστότητα και ζήτηση ενοικίου",
            "δεν τις ξέρουμε ακόμα. Τις μετράμε κάθε εβδομάδα από 30/10",
        )
    ]


def _card(rank: int | None, x: ai.AreaInsight, *, key: str) -> None:
    with st.container(border=True, key=f"area-card-{key}"):
        st.markdown(f"#### {rank}. {x.area}" if rank else f"##### {x.area}")
        st.markdown(x.why)
        rows = [
            ("Τιμή", f"{gr_ppm(x.median_ppm)} ζητούν συνήθως, σε {x.n_fresh} αγγελίες"),
            ("Νεόδμητα / παλιά", new_old_text(x)),
            (
                "Ενοίκιο (εκτίμηση)",
                f"{gr_rent(x.rent_ppm)}/μήνα"
                + (
                    f", από {x.rent_samples} αγγελίες ενοικίασης"
                    if x.rent_samples
                    else ", δεν ξέρουμε από πόσες αγγελίες"
                ),
            ),
            ("Μικτή απόδοση", yield_text(x)),
            ("Υπό κατασκευή", uc_text(x)),
            (
                "Στην αγορά",
                (
                    f"{gr_num(x.median_dom)} {'μέρα' if round(x.median_dom) == 1 else 'μέρες'} "
                    "συνήθως, από τότε που τις πρωτοείδαμε"
                    if x.median_dom
                    else "δεν το ξέρουμε ακόμα"
                ),
            ),
            ("Με μείωση τιμής", gr_pct(x.cut_share, 0)),
            ("Τάση €/τ.μ.", trend_line(x)),
            *_liquidity_rows(x),
            ("Σταθμός", ", ".join(x.stations) if x.stations else "καμία γειτονιά δεν έχει σταθμό"),
        ]
        if x.line4:
            rows.append(
                ("Μετρό Γραμμή 4 υπό κατασκευή", f"{', '.join(x.line4)}, γύρω στο {OPENING}")
            )
        if x.reg_flags:
            rows.append(("Κανονιστικά", " · ".join(x.reg_flags)))
        rows.append(("Εμπιστοσύνη", confidence_text(x)))
        st.markdown("\n".join(f"- **{k}:** {v[:1].upper()}{v[1:]}" for k, v in rows))
        render_series(x)
        st.markdown("**Προσοχή**\n" + "\n".join(f"- {r}" for r in x.risks))
        st.button(
            "Δες τις αγγελίες",
            key=f"area_go_{key}",
            on_click=_go_to_listings,
            args=(x.area,),
            width="stretch",
        )


def _table(insights: list[ai.AreaInsight]) -> None:
    # Streamlit draws a null cell as a grey English "None" whatever the Styler says, so a
    # missing number becomes −inf here: it sorts to the end and the formatter prints "—".
    df = table_frame(insights)
    nums = list(_TABLE_FORMAT)
    df[nums] = df[nums].astype(float).fillna(-math.inf)
    df = df[PHONE_COLUMNS]  # phone: 4 columns; the rest is in the card below
    cc = st.column_config
    st.dataframe(
        df.style.format({k: f for k, f in _TABLE_FORMAT.items() if k in PHONE_COLUMNS}),
        hide_index=True,
        width="stretch",
        height=min(35 * (len(df) + 1) + 3, 800),  # every area visible without inner scroll
        column_config={
            "Περιοχή": cc.TextColumn(pinned=True),
            "€/τ.μ. (όλα)": cc.NumberColumn("€/τ.μ.", help="Όσο ζητούν συνήθως για αγορά"),
            "Μικτή απόδοση": cc.NumberColumn(
                "Μικτή απόδοση", help="12 × ενοίκιο €/τ.μ. ÷ τιμή €/τ.μ."
            ),
            "Πρόσφατες αγγελίες": cc.NumberColumn("Αγγελίες"),
        },
    )
    st.caption("Πάτα μια επικεφαλίδα για ταξινόμηση. Η παύλα «—» σημαίνει λίγες αγγελίες.")


def _map(insights: list[ai.AreaInsight], listings: list[dict]) -> None:
    import pydeck as pdk

    pts = area_points(listings, {x.area for x in insights})
    recs = []
    for x in insights:
        if x.area not in pts:
            continue
        lat, lng, approx = pts[x.area]
        recs.append(
            {
                "lat": lat,
                "lon": lng,
                "fill": [*components.score_color(x.score), 220],
                "r": min(8 + math.sqrt(x.n_fresh) / 1.5, 22),
                "area": x.area,
                "score": gr_num(x.score, 1),
                "conf": confidence(x),
                "ppm": gr_ppm(x.median_ppm),
                "rent": gr_rent(x.rent_ppm),
                "yld": gr_pct(x.gross_yield),
                "n": str(x.n_fresh),
                "prec": "θέση: περίπου στο κέντρο της περιοχής" if approx else "",
            }
        )
    if not recs:
        st.info("Δεν έχουμε θέση στον χάρτη για καμία περιοχή.")
        return
    df = pd.DataFrame(recs)
    lat_c, lng_c, zoom = components._map_view(df["lat"].tolist(), df["lon"].tolist())
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_fill_color="fill",
        get_radius="r",
        radius_units="'pixels'",  # quoted: pydeck evals bare strings
        stroked=True,
        get_line_color=[255, 255, 255, 200],
        line_width_min_pixels=1,
        pickable=True,
    )
    tooltip = {
        "html": "<b>{area}</b><br/>Βαθμολογία <b>{score}</b> · εμπιστοσύνη {conf}<br/>"
        "Τιμή {ppm} · ενοίκιο (εκτίμηση) {rent}/μήνα<br/>Μικτή απόδοση {yld} · {n} αγγελίες"
        "<br/><i>{prec}</i>",
        "style": {"fontSize": "12px", "maxWidth": "280px"},
    }
    st.pydeck_chart(
        pdk.Deck(
            map_style="light",
            initial_view_state=pdk.ViewState(latitude=lat_c, longitude=lng_c, zoom=min(zoom, 11.5)),
            layers=[layer],
            tooltip=tooltip,
        ),
        height=420,
    )
    st.caption(
        "Μία κουκκίδα για κάθε περιοχή, στη μέση των αγγελιών της που έχουν ακριβή θέση, "
        "αλλιώς στο κέντρο της. Πράσινο σημαίνει υψηλή βαθμολογία, κόκκινο χαμηλή. Όσο πιο "
        "μεγάλη η κουκκίδα, τόσο περισσότερες αγγελίες."
    )


def page_areas(listings: list[dict]) -> None:
    st.markdown("## Πού να αγοράσω")
    ne_only = st.toggle(
        "Μόνο ΒΑ Αθήνα",
        value=True,
        key="areas_ne_only",
        help="Ανοιχτό: μόνο οι 15 περιοχές που ψάχνουμε. Κλειστό: και οι γειτονικές που "
        "βγαίνουν στις ίδιες αναζητήσεις (π.χ. Αχαρνές, Γέρακας).",
    )
    budget = int(st.session_state.get("find_budget", ai.DEFAULT_BUDGET))
    ranked = _ranked(listings, _stamp(listings), budget) if listings else []
    shown = [x for x in ranked if is_ne(x.area)] if ne_only else ranked
    if not shown:
        st.info(
            f"Καμία περιοχή δεν έχει ακόμα {ai.MIN_FRESH} πρόσφατες αγγελίες. Με λιγότερες "
            "δεν τις συγκρίνουμε."
        )
        return

    with st.container(border=True):
        st.markdown("**Για αγορά προς ενοικίαση**")
        for line in verdicts(shown, budget):
            st.markdown(line)
        with st.expander("Από πού βγαίνουν"):  # the sentences, their counts and the method
            for line in ai.decision(shown, budget):
                st.markdown(line)
            st.markdown("\n".join(f"- {line}" for line in ai.decision_basis(shown)))
            st.caption(coverage_line(shown, listings) + ". " + FILTERS_CAPTION)

    st.markdown("### Οι 3 περιοχές με την καλύτερη βαθμολογία")
    for i, x in enumerate(shown[:3], 1):
        _card(i, x, key=str(i))

    with st.expander(f"Όλες οι περιοχές ({len(shown)})"):
        _table(shown)
        pick = st.selectbox(
            "Αναλυτικά στοιχεία περιοχής", [x.area for x in shown], key="areas_detail"
        )
        _card(None, next(x for x in shown if x.area == pick), key="detail")

    st.markdown("### Χάρτης")
    _map(shown, listings)
    _method()
