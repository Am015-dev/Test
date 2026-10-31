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

from .. import area_insights as ai
from ..nl_search import area_matches
from . import components, queries

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
    "yield": ("Μικτή απόδοση", "3% → 7%"),
    "affordability": (
        "Προσιτότητα",
        "20% πάνω → 20% κάτω από τη διάμεση €/τ.μ. της ΒΑ Αθήνας",
    ),
    "stock": ("Καλό απόθεμα", "0 → 30 διαμερίσματα"),
    "negotiability": ("Περιθώριο διαπραγμάτευσης", "0% → 40% των αγγελιών με μείωση τιμής"),
    "momentum": ("Τάση τιμών", "−5% → +5% από τον Ιούλιο"),
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
    """0.054 → '5,4%' (sign=True: '+5,4%')."""
    if _missing(fraction):
        return "—"
    s = gr_num(fraction * 100, digits)
    return f"+{s}%" if sign and fraction > 0 else f"{s}%"


def samples_text(x: ai.AreaInsight) -> str:
    return str(x.rent_samples) if x.rent_samples else "—"


def trend_text(x: ai.AreaInsight) -> str:
    n = f"n={x.trend_early_n}/{x.trend_late_n}"
    return f"— ({n})" if x.trend_pct is None else f"{gr_pct(x.trend_pct, sign=True)} ({n})"


def coverage_line(insights: list[ai.AreaInsight], listings: list[dict]) -> str:
    seen = [d["last_seen"] for d in listings if d.get("last_seen") is not None]
    when = f" έως {max(seen):%d/%m}" if seen else ""
    return (
        f"Ζητούμενες τιμές XE.gr{when} · {len(insights)} περιοχές με "
        f"≥{ai.MIN_FRESH} πρόσφατες αγγελίες"
    )


def table_frame(insights: list[ai.AreaInsight]) -> pd.DataFrame:
    """One numeric row per area (percentages as % numbers), so columns sort by value."""
    rows = []
    for x in insights:
        rows.append(
            {
                "Περιοχή": x.area,
                "Σκορ": x.score,
                "Εμπιστοσύνη": confidence(x),
                "Πρόσφατες αγγελίες": x.n_fresh,
                "€/τ.μ. (όλα)": x.median_ppm,
                "€/τ.μ. ≤30 ετών": x.median_ppm_recent,
                "n ≤30 ετών": x.n_recent,
                "Ενοίκιο €/τ.μ./μήνα": x.rent_ppm,
                "Δείγματα ενοικίου": x.rent_samples or None,
                "Μικτή απόδοση": None if x.gross_yield is None else 100 * x.gross_yield,
                "Τάση από Ιούλιο": None if x.trend_pct is None else 100 * x.trend_pct,
                "n τάσης": f"{x.trend_early_n}/{x.trend_late_n}",
                "Με μείωση τιμής": 100 * x.cut_share,
                "Καλό απόθεμα": x.good_stock,
            }
        )
    return pd.DataFrame(rows)


_TABLE_FORMAT = {
    "Σκορ": lambda v: gr_num(v, 1),
    "Πρόσφατες αγγελίες": gr_num,
    "€/τ.μ. (όλα)": gr_ppm,
    "€/τ.μ. ≤30 ετών": gr_ppm,
    "n ≤30 ετών": gr_num,
    "Ενοίκιο €/τ.μ./μήνα": gr_rent,
    "Δείγματα ενοικίου": gr_num,
    "Μικτή απόδοση": lambda v: gr_pct(None if _missing(v) else v / 100),
    "Τάση από Ιούλιο": lambda v: gr_pct(None if _missing(v) else v / 100, sign=True),
    "Με μείωση τιμής": lambda v: gr_pct(v / 100, 0),
    "Καλό απόθεμα": gr_num,
}


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
def _ranked(_listings: list[dict], stamp: tuple) -> list[ai.AreaInsight]:
    """Ranked over the 15 NE-Athens SEARCHES (so the reference median is NE Athens and a
    score does not change with the toggle). ``stamp`` keys the cache on the data."""
    try:
        rents = queries.load_rent_comp_rows()
    except Exception:  # a missing rent table must not take the page down
        rents = []
    return ai.rank_areas(_listings, rents, areas=ai.NE_ATHENS_AREAS)


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
            f"| {SCALES[k][0]} | {gr_num(100 * w)}% | {SCALES[k][1]} |"
            for k, w in ai.WEIGHTS.items()
        )
        st.markdown(
            "**Σκορ (0–100) = 100 × Σ βάρος × συνιστώσα.** Κάθε συνιστώσα μετράει 0–1 σε "
            "σταθερή κλίμακα (όχι σε σχέση με τις άλλες περιοχές), άρα το ίδιο σκορ σημαίνει "
            "το ίδιο πράγμα κάθε εβδομάδα. Όπου λείπει στοιχείο (ενοίκιο, τάση) η συνιστώσα "
            "παίρνει ουδέτερο 0,5 και αναφέρεται ως κίνδυνος.\n\n"
            "| Συνιστώσα | Βάρος | Κλίμακα (0 → 1) |\n|---|---|---|\n" + rows + "\n\n"
            "**Τύποι**\n"
            "- Μικτή απόδοση = 12 × διάμεσο ζητούμενο ενοίκιο €/τ.μ./μήνα ÷ διάμεση "
            "ζητούμενη τιμή πώλησης €/τ.μ. (πριν από έξοδα, φόρους, κενά).\n"
            "- Τάση από Ιούλιο = διάμεση €/τ.μ. αγγελιών που εμφανίζονται 16–31/10 ÷ "
            "διάμεση αρχική €/τ.μ. αγγελιών που πρωτοεμφανίστηκαν τον Ιούλιο − 1. "
            f"Χρειάζονται ≥{ai.MIN_TREND} αγγελίες σε κάθε ομάδα, αλλιώς «—».\n"
            "- Καλό απόθεμα = διαμερίσματα έως 30 ετών, από 1ο όροφο, κάτω από τη διάμεση "
            "τιμή της ηλικιακής τους κατηγορίας στην ίδια περιοχή.\n"
            "- Προσιτότητα: σε σχέση με τη διάμεση ζητούμενη €/τ.μ. όλων των πρόσφατων "
            "αγγελιών από τις 15 αναζητήσεις ΒΑ Αθήνας.\n"
            f"- Πρόσφατες αγγελίες = εμφανίστηκαν στην τελευταία σάρωση "
            f"(≤{queries.FRESH_DAYS} ημέρες πριν από την πιο πρόσφατη). Περιοχή με "
            f"λιγότερες από {ai.MIN_FRESH} δεν αξιολογείται. Ισόγεια, ημιτελή και "
            "ύποπτες αγγελίες δεν μετράνε.\n\n"
            f"**Εμπιστοσύνη** — {CONF_HIGH}: ≥{HIGH_LISTINGS} αγγελίες και "
            f"≥{HIGH_RENT_SAMPLES} δείγματα ενοικίου. {CONF_LOW}: χωρίς ενοίκιο, "
            f"<{ai.SMALL_SAMPLE} αγγελίες ή <{ai.FEW_RENT_SAMPLES} δείγματα ενοικίου. "
            f"{CONF_MID}: όλα τα άλλα — και πάντα όταν ο αριθμός δειγμάτων του ενοικίου "
            "δεν έχει καταγραφεί («δείγματα: —»).\n\n"
            "**Τι δεν μπορούν να πουν τα δεδομένα**\n"
            "- Οι τιμές είναι ζητούμενες τιμές αγγελιών XE.gr, όχι τιμές συμβολαίου· η "
            "τελική τιμή είναι συνήθως χαμηλότερη.\n"
            "- Το ενοίκιο είναι ζητούμενο ενοίκιο από αγγελίες ενοικίασης, όχι "
            "υπογεγραμμένα μισθωτήρια.\n"
            "- Οι ημέρες στην αγορά μετρούν από τότε που είδαμε πρώτη φορά την αγγελία· "
            "μέχρι να γίνονται τακτικές εβδομαδιαίες σαρώσεις δεν είναι αξιόπιστες και δεν "
            "μπαίνουν στο σκορ.\n"
            "- Η τάση συγκρίνει ζητούμενες τιμές αγγελιών που είναι ακόμα ενεργές· όσες "
            "πουλήθηκαν ή αποσύρθηκαν από τον Ιούλιο δεν μετράνε.\n"
            "- Μόνο μία πηγή (XE.gr): μέρος της αγοράς, όχι κάθε αγγελία."
        )


def _card(rank: int, x: ai.AreaInsight) -> None:
    with st.container(border=True):
        st.markdown(f"#### {rank}. {x.area}")
        st.markdown(
            f"**Σκορ {gr_num(x.score, 1)}/100** · Εμπιστοσύνη: **{confidence(x)}**  \n"
            f"{x.n_fresh} πρόσφατες αγγελίες · δείγματα ενοικίου: {samples_text(x)}"
        )
        st.markdown(
            f"Ζητούμενη **{gr_ppm(x.median_ppm)}** (≤30 ετών {gr_ppm(x.median_ppm_recent)}, "
            f"n={x.n_recent}) · ενοίκιο **{gr_rent(x.rent_ppm)}**/μήνα · μικτή απόδοση "
            f"**{gr_pct(x.gross_yield)}** · τάση από Ιούλιο {trend_text(x)}"
        )
        st.markdown("**Γιατί**\n" + "\n".join(f"- {r}" for r in x.reasons))
        st.markdown("**Προσοχή**\n" + "\n".join(f"- {r}" for r in x.risks))
        st.button(
            "Δες τις αγγελίες",
            key=f"area_go_{rank}",
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
    cc = st.column_config
    st.dataframe(
        df.style.format(_TABLE_FORMAT),
        hide_index=True,
        width="stretch",
        height=min(35 * (len(df) + 1) + 3, 800),  # every area visible without inner scroll
        column_config={
            "Περιοχή": cc.TextColumn(pinned=True),
            "Σκορ": cc.NumberColumn(help="0–100, βλ. «Πώς βαθμολογούμε»"),
            "€/τ.μ. (όλα)": cc.NumberColumn(help="Διάμεση ζητούμενη τιμή πώλησης"),
            "€/τ.μ. ≤30 ετών": cc.NumberColumn(help="Διάμεση ζητούμενη, κτίρια έως 30 ετών"),
            "Ενοίκιο €/τ.μ./μήνα": cc.NumberColumn(help="Διάμεσο ζητούμενο ενοίκιο"),
            "Δείγματα ενοικίου": cc.NumberColumn(help="«—» = δεν έχει καταγραφεί ακόμα"),
            "Μικτή απόδοση": cc.NumberColumn(help="12 × ενοίκιο €/τ.μ. ÷ τιμή €/τ.μ."),
            "Τάση από Ιούλιο": cc.NumberColumn(
                help="Ζητούμενη €/τ.μ. τέλη Οκτωβρίου έναντι Ιουλίου (n στη διπλανή στήλη)"
            ),
            "n τάσης": cc.TextColumn(help="Αγγελίες Ιουλίου / τέλη Οκτωβρίου"),
            "Με μείωση τιμής": cc.NumberColumn(help="Ποσοστό αγγελιών που έχουν μειώσει τιμή"),
            "Καλό απόθεμα": cc.NumberColumn(
                help="Έως 30 ετών, από 1ο όροφο, κάτω από τη διάμεση της ηλικίας τους"
            ),
        },
    )
    st.caption("Κλικ σε επικεφαλίδα για ταξινόμηση. «—» = δεν υπάρχει αρκετό δείγμα.")


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
                "prec": "θέση: κέντρο περιοχής (κατά προσέγγιση)" if approx else "",
            }
        )
    if not recs:
        st.info("Καμία περιοχή δεν έχει θέση στον χάρτη.")
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
        "html": "<b>{area}</b><br/>Σκορ <b>{score}</b> · εμπιστοσύνη {conf}<br/>"
        "Ζητούμενη {ppm} · ενοίκιο {rent}/μήνα<br/>Μικτή απόδοση {yld} · {n} αγγελίες"
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
        "Ένα σημείο ανά περιοχή (διάμεση θέση αγγελιών με ακριβή θέση, αλλιώς το κέντρο "
        "της περιοχής). Χρώμα = σκορ (κόκκινο χαμηλό → πράσινο υψηλό), μέγεθος = "
        "πλήθος αγγελιών."
    )


def page_areas(listings: list[dict]) -> None:
    st.markdown("## Πού να αγοράσω")
    ne_only = st.toggle(
        "Μόνο ΒΑ Αθήνα",
        value=True,
        key="areas_ne_only",
        help="Οι 15 περιοχές της αναζήτησής σου. Κλειστό: και γειτονικές περιοχές που "
        "εμφανίζονται στις ίδιες αναζητήσεις (π.χ. Αχαρνές, Γέρακας).",
    )
    ranked = _ranked(listings, _stamp(listings)) if listings else []
    shown = [x for x in ranked if is_ne(x.area)] if ne_only else ranked
    st.caption(coverage_line(shown, listings))
    _method()
    if not shown:
        st.info(
            f"Καμία περιοχή δεν έχει ακόμα ≥{ai.MIN_FRESH} πρόσφατες αγγελίες για "
            "αξιόπιστη σύγκριση."
        )
        return

    st.markdown("### Οι 3 καλύτερες για αγορά προς ενοικίαση")
    for col, (i, x) in zip(st.columns(3), enumerate(shown[:3], 1), strict=False):
        with col:
            _card(i, x)

    st.markdown("### Όλες οι περιοχές")
    _table(shown)

    st.markdown("### Χάρτης")
    _map(shown, listings)
