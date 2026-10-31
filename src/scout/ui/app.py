"""Streamlit app — reads the DB the pipeline populated and surfaces opportunities.

Pages: Opportunities (home), Today, Map, Listing detail, Watchlist, Strategy, Debug.
The app NEVER scrapes in the request cycle; scraping is the scheduled pipeline's
job. A "Refresh now" button runs the pipeline explicitly in the foreground.

Design goals: answer "what should I look at today?" at a glance (KPI header + top
picks + a ranked, readable table), and NEVER render a blank screen when there is
real data — if nothing passes the hard filters, show everything with the reason.

Run:  streamlit run src/scout/ui/app.py
"""

from __future__ import annotations

import os
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Allow running via `streamlit run src/scout/ui/app.py` without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _source_stamp() -> float:
    """Newest modification time across the scout package's source files."""
    return max(f.stat().st_mtime for f in Path(__file__).resolve().parents[1].rglob("*.py"))


def _drop_stale_scout_modules() -> None:
    """Streamlit Cloud pulls new code into the RUNNING process and re-runs this script, but the
    scout modules imported on an earlier run stay cached in sys.modules — new app.py + old
    helpers = AttributeError. Unless the loaded package carries the current source stamp,
    forget every scout module so this run imports the code on disk."""
    pkg = sys.modules.get("scout")
    if pkg is None or getattr(pkg, "_source_stamp", None) == _SOURCE_STAMP:
        return
    try:  # only code pulled AFTER this process started can be stale in memory
        started = Path(f"/proc/{os.getpid()}").stat().st_ctime
    except OSError:
        return
    if _SOURCE_STAMP > started:
        for n in [n for n in sys.modules if n == "scout" or n.startswith("scout.")]:
            del sys.modules[n]


_SOURCE_STAMP = _source_stamp()
_drop_stale_scout_modules()

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

# Streamlit Cloud's Secrets manager populates st.secrets, NOT the process environment —
# but Settings (config.py) is a pydantic-settings BaseSettings that only reads env vars /
# .env. Bridge DATABASE_URL across so the deployed app reaches the same Postgres the daily
# workflow writes to, instead of silently falling back to a local (empty) SQLite file.
# Guarded: st.secrets raises if no secrets.toml exists at all (e.g. local `streamlit run`).
try:
    if "DATABASE_URL" in st.secrets:
        # Unconditional overwrite, not setdefault: a stray/stale DATABASE_URL already
        # present in the container's environment must never silently win over the
        # secret the user actually configured.
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
    for _name in ("GITHUB_TOKEN", "GITHUB"):  # accept either secret name
        if _name in st.secrets:
            os.environ["GITHUB_TOKEN"] = st.secrets[_name]
            break
except Exception:
    pass

from scout import (  # noqa: E402
    acquisition,
    analytics,
    comps,
    comps_panel,
    deal_scorecard,
    epbd,
    finance,
    investment,
    liquidity,
    listing_report,
    projection,
    score_explain,
    sensitivity,
    shortlist,
)
from scout.config import Strategy, get_settings, load_strategy, save_strategy  # noqa: E402
from scout.regions import REGIONS  # noqa: E402
from scout.regulatory import (  # noqa: E402
    golden_visa_status,
    renovation_subsidy,
    str_legality,
)
from scout.relative_value import (  # noqa: E402
    relative_value,
    relative_yield,
)
from scout.scoring import (  # noqa: E402
    energy_class_score,
    energy_liability_multiplier,
    newness_score,
)  # noqa: E402
from scout.strategy_fit import STRATEGY_LABELS, strategy_label  # noqa: E402
from scout.ui import (  # noqa: E402
    account,  # noqa: E402
    areas,  # noqa: E402
    buyer,  # noqa: E402
    components,  # noqa: E402
    queries,  # noqa: E402
)

# Round-3 pages land in separate PRs: use each when it exists, keep today's page otherwise.
try:
    from scout.ui import guide  # noqa: E402
except ImportError:
    guide = None
try:
    from scout.ui import find  # noqa: E402
except ImportError:  # retired into the guide
    find = None
try:
    from scout.ui import maplist  # noqa: E402
except ImportError:
    maplist = None
try:
    from scout.collectors import SOURCE_LABELS  # noqa: E402
except ImportError:
    SOURCE_LABELS = {"xe": "XE.gr"}
from scout.ui import format as fmt  # noqa: E402

sys.modules["scout"]._source_stamp = _SOURCE_STAMP
from scout.ui.theme import inject_css  # noqa: E402

st.set_page_config(
    page_title="Holargos Property Scout",
    page_icon="🏠",
    layout="wide",
    # "auto": open on desktop, collapsed on phones. "expanded" covered the whole page on a
    # phone, hiding the content until the user found the « button.
    initial_sidebar_state="auto",
)
inject_css()

# MEMORY: the big reads use st.cache_RESOURCE, not cache_data. cache_data pickles the
# value and hands every access a fresh deep copy — with 22k listing dicts (~226 MB
# materialised) a couple of concurrent reruns blew straight past Streamlit Community
# Cloud's ~1 GB limit and the app OOM-restarted (dropped websocket, "lost" sidebar).
# cache_resource shares ONE object across sessions; pages treat these as READ-ONLY —
# never mutate a dict from these caches (copy first).
#
# TTL=3h on the expensive loaders below (was 5-10min): materializing ~23k ORM rows from
# the DB takes ~4-5s, and at a 5-min TTL EVERY visitor after a 5-min gap paid that cost —
# the dominant cause of the app "feeling frozen". The underlying data only changes once a
# day (the scheduled daily-refresh workflow), so a short TTL bought near-zero freshness
# for a real, frequent latency hit. The "Refresh now" button clears both cache_data AND
# cache_resource explicitly, so anyone who needs it fresher NOW still gets that instantly —
# this TTL only controls the passive/background refresh cadence.


@st.cache_resource(ttl=21600, show_spinner="Κατεβάζω τις πιο πρόσφατες αγγελίες…")
def _sync_data() -> bool:
    """Pull the daily-published DB from the repo's `data` branch (no-op with DATABASE_URL)."""
    from scout import remote_db
    from scout.db import init_db

    fresh = remote_db.ensure_local_db()
    init_db()  # also creates the tables when there is no published DB yet
    return fresh


@st.cache_resource(
    ttl=10800, show_spinner="Φορτώνω τις αγγελίες και υπολογίζω τις τιμές της αγοράς…"
)
def get_listings() -> list[dict]:
    _sync_data()
    # Market-position annotation (price/yield percentile vs comparable active listings),
    # strategy tags and the BUY/WATCH/PASS recommendation are all computed inside
    # load_listings() itself now — every caller (this page, the digest, health/data-quality
    # checks) needs the same honest, area-relative numbers, not just the UI.
    return queries.load_listings(include_excluded=True, only_active=True)


@st.cache_data(ttl=10800)
def get_strategy() -> Strategy:
    return load_strategy()


@st.cache_resource(ttl=10800)
def get_all_listings_debug() -> list[dict]:
    """Everything, including excluded and inactive (gone) listings — for the Debug page."""
    return queries.load_listings(
        include_excluded=True, only_active=False, collapse_relistings=False
    )


@st.cache_data(ttl=60)
def get_history(listing_id: int):
    return queries.load_price_history(listing_id)


@st.cache_resource(ttl=10800)
def get_all_price_history() -> list[dict]:
    return queries.load_all_price_history()


@st.cache_data(ttl=120)
def get_recent_health() -> list[dict]:
    return queries.load_recent_health(10)


@st.cache_resource(ttl=10800)
def get_valuation_summary() -> dict:
    return queries.load_valuation_summary()


@st.cache_data(ttl=60)
def get_recent_price_drops(hours: int = 24) -> list[dict]:
    return queries.load_recent_price_drops(hours)


def _valuation_banner() -> dict:
    """Show — honestly — how much to trust the fair-value numbers, and return the summary
    so callers can render ± bands. Never implies more precision than the fit supports."""
    v = get_valuation_summary()
    if not v.get("fitted"):
        st.info(
            "**Μοντέλο εκτιμώμενης αξίας:** δεν υπάρχουν ακόμα αρκετές συγκρίσιμες αγγελίες "
            "για αποτίμηση βάσει χαρακτηριστικών — εμφανίζονται μόνο τιμές €/τ.μ."
        )
        return v
    o = v["overall"]
    r2, n, n_areas = o["r2"], o["n"], o.get("n_areas", 1)
    band = f"±{(pow(2.718281828, o['residual_std']) - 1) * 100:.0f}%"
    scope = f"{n_areas} μοντέλα ανά περιοχή σε {n} συγκρίσιμες αγγελίες"
    basis = (
        "Οι εκτιμήσεις είναι **σε σχέση με τις ΖΗΤΟΥΜΕΝΕΣ τιμές** κάθε περιοχής (οι τιμές "
        "πώλησης στην Ελλάδα δεν είναι δημόσιες) — δείχνουν *τιμή έναντι συγκρίσιμων "
        "αγγελιών*, όχι έναντι της τιμής που τελικά πουλιούνται τα ακίνητα."
    )
    # One-line headline, with the full honesty caveats tucked in an expander so the top of
    # the page isn't a five-line wall of yellow text on every visit.
    conf = "αξιόπιστο" if o["is_confident"] else "ενδεικτικό — ξεχώρισε και μετά επιβεβαίωσε"
    headline = f"📐 Μοντέλο εκτιμώμενης αξίας: R²={r2:.2f}, τυπικό εύρος {band} — {conf}."
    (st.success if o["is_confident"] else st.warning)(headline)
    with st.expander("Πώς διαβάζεται η εκτιμώμενη αξία"):
        st.markdown(
            f"{scope}. {basis} Μεγάλο εύρος ± σημαίνει ότι το μοντέλο δεν αποτιμά με ακρίβεια "
            "αυτή την περιοχή — χρησιμοποίησε την κατάταξη για να ξεχωρίσεις αγγελίες "
            "και επιβεβαίωσε κάθε μία στην πηγή."
        )
    return v


def _last_updated(listings: list[dict]) -> datetime | None:
    """Most recent time any listing was seen by the pipeline."""
    seens = [d["last_seen"] for d in listings if d["last_seen"]]
    return max(seens) if seens else None


def _eligible(listings: list[dict]) -> list[dict]:
    """Listings that pass the hard filters (not excluded)."""
    return [d for d in listings if not d["excluded"]]


# Display labels for the deal-scorecard verdict (the English value stays the data key).
VERDICT_GR = {"Strong": "Ισχυρή", "Fair": "Μέτρια", "Pass": "Απόρριψη"}
# Short-let (Airbnb) filter options on Opportunities.
SL_ANY, SL_ALLOWED, SL_FROZEN = "Όλα", "Επιτρέπεται Airbnb", "Πάγωμα (μόνο μακροχρόνια)"


# ---- shared rendering helpers ---------------------------------------------


def _metro_label(d: dict) -> str:
    m = d["metro_distance_m"]
    return f"{m} m" if m is not None else "άγνωστη"


def _floor_label(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}"


def _max_affordable_price(
    monthly_income: float,
    *,
    dsr: float = 0.35,
    rate: float = 0.045,
    term_years: int = 25,
    deposit_pct: float = 0.30,
) -> int | None:
    """Max purchase price supported by a monthly net income: cap the mortgage payment at a
    debt-service ratio of income, invert the amortization to a loan, then gross up for the
    deposit. A rough affordability gate for filtering, not mortgage advice."""
    if monthly_income <= 0:
        return None
    max_payment = monthly_income * dsr
    r = rate / 12
    n = term_years * 12
    loan = max_payment * n if r <= 0 else max_payment * (1 - (1 + r) ** -n) / r
    return int(loan / max(1 - deposit_pct, 1e-9))


def _table(rows: list[dict], show_reason: bool = False) -> None:
    """Render listings as a sortable, readable table (sorted by score, desc)."""
    records = []
    for d in rows:
        rec = {
            "Σκορ": round(d["score"], 0),
            "Κατηγορία": components.archetype_label(d.get("archetype")),
            "Τιμή": d["price"],
            # Only show a "Fair value" figure the model could actually stand behind (its
            # value_gap survived the confidence + real-attributes gate); blank otherwise so
            # an imputed prediction isn't read as a precise valuation.
            "Εκτιμώμενη αξία": (
                d.get("predicted_price") if d.get("value_gap_pct") is not None else None
            ),
            "Απόκλιση αξίας": (
                (d.get("value_gap_pct") * 100) if d.get("value_gap_pct") is not None else None
            ),
            # Honest market-position rank: cheaper per m² than N% of comparable active listings.
            "Έναντι αγοράς": (
                d["value_percentile"] * 100 if d.get("value_percentile") is not None else None
            ),
            "€/τ.μ.": d["price_per_m2"],
            "Εμβαδόν": d["area_m2"],
            "Όροφος": d["floor"],
            "Έτος": d.get("renovated_year") or d.get("year_built"),
            "Ενεργ. κλάση": d.get("energy_class") or "",
            "Απόδοση": (d["gross_yield"] * 100) if d["gross_yield"] is not None else None,
            "Airbnb": {
                "FROZEN": "🚫 πάγωμα",
                "EXPANDING_RISK": "⚠️ κίνδυνος",
                "ALLOWED": "✓ επιτρέπεται",
            }.get(str_legality(_area_key(d)).status, ""),
            "Μετρό": d["metro_distance_m"],
            "Γειτονιά": d["neighborhood"] or "—",
            "Σημάνσεις": " ".join(fmt.badges(d)) or "",
            "Σύνδεσμος": d["url"],
        }
        if show_reason:
            rec["Λόγος αποκλεισμού"] = d["exclusion_reason"] or ""
        records.append(rec)
    df = pd.DataFrame(records)
    column_config = {
        "Σκορ": st.column_config.ProgressColumn(
            "Σκορ",
            help="0–100: ταίριασμα με τη στρατηγική",
            min_value=0,
            max_value=100,
            format="%.0f",
        ),
        "Κατηγορία": st.column_config.TextColumn(
            "Κατηγορία",
            help="Νεόδμητο / Ανακαινισμένο / Σύγχρονο / Παλαιό / Ενεργοβόρο",
        ),
        "Τιμή": st.column_config.NumberColumn("Τιμή", format="€%d"),
        "Εκτιμώμενη αξία": st.column_config.NumberColumn(
            "Εκτιμώμενη αξία",
            help="Εκτίμηση του μοντέλου έναντι της ΤΥΠΙΚΗΣ ΖΗΤΟΥΜΕΝΗΣ τιμής παρόμοιων "
            "διαμερισμάτων (εύρος ±44%, όχι αποτίμηση τιμής πώλησης — στην Ελλάδα δεν "
            "υπάρχει δημόσιο μητρώο πωλήσεων). Κενό όταν η εκτίμηση είναι αβέβαιη.",
            format="€%d",
        ),
        "Απόκλιση αξίας": st.column_config.NumberColumn(
            "Έναντι ζητούμενης (εκτ.)",
            help="+ = τιμή κάτω από την εκτίμηση του μοντέλου για την τυπική ζητούμενη. "
            "Ενδεικτικό φίλτρο, όχι αποδεδειγμένη έκπτωση.",
            format="%+.0f%%",
        ),
        "Έναντι αγοράς": st.column_config.NumberColumn(
            "Έναντι αγοράς",
            help="Φθηνότερο ανά τ.μ. από αυτό το % συγκρίσιμων ενεργών αγγελιών (ίδια "
            "περιοχή, ±30% εμβαδόν). Πραγματική θέση στην αγορά — χωρίς ψευδο-ακρίβεια.",
            format="%.0f%%",
        ),
        "Airbnb": st.column_config.TextColumn(
            "Airbnb",
            help="Επιτρέπεται νέα βραχυχρόνια μίσθωση (Airbnb) εδώ; (πάγωμα Αθήνας 2026)",
        ),
        "€/τ.μ.": st.column_config.NumberColumn("€/τ.μ.", format="€%.0f"),
        "Εμβαδόν": st.column_config.NumberColumn("Εμβαδόν", format="%.0f τ.μ."),
        "Όροφος": st.column_config.NumberColumn("Όροφος", format="%.0f"),
        "Έτος": st.column_config.NumberColumn(
            "Έτος", help="έτος κατασκευής / ανακαίνισης", format="%d"
        ),
        "Ενεργ. κλάση": st.column_config.TextColumn("Ενεργ. κλάση", help="ενεργειακή κλάση (ΠΕΑ)"),
        "Απόδοση": st.column_config.NumberColumn("Απόδοση", format="%.1f%%"),
        "Μετρό": st.column_config.NumberColumn(
            "Μετρό", help="απόσταση με τα πόδια ως τη Γραμμή 3", format="%d m"
        ),
        "Σύνδεσμος": st.column_config.LinkColumn("Σύνδεσμος", display_text="άνοιγμα ↗"),
    }
    st.dataframe(df, width="stretch", hide_index=True, column_config=column_config)


def _kpi_header(listings: list[dict]) -> None:
    eligible = _eligible(listings)
    buys = sum(1 for d in eligible if d.get("rec_verdict") == "BUY")
    ppm = [d["price_per_m2"] for d in eligible if d.get("price_per_m2")]
    drops = sum(1 for d in eligible if d.get("price_dropped"))
    c = st.columns(4)
    c[0].metric("Αγγελίες", len(eligible), help="Ενεργές αγγελίες που περνούν τα φίλτρα")
    c[1].metric(
        "🟢 Προτάσεις αγοράς",
        buys,
        help="Αγγελίες που περνούν το αυστηρό κριτήριο «Αγορά» — η επιλεγμένη λίστα, "
        "όχι όλο το απόθεμα",
    )
    c[2].metric("Διάμεσο €/τ.μ.", fmt.euro_per_m2(statistics.median(ppm)) if ppm else "—")
    c[3].metric("📉 Μειώσεις τιμής", drops)


def _area_key(d: dict) -> str | None:
    """The area name to resolve regulatory zones against. `search_area` is the clean Latin
    scrape area ("Koukaki", "Pagkrati") that matches the regulatory tables; `neighborhood`
    is free-text Greek ("Αθήνα (Κουκάκι)") and won't match — so prefer search_area."""
    return d.get("search_area") or d.get("neighborhood")


def _regulatory_panel(d: dict) -> None:
    """The differentiator no portal shows: can a buyer legally short-let this, does it clear
    the Golden-Visa bar, is it an energy-subsidy candidate. Indicative flags — always tell the
    user to verify with a lawyer; regulation shifts and a wrong call costs real money."""
    strl = str_legality(_area_key(d))
    gv = golden_visa_status(d.get("price"), d.get("area_m2"))
    reno = renovation_subsidy(d.get("energy_class"), d.get("year_built"))

    st.markdown("#### 📜 Νομικός έλεγχος — όσα δεν λένε οι αγγελίες")
    box = {"FROZEN": st.error, "EXPANDING_RISK": st.warning, "ALLOWED": st.success}.get(
        strl.status, st.info
    )
    box(f"**Βραχυχρόνια μίσθωση (Airbnb):** {strl.headline} — {strl.detail}")

    cols = st.columns(2)
    (cols[0].success if gv.qualifies else cols[0].info)(
        f"**Golden Visa:** {gv.headline}" + (f" — {gv.detail}" if gv.detail else "")
    )
    if reno.candidate:
        cols[1].info(f"**Επιδότηση ενέργειας:** {reno.headline} — {reno.detail}")
    else:
        cols[1].caption(
            "Επιδότηση ενέργειας: δεν ισχύει (απαιτεί ενεργειακή κλάση Γ ή χαμηλότερη)."
        )
    st.caption(
        "⚖️ Ενδεικτικές ενδείξεις από τους δημόσιους κανόνες του 2026 — επιβεβαίωσε "
        "Airbnb / Golden Visa / επιδότηση με δικηγόρο πριν δεσμευτείς."
    )


# ---- investment-thesis helpers --------------------------------------------


def _investment_bullets(d: dict) -> list[str]:
    """Plain-language reasons why this listing is (or isn't) interesting, ordered by impact."""
    bullets: list[str] = []

    # Undervaluation vs hedonic fair value — the headline "is this a real bargain?" signal.
    gap = d.get("value_gap_pct")
    fair = d.get("predicted_price")
    if gap is not None and fair:
        if gap >= 0.10:
            bullets.append(
                f"**{gap*100:.0f}% κάτω από την εκτιμώμενη αξία** → το μοντέλο το αποτιμά "
                f"{fmt.euro(fair)} έναντι {fmt.euro(d.get('price', 0))} που ζητείται"
            )
        elif gap <= -0.10:
            bullets.append(
                f"**{abs(gap)*100:.0f}% πάνω από την εκτιμώμενη αξία** — το μοντέλο το αποτιμά "
                f"{fmt.euro(fair)}"
            )

    # Yield + income — most important signal
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    gy = d.get("gross_yield")
    if gy:
        annual = monthly * 12 if monthly else None
        if annual:
            bullets.append(
                f"**{gy*100:.1f}% μικτή απόδοση** → {fmt.euro(monthly)}/μήνα · "
                f"{fmt.euro(annual)}/έτος"
            )
        else:
            bullets.append(f"**{gy*100:.1f}% μικτή απόδοση**")

    # Newness & energy — quality signals (new/efficient stock rents better, holds value)
    yr = d.get("renovated_year") or d.get("year_built")
    if yr:
        label = "Ανακαίνιση" if d.get("renovated_year") else "Κατασκευή"
        tag = " — **νεόδμητο**" if yr >= 2010 else (" — παλαιό" if yr < 1990 else "")
        bullets.append(f"{label} **{yr}**{tag}")
    ec = d.get("energy_class")
    if ec:
        score_ec = energy_class_score(ec)
        if score_ec >= 0.75:
            note = " — αποδοτικό"
        elif energy_liability_multiplier(ec, get_strategy().scoring_reference) < 0.999:
            note = " — ⚠️ υποχρέωση ανακαίνισης EPBD (μειωμένο σκορ)"
        else:
            note = ""
        bullets.append(f"**Ενεργειακή κλάση {ec}**{note}")

    # Price drop — timing signal
    fp = d.get("first_price")
    cp = d.get("price", 0)
    if fp and cp < fp:
        drop_pct = (fp - cp) / fp * 100
        bullets.append(f"**Μείωση τιμής {drop_pct:.0f}%** από αρχικά {fmt.euro(fp)}")

    # Private seller — saves agent fees
    if d.get("is_private_seller"):
        bullets.append("**Ιδιώτης πωλητής** — χωρίς μεσιτική αμοιβή")

    # Currently rented — immediate cashflow
    if d.get("is_currently_rented"):
        rent_str = f" με {fmt.euro(d['listed_rent'])}/μήνα" if d.get("listed_rent") else ""
        bullets.append(f"**Ήδη νοικιασμένο{rent_str}** — έσοδο από την πρώτη μέρα")

    # Metro proximity — rental demand driver
    metro = d.get("metro_distance_m")
    nearest = d.get("nearest_metro") or "μετρό"
    if metro is not None:
        qualifier = "δίπλα" if metro <= 200 else ("με τα πόδια" if metro <= 400 else "")
        if qualifier:
            bullets.append(f"**{metro} m ({qualifier}) από {nearest}** (Γραμμή 3)")
        else:
            bullets.append(f"{metro} m από {nearest}")

    # Timing: days on market
    dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
    if dom is not None:
        if dom == 0:
            bullets.append("**Νέα αγγελία σήμερα** — κινήσου γρήγορα")
        elif dom >= 60:
            bullets.append(f"**{dom} μέρες στην αγορά** — ο πωλητής πιθανώς διαπραγματεύεται")
        elif dom >= 14:
            bullets.append(f"{dom} μέρες στην αγορά")

    return bullets


def _score_breakdown(d: dict, strategy: Strategy) -> None:
    """Render a table showing each signal's contribution to the score."""
    # Plain-language "why this score" first — what lifted it, what lowered it, what's
    # unknown (and therefore not scored) — before the detailed weight table.
    rows = score_explain.explain_score(d)
    if rows:
        icon = {"positive": "🟢", "negative": "🔴", "unknown": "⚪"}
        for r in rows:
            st.markdown(f"{icon.get(r['effect'], '•')} **{r['label']}** — {r['detail']}")
    w = strategy.weights
    ref = strategy.scoring_reference
    total_w = w.total() or 1.0

    # Recompute signals from stored fields (mirrors scoring.py, no DB needed)
    gy = d.get("gross_yield") or 0
    span = max(ref.yield_ceiling - ref.yield_floor, 1e-9)
    yield_sig = max(0.0, min(1.0, (gy - ref.yield_floor) / span)) if gy else 0.0

    fp, cp = d.get("first_price"), d.get("price", 0)
    if fp and fp > 0 and cp < fp:
        drop_sig = max(0.0, min(1.0, (fp - cp) / fp / max(ref.max_price_drop_pct, 1e-9)))
    else:
        drop_sig = 0.0

    rented_sig = 1.0 if d.get("is_currently_rented") else 0.0
    private_sig = 1.0 if d.get("is_private_seller") else 0.0
    new_sig = newness_score(d.get("year_built"), d.get("renovated_year"), ref)
    energy_sig = energy_class_score(d.get("energy_class"))
    built = d.get("renovated_year") or d.get("year_built")

    gap = d.get("value_gap_pct")
    target = max(getattr(ref, "target_undervaluation", 0.20), 1e-9)
    if gap is not None:
        under_sig = max(0.0, min(1.0, gap / target))
        under_value = f"{gap*100:+.0f}% έναντι αξίας"
        under_score = round(under_sig * w.undervaluation / total_w * 100, 1)
    else:
        # No hedonic fit for this area: the real scorer falls back to €/m²-vs-median,
        # which the UI can't decompose here (it lacks the market medians). Show "—"
        # rather than a misleading 0 that wouldn't reconcile with the total score.
        under_value = "μέσω €/τ.μ. (εναλλακτικά)"
        # Keep the column numeric (None → blank cell). A "—" string here made the whole
        # "Score" column object-dtype, which Streamlit/pyarrow can't serialise under the
        # NumberColumn config — the breakdown table then fell back to unformatted text.
        under_score = None

    rows = [
        {
            "Κριτήριο": "Υποτίμηση",
            "Τιμή": under_value,
            "Πόντοι": under_score,
            "Μέγιστο": round(w.undervaluation / total_w * 100, 1),
        },
        {
            "Κριτήριο": "Μικτή απόδοση",
            "Τιμή": f"{gy*100:.1f}%" if gy else "—",
            "Πόντοι": round(yield_sig * w.gross_yield / total_w * 100, 1),
            "Μέγιστο": round(w.gross_yield / total_w * 100, 1),
        },
        {
            "Κριτήριο": "Παλαιότητα (έτος κατασκ./ανακ.)",
            "Τιμή": str(built) if built else "—",
            "Πόντοι": round(new_sig * w.newness / total_w * 100, 1),
            "Μέγιστο": round(w.newness / total_w * 100, 1),
        },
        {
            "Κριτήριο": "Ενεργειακή κλάση",
            "Τιμή": d.get("energy_class") or "—",
            "Πόντοι": round(energy_sig * w.energy_class / total_w * 100, 1),
            "Μέγιστο": round(w.energy_class / total_w * 100, 1),
        },
        {
            "Κριτήριο": "Μείωση τιμής",
            "Τιμή": f"−{(fp-cp)/fp*100:.0f}%" if (fp and cp < fp) else "καμία",
            "Πόντοι": round(drop_sig * w.price_drop / total_w * 100, 1),
            "Μέγιστο": round(w.price_drop / total_w * 100, 1),
        },
        {
            "Κριτήριο": "Ήδη νοικιασμένο",
            "Τιμή": "✅ ναι" if d.get("is_currently_rented") else "✗ όχι",
            "Πόντοι": round(rented_sig * w.is_currently_rented / total_w * 100, 1),
            "Μέγιστο": round(w.is_currently_rented / total_w * 100, 1),
        },
        {
            "Κριτήριο": "Ιδιώτης πωλητής",
            "Τιμή": "✅ ναι" if d.get("is_private_seller") else "✗ όχι",
            "Πόντοι": round(private_sig * w.is_private_seller / total_w * 100, 1),
            "Μέγιστο": round(w.is_private_seller / total_w * 100, 1),
        },
    ]
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "Πόντοι": st.column_config.NumberColumn("Πόντοι", format="%.1f"),
            "Μέγιστο": st.column_config.NumberColumn("Μέγιστο", format="%.1f"),
        },
    )
    # The final score is scaled down for energy-inefficient stock (EU-EPBD liability), so
    # the weighted rows above don't tell the whole story — surface that adjustment.
    mult = energy_liability_multiplier(d.get("energy_class"), ref)
    if mult < 0.999:
        st.warning(
            f"⚠️ **Προσαρμογή ενεργειακού κινδύνου: ×{mult:.2f}** — η κλάση "
            f"{d.get('energy_class') or '?'} υπόκειται σε υποχρεώσεις ανακαίνισης EPBD, άρα "
            f"το τελικό σκορ είναι ~{(1 - mult) * 100:.0f}% χαμηλότερο από το άθροισμα."
        )
    st.caption(
        "Η υποτίμηση συγκρίνει τη ζητούμενη τιμή με την εκτιμώμενη αξία βάσει εμβαδού, "
        "ορόφου, παλαιότητας, ενεργειακής κλάσης, απόστασης από μετρό και περιοχής — "
        "εντοπίζει πραγματική λάθος τιμολόγηση, όχι απλώς ένα φθηνό αλλά κατώτερο σπίτι. "
        "Χρειάζεται ≥ 25 συγκρίσιμες· αλλιώς συγκρίνει το €/τ.μ. με τη διάμεσο περιοχής."
    )


def _fair_value_block(d: dict) -> None:
    """Asking price vs the model's fair value, shown WITH a ±1σ range so the estimate is
    never presented as more precise than the fit supports. Only calls it 'undervalued'
    when the discount exceeds the model's own noise band."""
    fair = d.get("predicted_price")
    gap = d.get("value_gap_pct")
    if not fair or gap is None:
        return
    v = get_valuation_summary()
    # Use THIS listing's submarket band (fall back to the widest overall band).
    area_info = v.get("areas", {}).get(d.get("search_area") or "", {})
    sigma = area_info.get("residual_std") or v.get("overall", {}).get("residual_std") or 0.0
    area_confident = area_info.get("is_confident", v.get("overall", {}).get("is_confident", False))
    lo = int(round(fair * pow(2.718281828, -sigma)))
    hi = int(round(fair * pow(2.718281828, sigma)))
    ask = d.get("price", 0)

    st.markdown("#### 💰 Εκτιμώμενη αξία έναντι ζητούμενης")
    cols = st.columns(3)
    cols[0].metric("Ζητούμενη", fmt.euro(ask))
    cols[1].metric("Εκτιμώμενη αξία", fmt.euro(fair), delta=f"{gap*100:+.0f}% έναντι ζητούμενης")
    cols[2].metric("Εύρος αξίας (±1σ)", f"{fmt.euro(lo)} – {fmt.euro(hi)}")

    # Only a discount BEYOND the model's noise earns a confident "undervalued" call.
    beyond_noise = ask < lo
    if gap > 0 and beyond_noise and area_confident:
        st.success(
            "Τιμή **κάτω** από το εύρος αξίας του μοντέλου — πραγματική ένδειξη "
            "υποτίμησης, όχι απλώς φθηνό σπίτι."
        )
    elif gap > 0:
        st.caption(
            "Τιμή κάτω από την εκτίμηση, αλλά *μέσα* στο εύρος αβεβαιότητας του μοντέλου — "
            "ενδεικτικό, όχι οριστικό. Επιβεβαίωσε την αγγελία πριν κινηθείς."
        )
    elif ask > hi:
        st.warning("Τιμή **πάνω** από το εύρος αξίας — φαίνεται ακριβό για τα χαρακτηριστικά του.")


def _net_return_and_financing(d: dict, lid: int) -> None:
    """Net yield after Greek buying + operating costs, and a mortgage/cash-on-cash model.

    All inputs are UI-editable assumptions (nothing is stored); the score/thesis are
    unchanged — this is analysis layered on top of the listing's own figures.
    """
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not monthly:
        st.markdown("#### 💶 Καθαρή απόδοση")
        st.caption("_Χρειάζεται ενοίκιο για την καθαρή απόδοση — δεν βρέθηκε ούτε εκτιμήθηκε._")
        return
    annual = monthly * 12
    price = d["price"]
    area = d.get("area_m2")
    private = bool(d.get("is_private_seller"))

    st.markdown("#### 💶 Καθαρή απόδοση (μετά από κόστη αγοράς & λειτουργίας)")
    with st.expander("⚙️ Παραδοχές κόστους — προσάρμοσέ τες στην περίπτωσή σου"):
        c = st.columns(3)
        vacancy = c[0].number_input("Κενότητα %", 0.0, 30.0, 5.0, 0.5, key=f"vac-{lid}") / 100
        maint = c[1].number_input("Συντήρηση % ενοικίου", 0.0, 30.0, 8.0, 0.5, key=f"maint-{lid}")
        enfia = c[2].number_input("ΕΝΦΙΑ €/τ.μ./έτος", 0.0, 20.0, 4.0, 0.5, key=f"enfia-{lid}")
        c2 = st.columns(3)
        mgmt = c2[0].number_input("Διαχείριση % ενοικίου", 0.0, 20.0, 0.0, 0.5, key=f"mgmt-{lid}")
        ins = c2[1].number_input("Ασφάλιση % αξίας/έτος", 0.0, 2.0, 0.1, 0.05, key=f"ins-{lid}")
    a = finance.CostAssumptions(
        vacancy_rate=vacancy,
        maintenance_pct_of_rent=maint / 100,
        enfia_eur_per_m2_year=enfia,
        mgmt_pct_of_rent=mgmt / 100,
        insurance_pct_of_value_year=ins / 100,
    )
    ny = finance.net_yield(price, annual, area, private, a)
    noi = finance.net_operating_income(annual, price, area, a)
    acq = finance.acquisition_costs(price, private, a)
    nc = st.columns(4)
    nc[0].metric("Καθαρή απόδοση", fmt.pct(ny), help="Καθαρό έσοδο ÷ (τιμή + κόστη αγοράς)")
    nc[1].metric("Μικτή απόδοση", fmt.pct(d.get("gross_yield")))
    nc[2].metric(
        "Καθαρό έσοδο/έτος",
        fmt.euro(noi),
        help="Ενοίκιο μετά από κενότητα, διαχείριση, συντήρηση, φόρους",
    )
    nc[3].metric(
        "Κόστη αγοράς",
        fmt.euro(acq),
        help="Φόρος μεταβίβασης, συμβολαιογράφος, δικηγόρος" + ("" if private else ", μεσίτης"),
    )

    st.markdown("#### 🏦 Χρηματοδότηση (στεγαστικό & απόδοση ιδίων κεφαλαίων)")
    fc = st.columns(3)
    deposit = fc[0].slider("Προκαταβολή %", 10, 100, 30, key=f"dep-{lid}") / 100
    rate = fc[1].slider("Επιτόκιο %", 0.0, 10.0, 4.0, 0.1, key=f"rate-{lid}") / 100
    years = fc[2].slider("Διάρκεια (έτη)", 5, 40, 25, key=f"term-{lid}")
    lev = finance.leverage_summary(price, annual, area, private, deposit, rate, years, a)
    if lev:
        lc = st.columns(4)
        lc[0].metric("Μηνιαία δόση", fmt.euro(lev["monthly_payment"]))
        lc[1].metric(
            "Ίδια κεφάλαια",
            fmt.euro(lev["cash_invested"]),
            help="Προκαταβολή + κόστη αγοράς",
        )
        lc[2].metric("Ταμειακή ροή/έτος μετά τη δόση", fmt.euro(lev["annual_cashflow_after_debt"]))
        lc[3].metric(
            "Απόδοση ιδίων κεφ.",
            fmt.pct(lev["cash_on_cash"]),
            help="Ετήσια ταμειακή ροή ÷ ίδια κεφάλαια",
        )


def _comparables(d: dict, listings: list[dict]) -> None:
    """Similar active listings in the same neighborhood, with a €/m² delta vs this one."""
    rows = comps.find_comparables(d, listings)
    # Fall back to the softer, tested comps panel so the section is never empty just because
    # nothing sat inside the strict tolerance bands.
    if not rows:
        rows = comps_panel.comparable_listings(d, listings, n=6)
    if not rows:
        st.caption("Δεν υπάρχουν ακόμα συγκρίσιμες ενεργές αγγελίες σε αυτή τη γειτονιά.")
        return
    records = [
        {
            "Τιμή": c.get("price"),
            "€/τ.μ.": c.get("price_per_m2"),
            "Εμβαδόν": c.get("area_m2"),
            "Όροφος": c.get("floor"),
            "Διαφορά €/τ.μ.": c.get("ppm2_delta_pct"),
            "Σκορ": round(c["score"], 0) if c.get("score") is not None else None,
            "Σύνδεσμος": c.get("url"),
        }
        for c in rows
    ]
    st.dataframe(
        pd.DataFrame(records),
        width="stretch",
        hide_index=True,
        column_config={
            "Τιμή": st.column_config.NumberColumn("Τιμή", format="€%d"),
            "€/τ.μ.": st.column_config.NumberColumn("€/τ.μ.", format="€%.0f"),
            "Εμβαδόν": st.column_config.NumberColumn("Εμβαδόν", format="%.0f τ.μ."),
            "Όροφος": st.column_config.NumberColumn("Όροφος", format="%.0f"),
            "Διαφορά €/τ.μ.": st.column_config.NumberColumn(
                "Διαφορά €/τ.μ.",
                help="Αρνητικό = φθηνότερο ανά τ.μ. από αυτή την αγγελία",
                format="%+.0f%%",
            ),
            "Σκορ": st.column_config.NumberColumn("Σκορ", format="%.0f"),
            "Σύνδεσμος": st.column_config.LinkColumn("Σύνδεσμος", display_text="άνοιγμα ↗"),
        },
    )
    st.caption("Ίδια γειτονιά, ±25% εμβαδόν και ±30% τιμή, ταξινομημένα κατά εγγύτητα €/τ.μ.")


def _acquisition_block(d: dict) -> None:
    """Total cash to actually buy — sticker price is not the real cost. Greek purchase
    carries transfer tax, notary, land registry, legal and (unless private) agent fees."""
    price = d.get("price")
    if not price:
        return
    private = bool(d.get("is_private_seller"))
    ac = acquisition.acquisition_costs(price, agent_fee_pct=0.0 if private else 0.0248)
    st.markdown("#### 🧾 Συνολικό κόστος αγοράς")
    c = st.columns(4)
    c[0].metric("Τιμή αγγελίας", fmt.euro(ac["price"]))
    c[1].metric(
        "Έξοδα & φόροι",
        fmt.euro(ac["total_fees"]),
        help="Φόρος μεταβίβασης, συμβολαιογράφος, κτηματολόγιο, δικηγόρος, μεσίτης",
    )
    c[2].metric("Συνολικό ποσό", fmt.euro(ac["total_cash"]))
    c[3].metric("Έξοδα % τιμής", f"{ac['fees_pct_of_price'] * 100:.1f}%")
    st.caption(
        f"Φόρος μεταβίβασης {fmt.euro(ac['transfer_tax'])} · "
        f"συμβολαιογράφος {fmt.euro(ac['notary'])} · "
        f"κτηματολόγιο {fmt.euro(ac['land_registry'])} · δικηγόρος {fmt.euro(ac['legal'])} · "
        f"μεσίτης {fmt.euro(ac['agent'])}"
        + ("  _(ιδιώτης πωλητής — χωρίς μεσιτική αμοιβή)_" if private else "")
    )


def _investor_metrics_block(d: dict) -> None:
    """The recognized metrics an investor scans for by name — cap rate, GRM, DSCR,
    break-even occupancy — on the same Greek cost model as the net yield above."""
    price = d.get("price")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not price or not monthly:
        return
    from scout import metrics as _m

    mm = _m.investor_metrics(
        price, monthly * 12, d.get("area_m2"), is_private_seller=bool(d.get("is_private_seller"))
    )
    v = mm["verdicts"]
    emoji = {"good": "🟢", "ok": "🟡", "weak": "🔴", None: "⚪"}

    def cell(label, val, key, fmt_s):
        shown = fmt_s.format(val) if val is not None else "—"
        return f"{emoji[v[key]]} **{label}:** {shown}"

    st.markdown("#### 📐 Επενδυτικοί δείκτες")
    c = st.columns(4)
    c[0].markdown(cell("Cap rate", mm["cap_rate"], "cap_rate", "{:.1%}"))
    c[1].markdown(cell("GRM", mm["grm"], "grm", "{:.0f}×"))
    c[2].markdown(cell("DSCR", mm["dscr"], "dscr", "{:.2f}"))
    c[3].markdown(
        cell("Νεκρό σημείο πληρότ.", mm["break_even_occupancy"], "break_even_occupancy", "{:.0%}")
    )
    est = " Το ενοίκιο είναι εκτίμηση." if d.get("rent_estimated") else ""
    st.caption(
        "Βαθμονομημένο για την Αθήνα (cap rate ≥4,5%, GRM ≤22, DSCR ≥1,2, νεκρό σημείο ≤80% "
        "= καλό). Δεν χρησιμοποιούμε αμερικανικούς κανόνες όπως ο «κανόνας 1%» — με αποδόσεις "
        "~5% στην Αθήνα θα απέρριπταν κάθε διαμέρισμα." + est
    )


def _scorecard_block(d: dict) -> None:
    """Transparent Athens-calibrated deal scorecard — every check, its points, and why,
    so the grade isn't a black box."""
    sc = deal_scorecard.scorecard(d)
    if not sc.get("checks"):
        return
    color = {"Strong": "🟢", "Fair": "🟡", "Pass": "🔴"}
    verdict = VERDICT_GR.get(sc["verdict"], sc["verdict"])
    st.markdown(f"#### 🧮 Αξιολόγηση ευκαιρίας — {color.get(sc['verdict'], '')} {verdict}")
    st.caption(
        f"{sc['points']}/{sc['max_points']} πόντοι ({sc['pct']:.0f}%). "
        "Βαθμονομημένο για την Αθήνα."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Έλεγχος": c["label"],
                    "Πόντοι": f"{c['points']}/{c['max_points']}",
                    "Σημείωση": c["note"],
                }
                for c in sc["checks"]
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def _projection_block(d: dict) -> None:
    """5-year total-return projection — the four pillars (cashflow, appreciation, debt
    paydown, equity). Appreciation is a labelled assumption, not a forecast."""
    price = d.get("price")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not price or not monthly:
        return
    pr = projection.five_year_projection(
        price, monthly * 12, d.get("area_m2"), is_private_seller=bool(d.get("is_private_seller"))
    )
    if not pr:
        return
    t = pr["total"]
    st.markdown("#### 📈 Πρόβλεψη 5ετίας")
    c = st.columns(4)
    c[0].metric("Σωρευτική ταμειακή ροή", fmt.euro(t["cumulative_cash_flow"]))
    c[1].metric("Υπεραξία (2%/έτος)", fmt.euro(t["property_appreciation"]))
    c[2].metric("Αποπληρωμή δανείου", fmt.euro(t["debt_paydown"]))
    c[3].metric("Συνολική απόδοση ιδίων", f"{t['total_return_pct'] * 100:.0f}%")
    st.caption(
        "Οι τέσσερις πηγές απόδοσης σε 5ετή διακράτηση (30% προκαταβολή, 25ετές δάνειο @4,5%). "
        "Η υπεραξία είναι ΣΥΝΤΗΡΗΤΙΚΗ παραδοχή 2%/έτος, όχι πρόβλεψη."
    )


def _sensitivity_block(d: dict) -> None:
    """How the return holds up if rates rise or the flat sits empty — the stress test an
    investor actually underwrites on."""
    price = d.get("price")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not price or not monthly:
        return
    grid = sensitivity.sensitivity_grid(price, monthly * 12)
    if not grid.get("net_yield"):
        return
    st.markdown("#### 🎛️ Ευαισθησία επιτοκίου × κενότητας")
    rates = grid["rates"]
    vac = grid["vacancies"]
    ny = pd.DataFrame(
        grid["net_yield"],
        index=[f"επιτόκιο {r * 100:.0f}%" for r in rates],
        columns=[f"κενό {v * 100:.0f}%" for v in vac],
    )
    st.caption(
        "Καθαρή απόδοση (μετά από κενότητα, κόστη, τόκους) — 30% προκαταβολή, 25ετές δάνειο."
    )
    st.dataframe(ny.style.format("{:.1%}"), width="stretch")

    annual = monthly * 12
    with st.expander("Περισσότερα σενάρια — αλλαγές ενοικίου & τιμής αγοράς"):
        rs = sensitivity.rent_sensitivity(price, annual)
        if rs.get("net_yield"):
            rdf = pd.DataFrame(
                {
                    "Αλλαγή ενοικίου": [f"{s * 100:+.0f}%" for s in rs["steps"]],
                    "Καθαρή απόδοση": rs["net_yield"],
                    "Ταμειακή ροή/μήνα": rs["cashflow_monthly"],
                }
            )
            st.markdown("**Αν αλλάξει το ενοίκιο**")
            st.dataframe(
                rdf.style.format({"Καθαρή απόδοση": "{:.1%}", "Ταμειακή ροή/μήνα": "{:.0f} €"}),
                width="stretch",
                hide_index=True,
            )
        ps = sensitivity.price_sensitivity(price, annual)
        if ps.get("net_yield"):
            pdf = pd.DataFrame(
                {
                    "Αλλαγή τιμής": [f"{s * 100:+.0f}%" for s in ps["steps"]],
                    "Καθαρή απόδοση": ps["net_yield"],
                    "Απόδοση ιδίων κεφ.": ps["cash_on_cash"],
                }
            )
            st.markdown("**Αν διαπραγματευτείς την τιμή**")
            st.dataframe(
                pdf.style.format({"Καθαρή απόδοση": "{:.1%}", "Απόδοση ιδίων κεφ.": "{:.1%}"}),
                width="stretch",
                hide_index=True,
            )
    if d.get("rent_estimated"):
        st.caption(
            "_Το ενοίκιο είναι εκτίμηση (χωρίς τοπικό συγκρίσιμο) — τα νούμερα είναι ενδεικτικά._"
        )


# ---- pages -----------------------------------------------------------------


def _coverage_panel(listings: list[dict]) -> None:
    """Honest per-region coverage: how many listings, how complete, how fresh. Trust comes
    from showing exactly what we have and what's still shallow, not hiding the gaps."""
    from collections import defaultdict

    if not listings:
        return
    by_region: dict[str, list[dict]] = defaultdict(list)
    for d in listings:
        by_region[d.get("region") or "—"].append(d)
    total = len(listings)
    complete = sum(1 for d in listings if d.get("data_complete"))
    with st.expander(
        (
            f"📦 Κάλυψη — {total:,} αγγελίες, {complete / total * 100:.0f}% με πλήρη στοιχεία"
            if total
            else "📦 Κάλυψη"
        ),
        expanded=False,
    ):
        rows = []
        for region, ds in sorted(by_region.items(), key=lambda kv: -len(kv[1])):
            n = len(ds)
            comp = sum(1 for d in ds if d.get("data_complete"))
            en = sum(1 for d in ds if (d.get("energy_class") or "").strip())
            exact = sum(1 for d in ds if d.get("location_precision") == "exact")
            newest = max((d["last_seen"] for d in ds if d.get("last_seen")), default=None)
            rows.append(
                {
                    "Περιοχή": region,
                    "Αγγελίες": n,
                    "Πλήρη στοιχεία": f"{comp / n * 100:.0f}%" if n else "—",
                    "Με ενεργ. κλάση": f"{en / n * 100:.0f}%" if n else "—",
                    "Ακριβής θέση": f"{exact / n * 100:.0f}%" if n else "—",
                    "Ενημέρωση": newest.strftime("%d/%m/%Y %H:%M") if newest else "—",
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption(
            "Τα πλήρη στοιχεία συμπληρώνονται σταδιακά από την αναλυτική σάρωση· μέχρι τότε "
            "οι αγγελίες φέρουν την ένδειξη *ελλιπή στοιχεία*."
        )


def page_opportunities(listings: list[dict]) -> None:
    st.subheader("Ευκαιρίες")
    _valuation_banner()
    _coverage_panel(_eligible(listings))

    if not listings:
        st.info(
            "Δεν υπάρχουν αγγελίες ακόμα. Πάτα **🔄 Φρέσκα δεδομένα** στο πλάι ή περίμενε "
            "την ημερήσια ενημέρωση."
        )
        return

    eligible = _eligible(listings)

    # Never blank: if the hard filters reject everything, still show the real data
    # with the reason each was filtered, so the user always sees what was scraped.
    if not eligible:
        st.warning(
            f"Βρέθηκαν **{len(listings)}** αγγελίες, αλλά καμία δεν περνά τα τρέχοντα "
            "αυστηρά φίλτρα. Εμφανίζονται όλες παρακάτω με τον λόγο αποκλεισμού — "
            "χαλάρωσε τους κανόνες της στρατηγικής για να δεις περισσότερες."
        )
        rows = sorted(listings, key=lambda d: (d["price_per_m2"] or float("inf")))
        _table(rows, show_reason=True)
        return

    # Sidebar filters — defaults include everything so nothing hides silently.
    with st.sidebar:
        st.subheader("Φίλτρα")
        # Keep the everyday filters visible; tuck the rest into an expander so the sidebar
        # isn't a wall of ~15 controls (the #1 "hard to use" complaint).
        present_regions = [r for r in REGIONS if any(d.get("region") == r for d in eligible)]
        chosen_regions = (
            st.multiselect("Περιοχή", present_regions, default=present_regions)
            if present_regions
            else []
        )
        prices = [d["price"] for d in eligible]
        pmin, pmax = min(prices), max(prices)
        price_range = (
            st.slider("Τιμή (€)", pmin, pmax, (pmin, pmax), step=5000)
            if pmin < pmax
            else (pmin, pmax)
        )
        min_vs_market = st.slider(
            "Μόνο καλή τιμή — φθηνότερο από …% των παρόμοιων",
            0,
            95,
            0,
            step=5,
            help="Θέση στην αγορά έναντι συγκρίσιμων ενεργών αγγελιών (ίδια περιοχή, ±30% "
            "εμβαδόν). 0 = όλες.",
        )
        short_let_filter = st.selectbox(
            "🏠 Βραχυχρόνια μίσθωση (Airbnb)",
            [SL_ANY, SL_ALLOWED, SL_FROZEN],
            index=0,
            help="Πάγωμα = δεν εκδίδεται νέα άδεια Airbnb (πάγωμα περιοχών Αθήνας 2026).",
        )

        with st.expander("⚙️ Περισσότερα φίλτρα"):
            near_metro_only = st.checkbox(
                "🚇 Μόνο κοντά σε σταθμό μετρό",
                value=False,
                help="Μόνο αγγελίες εντός της απόστασης από μετρό παρακάτω (Γραμμή 2/3).",
            )
            income = st.number_input(
                "Μηνιαίο καθαρό εισόδημα (€) — 0 = ανενεργό",
                min_value=0,
                value=0,
                step=100,
                help="Μόνο σπίτια που καλύπτει 25ετές στεγαστικό με ~30% προκαταβολή.",
            )
            max_afford = _max_affordable_price(income)
            if max_afford:
                st.caption(
                    f"≈ προσιτό έως **{fmt.euro(max_afford)}** (35% εισοδήματος, ~4,5%, 25 έτη)."
                )
            present_strats = sorted({t for d in eligible for t in (d.get("strategy_tags") or [])})
            strat_filter = (
                st.multiselect(
                    "Στρατηγική",
                    present_strats,
                    default=[],
                    format_func=strategy_label,
                    help=" · ".join(STRATEGY_LABELS.values()),
                )
                if present_strats
                else []
            )
            subsidy_only = st.checkbox(
                "🔧 Μόνο υποψήφια για ενεργειακή επιδότηση",
                value=False,
                help="Ενεργειακή κλάση Γ ή χαμηλότερη — επιλέξιμο για το Εξοικονομώ 2026.",
            )
            areas = [d["area_m2"] for d in eligible]
            amin, amax = int(min(areas)), int(max(areas)) + 1
            area_range = (
                st.slider("Εμβαδόν (τ.μ.)", amin, amax, (amin, amax))
                if amin < amax
                else (amin, amax)
            )
            min_yield = st.slider("Ελάχ. μικτή απόδοση (%)", 0.0, 12.0, 0.0, step=0.5) / 100
            min_year = st.slider("Κατασκευή/ανακαίνιση μετά το", 1950, 2025, 1950, step=5)
            new_only = st.checkbox("Μόνο νεόδμητα (≥ 2010)", value=False)
            include_unknown_year = st.checkbox("Και με άγνωστο έτος κατασκευής", value=True)
            max_metro = st.slider("Μέγ. απόσταση από μετρό (m)", 0, 5000, 5000, step=50)
            include_unknown_metro = st.checkbox("Και με άγνωστη απόσταση από μετρό", value=True)

    def _built_year(d: dict) -> int | None:
        return d.get("renovated_year") or d.get("year_built")

    def keep(d: dict) -> bool:
        if chosen_regions and d.get("region") not in chosen_regions:
            return False
        if not (price_range[0] <= d["price"] <= price_range[1]):
            return False
        if max_afford is not None and d["price"] > max_afford:
            return False
        if strat_filter and not (set(strat_filter) & set(d.get("strategy_tags") or [])):
            return False
        if short_let_filter != SL_ANY:
            status = str_legality(_area_key(d)).status
            if short_let_filter == SL_ALLOWED and status == "FROZEN":
                return False
            if short_let_filter == SL_FROZEN and status != "FROZEN":
                return False
        if (
            subsidy_only
            and not renovation_subsidy(d.get("energy_class"), d.get("year_built")).candidate
        ):
            return False
        if not (area_range[0] <= d["area_m2"] <= area_range[1]):
            return False
        if (d["gross_yield"] or 0) < min_yield:
            return False
        if min_vs_market > 0:
            vp = d.get("value_percentile")
            if vp is None or vp * 100 < min_vs_market:
                return False
        yr = _built_year(d)
        effective_min = max(min_year, 2010) if new_only else min_year
        if yr is None:
            if new_only or not include_unknown_year:
                return False
        elif yr < effective_min:
            return False
        if d["metro_distance_m"] is None:
            # "Near metro only" is a hard walk-to-metro requirement: an unlocatable
            # listing can't prove it qualifies, so it's excluded when the toggle is on.
            return include_unknown_metro and not near_metro_only
        limit = (
            min(max_metro, get_strategy().hard_filters.max_metro_distance_m)
            if near_metro_only
            else max_metro
        )
        return d["metro_distance_m"] <= limit

    # Let the buyer rank by the signal they care about — not just the quality score. All
    # of these are real numbers already in the data. Every sort puts BUY verdicts ahead of
    # WATCH ahead of PASS first: a verified BUY at score 70 beats an unverifiable WATCH at
    # 75 — the verdict already encodes how much of that score we can stand behind.
    _verdict_rank = {"BUY": 2, "WATCH": 1, "PASS": 0}
    sort_opts = {
        "Καλύτερο συνολικά (σκορ)": lambda d: (d["score"], d.get("data_complete", False)),
        "Φθηνότερο έναντι παρόμοιων": lambda d: (d.get("value_percentile") or -1),
        "Πιο διαπραγματεύσιμο (μέρες στην αγορά)": lambda d: (d.get("days_on_market") or 0),
        "Υψηλότερη καθαρή απόδοση": lambda d: (d.get("net_yield") or -1),
    }
    scol, fcol = st.columns([4, 1])
    with scol:
        sort_by = st.radio(
            "Ταξινόμηση", list(sort_opts), horizontal=True, label_visibility="collapsed"
        )
    with fcol:
        buys_only = st.checkbox(
            "🟢 Μόνο αγορά", value=False, help="Μόνο επιβεβαιωμένες προτάσεις αγοράς"
        )
    inner = sort_opts[sort_by]
    rows = sorted(
        [d for d in eligible if keep(d) and (not buys_only or d.get("rec_verdict") == "BUY")],
        # Data-quality suspects (whole building priced as a flat, future year, off-by-10x
        # €/m²) sink below every clean listing regardless of score — they can't top the rank.
        key=lambda d: (
            not d.get("is_suspect"),
            _verdict_rank.get(d.get("rec_verdict"), 0),
            inner(d),
        ),
        reverse=True,
    )

    n_buys = sum(1 for d in rows if d.get("rec_verdict") == "BUY")
    st.markdown(
        f"**{len(rows)}** αγγελίες ταιριάζουν στα φίλτρα (από {len(eligible)}) · "
        f"**{n_buys}** με σύσταση «Αγορά»"
    )
    if rows:
        # Cap the card grid to the top N by score — rendering all ~9k cards ships a
        # multi-megabyte DOM that janks the browser. The full set stays in the table/CSV.
        grid_cap = 60
        components.listing_grid(rows[:grid_cap])
        if len(rows) > grid_cap:
            st.caption(
                f"Εμφανίζονται οι πρώτες {grid_cap} κάρτες ({sort_by.split(' (')[0].lower()}). "
                "Η πλήρης λίστα είναι στον πίνακα παρακάτω."
            )
        with st.expander("Πίνακας (ταξινόμηση / εξαγωγή)"):
            _table(rows)
    else:
        st.info("Καμία αγγελία δεν ταιριάζει στα φίλτρα. Διεύρυνέ τα στο πλάι.")


def page_today(listings: list[dict]) -> None:
    st.subheader("🗞️ Ημερήσια ενημέρωση")
    elig = _eligible(listings)
    cap = 30

    new = sorted([d for d in elig if d["is_new"]], key=lambda d: d["score"], reverse=True)
    new_buys = [d for d in new if d.get("rec_verdict") == "BUY"]
    try:
        drops = get_recent_price_drops(24)
    except Exception:
        drops = []

    # Counts strip — the "what changed since yesterday" a subscriber opens the tool for.
    c = st.columns(3)
    c[0].metric("🟢 Νέες προτάσεις αγοράς (24 ώρες)", len(new_buys))
    c[1].metric("💸 Μειώσεις τιμής (24 ώρες)", len(drops))
    c[2].metric("🆕 Νέες αγγελίες (24 ώρες)", len(new))
    # Honest framing when the 24h feed is empty: the change-signals (new listings, price
    # drops, motivated sellers) are BUILT by comparing daily snapshots — they only appear
    # once the pipeline has run on consecutive days. Show that instead of three bare zeros
    # that read as "broken". The always-useful briefs below still make the page actionable.
    if not new_buys and not drops and not new:
        st.info(
            "Δεν υπάρχουν ακόμα αλλαγές 24ώρου. Οι ημερήσιες αλλαγές (νέες αγγελίες, "
            "μειώσεις τιμής, πρόθυμοι πωλητές) προκύπτουν συγκρίνοντας στιγμιότυπα ημερών και "
            "συμπληρώνονται καθώς τρέχει η ενημέρωση. Στο μεταξύ, οι **καλύτερες τρέχουσες "
            "ευκαιρίες** είναι παρακάτω."
        )
    st.divider()

    # Lead with the actual decisions: BUY-verdict listings that appeared today. This is the
    # feed a paying user wants — not "here's everything new", but "here's what to act on".
    if new_buys:
        st.markdown("#### 🟢 Νέες προτάσεις αγοράς σήμερα")
        components.listing_grid(new_buys[:cap])
        st.divider()

    # Price cuts today — the classic motivated-seller trigger, straight from price history.
    if drops:
        st.markdown("#### 💸 Μειώσεις τιμής το τελευταίο 24ωρο")
        for d in drops:
            # Surface the cut as a lead strategy pill (the recommendation line owns the
            # thesis slot, so a deal_thesis here would never render). €old→€new is the
            # actionable bit — a fresh cut is the classic motivated-seller trigger.
            pill = f"💸 −{d['drop_pct'] * 100:.0f}% σήμερα ({fmt.euro(d['new_price'])})"
            d["strategy_tags"] = [pill, *(d.get("strategy_tags") or [])]
        components.listing_grid(sorted(drops, key=lambda d: d["drop_pct"], reverse=True)[:cap])
        st.divider()

    if new and not new_buys:
        st.markdown(
            f"#### 🆕 {len(new)} νέες το τελευταίο 24ωρο " "(καμία δεν πέρασε το κριτήριο «Αγορά»)"
        )
        components.listing_grid(new[:cap])
        st.divider()

    # Always-useful daily brief from the real signals: the best value, the most negotiable,
    # and the highest yield right now — so the landing view is actionable even between runs.
    briefs = [
        (
            "💰 Φθηνότερα έναντι παρόμοιων",
            lambda d: d.get("value_percentile") or -1,
            lambda d: (d.get("value_percentile") or 0) >= 0.90,
        ),
        (
            "⏳ Πιο διαπραγματεύσιμα (περισσότερο στην αγορά)",
            lambda d: d.get("days_on_market") or 0,
            lambda d: (d.get("days_on_market") or 0) > 90,
        ),
        (
            "📈 Υψηλότερη καθαρή απόδοση",
            lambda d: d.get("net_yield") or -1,
            lambda d: d.get("net_yield") is not None,
        ),
    ]
    for title, keyfn, pred in briefs:
        picks = sorted([d for d in elig if pred(d)], key=keyfn, reverse=True)[:4]
        if picks:
            st.markdown(f"#### {title}")
            components.listing_grid(picks)
    if not new and not drops and not any(any(pred(d) for d in elig) for _, _, pred in briefs):
        st.info("Δεν υπάρχουν αγγελίες ακόμα — ανανέωσε τα δεδομένα από το πλάι.")


MAP_YEAR_MIN = 1960  # the year slider's low end means "any year"


def _map_area_group(d: dict) -> str:
    """Municipality part of the neighbourhood: "Χολαργός (Τσακός)" -> "Χολαργός"."""
    name = d.get("neighborhood") or d.get("search_area") or "Άγνωστη περιοχή"
    return name.split(" (")[0].strip()


def _built_year(d: dict) -> int | None:
    yb = d.get("year_built")
    if yb:
        return int(yb)
    age = d.get("building_age")
    return datetime.utcnow().year - age if age is not None else None


def _map_hidden(d: dict) -> bool:
    """Never drawn: failed the hard filters, suspect data, or a flat that is still unfinished."""
    return bool(d["excluded"] or d.get("is_suspect") or d.get("is_unfinished"))


def _map_filter(
    listings: list[dict],
    *,
    areas: list[str],
    price_max: int | None,
    min_year: int | None,
) -> list[dict]:
    """The map's three filters. Only active listings that are not hidden (see _map_hidden).
    A flat with no known year is dropped when a minimum year is set (we can't vouch for it)."""
    wanted = set(areas)
    out = []
    for d in listings:
        if _map_hidden(d) or not d.get("is_fresh", True):
            continue
        if wanted and _map_area_group(d) not in wanted:
            continue
        p = d.get("price")
        if price_max is not None and p and p > price_max:
            continue
        if min_year is not None:
            yb = _built_year(d)
            if yb is None or yb < min_year:
                continue
        out.append(d)
    return out


def page_map(listings: list[dict]) -> None:
    st.subheader("Χάρτης")
    if not listings:
        st.info("Δεν υπάρχουν αγγελίες ακόμα — πάτα «Ανανέωση» πάνω.")
        return
    # One score everywhere: colours and legend use the buyer score on the cards.
    scores = buyer.buyer_scores(listings)
    listings = [{**d, "score": scores[d["id"]]} for d in listings]
    visible = [d for d in listings if not _map_hidden(d) and d.get("is_fresh", True)]
    options = [g for g, _ in Counter(_map_area_group(d) for d in visible).most_common()]
    prices = sorted(d["price"] for d in visible if d.get("price"))
    p_hi = int(-(-prices[min(len(prices) * 99 // 100, len(prices) - 1)] // 10_000) * 10_000)
    p_hi = max(p_hi if prices else 1_000_000, 50_000)

    with st.expander("Φίλτρα", expanded=False):
        areas = st.multiselect("Περιοχή", options, key="map_areas", placeholder="Όλες οι περιοχές")
        c1, c2 = st.columns(2)
        k_max = c1.slider(
            "Τιμή έως",
            min_value=50,
            max_value=p_hi // 1000,
            value=p_hi // 1000,
            step=10,
            format="%d χιλ. €",
            key="map_price",
            help="Στο τέρμα δεξιά = χωρίς όριο.",
        )
        this_year = datetime.utcnow().year
        year = c2.slider(
            "Κατασκευή από",
            min_value=MAP_YEAR_MIN,
            max_value=this_year,
            value=MAP_YEAR_MIN,
            step=5,
            key="map_year",
            help="Στο τέρμα αριστερά = χωρίς όριο. Αγγελίες χωρίς έτος κρύβονται όταν βάλεις όριο.",
        )
    matched = _map_filter(
        listings,
        areas=areas,
        price_max=None if k_max * 1000 >= p_hi else k_max * 1000,
        min_year=None if year <= MAP_YEAR_MIN else year,
    )
    shown = [d for d in matched if d.get("lat") and d.get("lng")]
    no_loc = len(matched) - len(shown)
    approx = sum(1 for d in shown if d.get("location_precision") != "exact")
    noun = "αγγελία" if len(shown) == 1 else "αγγελίες"
    st.markdown(f"**{fmt._gr_int(len(shown))} {noun} στον χάρτη**")
    exact = len(shown) - approx
    st.caption(
        f"Μόνο {fmt._gr_int(exact)} αγγελίες έχουν ακριβή θέση· οι υπόλοιπες στο κέντρο της "
        "περιοχής τους."
        if exact
        else "Καμία αγγελία δεν έχει ακριβή θέση· όλες είναι στο κέντρο της περιοχής τους."
    )
    hidden_unfinished = sum(1 for d in listings if d.get("is_unfinished"))
    unchecked = sum(1 for d in shown if not d.get("page_checked"))
    notes = []
    if hidden_unfinished:
        notes.append(f"{fmt._gr_int(hidden_unfinished)} υπό κατασκευή δεν εμφανίζονται")
    if unchecked:
        notes.append(
            f"{fmt._gr_int(unchecked)} δεν έχουν ελεγχθεί ακόμα (δεν ξέρουμε αν είναι έτοιμες)"
        )
    if no_loc:
        notes.append(f"{fmt._gr_int(no_loc)} ταιριάζουν αλλά δεν έχουν θέση")
    if notes:
        st.caption(" · ".join(notes) + ".")
    if not shown:
        st.info("Καμία αγγελία δεν ταιριάζει — χαλάρωσε την τιμή, το έτος ή την περιοχή.")
        return
    from scout import market_intel

    intel = market_intel.build(listings)
    # Same ranking as the search page's default sort, so the two pages agree.
    from scout import nl_search
    from scout.nl_search import SearchFilters

    rank = buyer.SORTS[buyer.DEFAULT_SORT]
    views = {d["id"]: buyer.buyer_view(d, intel) for d in shown}

    def _key(d: dict):
        m = nl_search.match(d, SearchFilters())
        return rank(m[0] if m else 0, views[d["id"]], d)

    if maplist is not None:  # one map, one selection, the ranked list directly under it
        maplist.render(sorted(shown, key=_key), key="map", intel=intel)
        return
    components.results_map(shown, key="map_chart", height=420)
    # The best few as the same cards as the search page (not a wide table).
    top = sorted(shown, key=_key)[:5]
    st.markdown("#### Οι 5 καλύτερες στον χάρτη")
    for d in top:
        buyer.result_card(
            d,
            views[d["id"]],
            "m",
            [("Λεπτομέρειες", buyer.open_detail, (d["id"],)), buyer._star_action(d)],
        )


@st.cache_data(ttl=300)
def get_area_liquidity() -> dict:
    """Per-area liquidity (median days-on-market before delisting + absorption) over the
    full tracked set — the exit signal. Plain dicts so Streamlit can cache it."""
    allrows = queries.load_listings(include_excluded=True, only_active=False)
    out = {}
    for area, liq in liquidity.liquidity_by_area(allrows).items():
        out[area] = {
            "median_days": liq.median_days_on_market,
            "cleared": liq.cleared,
            "absorption": liq.absorption_rate,
        }
    return out


def _scenarios_block(d: dict) -> None:
    """Downside range + the questions a buyer underwrites on: net-yield under good/bad
    assumptions, yield if they land the recommended offer, break-even rent, and payback."""
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not monthly:
        return
    annual = monthly * 12
    price, area, priv = d["price"], d.get("area_m2"), bool(d.get("is_private_seller"))
    st.markdown("#### 📉 Δυσμενή σενάρια")
    sens = investment.net_yield_sensitivity(price, annual, area, priv)
    if sens:
        c = st.columns(3)
        c[0].metric(
            "Καθαρή απόδοση — απαισιόδοξο",
            fmt.pct(sens["pessimistic"]),
            help="12% κενότητα + υψηλότερη συντήρηση",
        )
        c[1].metric("Καθαρή απόδοση — βασικό", fmt.pct(sens["base"]))
        c[2].metric(
            "Καθαρή απόδοση — αισιόδοξο",
            fmt.pct(sens["optimistic"]),
            help="2% κενότητα + ελαφριά συντήρηση",
        )
    c2 = st.columns(3)
    yoo = d.get("yield_on_offer")
    if yoo is not None:
        c2[0].metric(
            "Καθαρή απόδοση στην προτεινόμενη προσφορά",
            fmt.pct(yoo),
            help=f"αν το κλείσεις στα {fmt.euro(d.get('suggested_offer'))}",
        )
    be = investment.break_even_rent(price, area, priv)
    if be:
        c2[1].metric(
            "Ενοίκιο νεκρού σημείου",
            fmt.euro(be) + "/μήνα",
            help="κάτω από αυτό το ενοίκιο έχεις ζημία (πριν τη χρηματοδότηση)",
        )
    pb = investment.payback_years(price, annual, area, priv)
    if pb:
        c2[2].metric("Απόσβεση (χωρίς δάνειο)", f"~{pb:.0f} έτη")
    tax = investment.greek_rental_tax(annual)
    if tax:
        st.caption(
            f"🧾 Φόρος εισοδήματος από ενοίκια ≈ **{fmt.euro(tax['annual_tax'])}/έτος** "
            f"({tax['effective_rate'] * 100:.0f}% πραγματικός) — περιλαμβάνεται στα καθαρά."
        )
    reno = investment.renovation_roi(d.get("energy_class"), area, annual)
    if reno:
        st.caption(
            f"🔧 Ενεργειακή αναβάθμιση: ~{fmt.euro(reno['capex'])} κόστος → "
            f"+{fmt.euro(reno['annual_rent_uplift'])}/έτος ενοίκιο "
            f"({reno['roi_pct'] * 100:.0f}% ROI, απόσβεση ~{reno['payback_years']:.0f} έτη)."
        )
    if d.get("rent_estimated"):
        st.caption("_Το ενοίκιο είναι εκτίμηση περιοχής — τα νούμερα είναι ενδεικτικά._")


def _risk_and_context(d: dict, listings: list[dict]) -> None:
    """EPBD renovation liability, transparent price percentile, area liquidity, and a
    leverage one-liner — the decision context portals don't give."""
    st.markdown("#### 🧭 Κίνδυνοι & πλαίσιο")

    # EPBD renovation-mandate liability + indicative capex (only for a known poor class).
    flag = epbd.epbd_flag(d.get("energy_class"), d.get("area_m2"))
    if flag.at_risk:
        st.warning(f"⚠️ **Υποχρέωση EPBD** — {flag.note}")

    cols = st.columns(2)
    # Transparent, checkable value signal: cheaper per m² than X% of this municipality.
    dist = analytics.area_ppm2_distributions(listings)
    pct = analytics.ppm2_percentile_cheaper(
        d.get("price_per_m2"), dist.get(d.get("search_area"), [])
    )
    if pct is not None:
        cols[0].metric(
            "Φθηνότερο ανά τ.μ. από",
            f"{pct * 100:.0f}% της περιοχής {d.get('search_area') or ''}".rstrip(),
            help="Ποσοστό ενεργών αγγελιών του δήμου με υψηλότερο €/τ.μ.",
        )

    # Area liquidity — how fast this submarket clears (from our own tracked lifecycle).
    liq = get_area_liquidity().get(d.get("search_area"))
    if liq and liq["median_days"] is not None:
        cols[1].metric(
            "Τυπικές μέρες στην αγορά",
            f"~{liq['median_days']:.0f}",
            help=(
                f"Διάμεσος χρόνος μέχρι την απόσυρση στην περιοχή {d.get('search_area')} "
                f"({liq['cleared']} αγγελίες· απορρόφηση "
                f"{(liq['absorption'] or 0) * 100:.0f}%). Η απόσυρση θεωρείται ένδειξη πώλησης."
            ),
        )

    # Leverage: cash-on-cash at standard assumptions (a buyer tweaks them per deal).
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if monthly:
        line = finance.leverage_oneliner(
            d["price"], monthly * 12, d.get("area_m2"), bool(d.get("is_private_seller"))
        )
        if line:
            est = " _(εκτίμηση ενοικίου)_" if d.get("rent_estimated") else ""
            st.caption(f"🏦 {line}{est}")


def page_detail(listings: list[dict]) -> None:
    st.subheader("Λεπτομέρειες αγγελίας")
    wanted = st.session_state.get("detail_id")
    ranked = sorted(listings, key=lambda x: -(x.get("score") or 0))
    # A selectbox of all ~23k listings is unusably heavy: offer the top 400 plus the one a card
    # linked to and the starred ones.
    starred = buyer.watch_keys()
    chosen = {x["id"]: x for x in ranked[:400]}
    for x in listings:
        if x["id"] == wanted or shortlist.lkey(x) in starred:
            chosen[x["id"]] = x
    options = {
        f"[{x['score']:.0f}] {x['title'] or x['source_id']} · {x['id']}": x["id"]
        for x in chosen.values()
    }
    if not options:
        st.info("Δεν υπάρχουν αγγελίες.")
        return
    labels = list(options)
    index = next((i for i, lab in enumerate(labels) if options[lab] == wanted), 0)
    choice = st.selectbox("Αγγελία", labels, index=index, key=f"detail_pick_{wanted}")
    lid = options[choice]
    d = chosen[lid]

    # --- top metrics row ---
    fp = d.get("first_price")
    # Only show a delta when the price actually moved — a red "↑ 0 €" reads like a rise.
    price_delta = fmt.euro(d["price"] - fp) if fp and fp != d["price"] else None
    cols = st.columns(5)
    cols[0].metric("Τιμή", fmt.euro(d["price"]), delta=price_delta, delta_color="inverse")
    cols[1].metric("€/τ.μ.", fmt.euro_per_m2(d["price_per_m2"]))
    cols[2].metric("Μικτή απόδοση", fmt.pct(d["gross_yield"]))
    dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
    cols[3].metric("Μέρες στην αγορά", dom if dom is not None else "—")
    cols[4].metric("Σκορ", f"{d['score']:.0f} / 100")

    if d["excluded"]:
        st.error(f"Αποκλείστηκε από αυστηρό φίλτρο: {d['exclusion_reason']}")

    # Verdict up front — the answer before any deep dive.
    sc = deal_scorecard.scorecard(d)
    vic = {"Strong": "🟢", "Fair": "🟡", "Pass": "🔴"}
    vc = st.columns(5)
    vc[0].metric("Βαθμός ευκαιρίας", d.get("deal_grade") or "—")
    vc[1].metric(
        "Αξιολόγηση",
        f"{vic.get(sc['verdict'], '')} {VERDICT_GR.get(sc['verdict'], sc['verdict'])}",
    )
    vc[2].metric(
        "Καθαρή απόδοση", fmt.pct(d["net_yield"]) if d.get("net_yield") is not None else "—"
    )
    # Honest headline value signal: market-position rank among comparable ACTIVE listings
    # (no sold-price data, no pseudo-precise ±44% "discount"). The hedonic model gap is kept
    # below as a secondary, clearly-labelled estimate.
    rv = relative_value(d)
    vc[3].metric(
        "Φθηνότερο από (% παρόμοιων)",
        f"{rv.percentile * 100:.0f}%" if rv else "—",
        help="Ποσοστό συγκρίσιμων ενεργών αγγελιών (ίδια περιοχή, ±30% εμβαδόν) με "
        "υψηλότερο €/τ.μ.",
    )
    # A raw yield % means nothing without area context — 5.5% is exceptional in a prime
    # low-yield neighborhood, mediocre in a peripheral high-yield one. This ranks the yield
    # against comparable ACTIVE listings in the SAME area, instead of a flat national band.
    ry = relative_yield(d)
    vc[4].metric(
        "Υψηλότερη απόδοση από (% παρόμοιων)",
        f"{ry.percentile * 100:.0f}%" if ry else "—",
        help="Ποσοστό συγκρίσιμων ενεργών αγγελιών (ίδια περιοχή, ±30% εμβαδόν) με "
        "χαμηλότερη απόδοση.",
    )
    if d.get("strategy_tags"):
        st.write(" ".join(f"`{strategy_label(t)}`" for t in d["strategy_tags"]))
    # The recommendation — the decision, up front: verdict + concrete action + why + risks.
    from scout.recommendation import verdict_emoji, verdict_label

    rv, rh = d.get("rec_verdict"), d.get("rec_headline")
    if rv and rh:
        box = {"BUY": st.success, "WATCH": st.info, "PASS": st.error}.get(rv, st.info)
        box(f"{verdict_emoji(rv)} **{verdict_label(rv)} — {rh}**")
        rc = st.columns(2)
        if d.get("rec_rationale"):
            rc[0].markdown("**Γιατί:**\n" + "\n".join(f"- {x}" for x in d["rec_rationale"]))
        if d.get("rec_risks"):
            rc[1].markdown("**Προσοχή:**\n" + "\n".join(f"- {x}" for x in d["rec_risks"]))
    elif d.get("deal_thesis"):
        st.info(f"💡 {d['deal_thesis']}")

    _regulatory_panel(d)

    tabs = st.tabs(
        [
            "💰 Αποδόσεις",
            "🧾 Κόστη & κίνδυνοι",
            "🎛️ Ευαισθησία",
            "🧮 Σκορ & συγκρίσιμα",
            "🏗️ Χαρακτηριστικά",
        ]
    )

    with tabs[0]:
        monthly = d.get("listed_rent") or d.get("est_monthly_rent")
        if monthly:
            math_cols = st.columns(4)
            math_cols[0].metric("Εκτ. μηνιαίο ενοίκιο", fmt.euro(monthly))
            math_cols[1].metric("Ετήσιο έσοδο", fmt.euro(monthly * 12))
            math_cols[2].metric("Τιμή αγοράς", fmt.euro(d["price"]))
            math_cols[3].metric("Μικτή απόδοση", fmt.pct(d.get("gross_yield")))
            if fp and d["price"] < fp:
                drop_pct = (fp - d["price"]) / fp * 100
                st.info(
                    f"📉 Η τιμή μειώθηκε **{drop_pct:.0f}%** από {fmt.euro(fp)} σε "
                    f"{fmt.euro(d['price'])} (−{fmt.euro(fp - d['price'])})"
                )
        else:
            st.caption("_Δεν βρέθηκε ενοίκιο — η απόδοση χρησιμοποιεί προεπιλεγμένο €/τ.μ./μήνα._")
        for b in _investment_bullets(d):
            st.markdown(f"• {b}")
        _fair_value_block(d)
        _net_return_and_financing(d, lid)
        _investor_metrics_block(d)
        _projection_block(d)

    with tabs[1]:
        _acquisition_block(d)
        _risk_and_context(d, listings)
        _scenarios_block(d)

    with tabs[2]:
        _sensitivity_block(d)

    with tabs[3]:
        _scorecard_block(d)
        st.markdown("#### 📊 Ανάλυση σκορ")
        _score_breakdown(d, get_strategy())
        st.markdown("#### 🔁 Συγκρίσιμες ενεργές αγγελίες κοντά")
        _comparables(d, listings)

    with tabs[4]:
        st.markdown("#### 🏗️ Χαρακτηριστικά ακινήτου")
        spec_cols = st.columns(3)
        spec_cols[0].markdown(
            f"**Εμβαδόν:** {d['area_m2']:.0f} τ.μ.  \n"
            f"**Υπνοδωμάτια:** {d['bedrooms'] or '—'}  \n"
            f"**Όροφος:** {_floor_label(d['floor'])}  \n"
            f"**Κατασκευή:** {d.get('year_built') or '—'}"
            + (f" (ανακαίν. {d['renovated_year']})" if d.get("renovated_year") else "")
        )
        spec_cols[1].markdown(
            f"**Γειτονιά:** {d['neighborhood'] or '—'}  \n"
            f"**Διεύθυνση:** {d['address'] or '—'}  \n"
            f"**Κοντινότερο μετρό:** {d.get('nearest_metro') or '—'}  \n"
            f"**Απόσταση από μετρό:** {_metro_label(d)}"
        )
        spec_cols[2].markdown(
            f"**Ενεργειακή κλάση:** {d.get('energy_class') or '—'}  \n"
            f"**Θέρμανση:** {d.get('heating') or '—'}  \n"
            f"**Ιδιώτης πωλητής:** {'✅ ναι' if d['is_private_seller'] else '✗ όχι'}  \n"
            f"**Ήδη νοικιασμένο:** {'✅ ναι' if d['is_currently_rented'] else '✗ όχι'}"
        )
        st.markdown("#### 📈 Ιστορικό τιμής")
        history = get_history(lid)
        if len(history) >= 2:
            hist_df = pd.DataFrame(history, columns=["Ημερομηνία", "Τιμή"]).set_index("Ημερομηνία")
            st.line_chart(hist_df)
        elif len(history) == 1:
            st.caption(
                f"Πρώτη καταγεγραμμένη τιμή: {fmt.euro(history[0][1])} στις "
                f"{history[0][0]:%d/%m/%Y}. Το ιστορικό χτίζεται με τις ημερήσιες ενημερώσεις."
            )
        else:
            st.caption("Δεν υπάρχει ακόμα ιστορικό τιμής — συγκεντρώνεται καθημερινά.")

    st.divider()
    lb, db = st.columns(2)
    with lb:
        st.link_button("Άνοιγμα στην πηγή ↗", d["url"], width="stretch")
    with db:
        st.download_button(
            "⬇ Αναφορά μίας σελίδας (HTML)",
            listing_report.build_report_html(d),
            file_name=f"holargos-{lid}.html",
            mime="text/html",
            width="stretch",
            help="Εκτυπώσιμη σύνοψη μίας σελίδας για την αγγελία.",
        )
    skey = shortlist.lkey(d)
    st.checkbox(
        "⭐ Στα αγαπημένα",
        value=skey in buyer.watch_keys(),
        key=f"watch-{lid}",
        on_change=buyer.toggle_watch,
        args=(skey,),
    )


def page_strategy() -> None:
    st.subheader("Strategy")
    st.caption("Edit the investor's rules & weights, then re-score live — no redeploy.")
    strategy = load_strategy()

    with st.form("strategy"):
        st.markdown("**Hard filters**")
        min_floor = st.number_input("Min floor", value=strategy.hard_filters.min_floor, step=1)
        max_metro = st.number_input(
            "Metro distance for the 'near metro' filter (m)",
            value=strategy.hard_filters.max_metro_distance_m,
            step=50,
            help="Not a hard cutoff — metro proximity is a scoring signal. This only sets the "
            "threshold for the optional 'Near metro only' toggle on Opportunities.",
        )
        st.markdown("**Weights**")
        w = strategy.weights
        under = st.slider(
            "Undervaluation (vs hedonic fair value)", 0.0, 50.0, float(w.undervaluation)
        )
        gy = st.slider("Gross yield", 0.0, 50.0, float(w.gross_yield))
        newness = st.slider("Newness (build/reno year)", 0.0, 50.0, float(w.newness))
        energy = st.slider("Energy class", 0.0, 50.0, float(w.energy_class))
        pd_ = st.slider("Price drop", 0.0, 50.0, float(w.price_drop))
        rented = st.slider("Currently rented", 0.0, 50.0, float(w.is_currently_rented))
        private = st.slider("Private seller", 0.0, 50.0, float(w.is_private_seller))
        st.markdown("**Newness reference**")
        by_floor = st.number_input(
            "Build year = 0 signal at/below",
            value=strategy.scoring_reference.build_year_floor,
            step=5,
        )
        by_ceiling = st.number_input(
            "Build year = full signal at/above",
            value=strategy.scoring_reference.build_year_ceiling,
            step=5,
        )
        submitted = st.form_submit_button("Save & re-score")

    if submitted:
        strategy.hard_filters.min_floor = int(min_floor)
        strategy.hard_filters.max_metro_distance_m = int(max_metro)
        strategy.weights.undervaluation = under
        strategy.weights.gross_yield = gy
        strategy.weights.newness = newness
        strategy.weights.energy_class = energy
        strategy.weights.price_drop = pd_
        strategy.weights.is_currently_rented = rented
        strategy.weights.is_private_seller = private
        strategy.scoring_reference.build_year_floor = int(by_floor)
        strategy.scoring_reference.build_year_ceiling = int(by_ceiling)
        save_strategy(strategy)
        from scout.pipeline import rescore_all

        n = rescore_all(strategy)
        st.cache_data.clear()
        st.cache_resource.clear()
        st.success(f"Saved and re-scored {n} listings.")


def page_debug() -> None:
    st.subheader("🐛 Debug")
    st.caption("Raw data & pipeline diagnostics for troubleshooting.")

    # Which database backend is this process actually connected to? The #1 diagnostic
    # for "the daily pipeline ran but the site still looks stale" — usually means the
    # deployed app hasn't picked up a Postgres DATABASE_URL secret (needs a reboot on
    # Streamlit Cloud after adding/changing a secret) and is still on local SQLite.
    db_url = get_settings().db_url
    if db_url.startswith("postgresql"):
        # Never print the real URL (it carries the password) — just prove it's Postgres
        # and show which host, which is enough to confirm/deny "using the right DB".
        host = db_url.split("@", 1)[-1].split("/", 1)[0] if "@" in db_url else "?"
        st.success(f"🐘 Database backend: **Postgres** ({host})")
    else:
        st.warning(
            "🗄️ Database backend: **local SQLite** — DATABASE_URL is not active in this "
            "process. If you expect Postgres, the secret may need the app rebooted "
            "(Streamlit Cloud doesn't always auto-restart on a secret change)."
        )

    rows = get_all_listings_debug()
    if not rows:
        st.warning("Database is empty — run the pipeline.")
        return

    active = [d for d in rows if d["status"] == "active"]
    last_up = _last_updated(rows)
    first_seens = [d["first_seen"] for d in rows if d["first_seen"]]

    c = st.columns(4)
    c[0].metric("Total records", len(rows))
    c[1].metric("Active", len(active))
    c[2].metric("Excluded", sum(1 for d in rows if d["excluded"]))
    c[3].metric("Geocoded", sum(1 for d in rows if d["lat"] and d["lng"]))

    st.write(
        f"**Data last updated:** {last_up:%Y-%m-%d %H:%M:%S} UTC"
        if last_up
        else "**Data last updated:** never"
    )
    if first_seens:
        st.write(f"**Earliest record seen:** {min(first_seens):%Y-%m-%d %H:%M:%S} UTC")

    # Data-quality audit panel — the same numbers the improvement loop optimises, so the
    # depth of the dataset is visible, not hidden.
    st.markdown("**Data-quality audit**")
    try:
        from scout.data_quality import audit as _audit

        a = _audit()
        ac = st.columns(4)
        ac[0].metric("Fully detailed", f"{a.get('complete_pct', 0) * 100:.0f}%")
        ac[1].metric("Top-100 complete", f"{a.get('top100_complete', 0)}%")
        ac[2].metric("Biggest gap", str(a.get("top_gap", "—")))
        ac[3].metric("Eligible", a.get("total", len(active)))
        fields = a.get("fields") or {}
        if fields:

            def _fld(k: str, v: float) -> str:
                # "real_rent" is the share with the listing's OWN scraped rent; the rest use an
                # area-comp ESTIMATE. Show it to 0.1% (a ~0.3% share must not read as "0%") and
                # spell out the estimated majority so the yield isn't mistaken for measured.
                if k == "real_rent":
                    return f"real rent (own): {v * 100:.1f}% · {(1 - v) * 100:.0f}% estimated (area comp)"
                return f"{k}: {v * 100:.0f}%"

            st.caption(" · ".join(_fld(k, v) for k, v in fields.items()))
    except Exception as exc:  # never break the debug page on an audit hiccup
        st.caption(f"_audit unavailable: {exc}_")

    st.markdown("**Records by source**")
    src: dict[str, int] = {}
    for d in rows:
        src[d["source"]] = src.get(d["source"], 0) + 1
    st.write(src)

    st.markdown("**All records (raw, including excluded & inactive)**")
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch")
    st.download_button(
        "⬇️ Download as CSV", df.to_csv(index=False).encode("utf-8"), "holargos_listings.csv"
    )

    _health_panel()


def _health_panel() -> None:
    """Live scraper-health + job-queue status, so the owner can spot a broken scrape
    without opening a DB console. Every part is guarded — the panel must never crash
    the page (e.g. on an older DB missing the scrape_job / health_report tables)."""
    st.divider()
    st.markdown("### 🩺 Scraper health")
    try:
        from scout.health import check_health

        report = check_health()
        icon = {"ok": "✅", "warn": "⚠️", "error": "🚨"}.get(report.status, "•")
        st.write(f"{icon} **{report.status.upper()}**")
        for issue in report.issues:
            st.write(f"- {issue}")
        st.json(report.metrics)
    except Exception as exc:
        st.caption(f"Health check unavailable: {exc}")
    try:
        from scout.queue import job_stats

        st.write("**Scrape-job queue:**", job_stats())
    except Exception:
        pass
    recent = get_recent_health()
    if recent:
        st.markdown("**Recent health snapshots**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"checked_at": r["checked_at"], "status": r["status"], "issues": r["issues"]}
                    for r in recent
                ]
            ),
            width="stretch",
            hide_index=True,
        )


def page_neighborhoods(listings: list[dict]) -> None:
    st.subheader("Ανάλυση αγοράς ανά γειτονιά")
    st.caption("Στατιστικά αγοράς ανά περιοχή για τις αγγελίες που περνούν τα φίλτρα.")
    stats = analytics.neighborhood_stats(_eligible(listings))
    if not stats:
        st.info("Δεν υπάρχουν ακόμα στοιχεία γειτονιών — ανανέωσε τα δεδομένα.")
        return
    records = [
        {
            "Γειτονιά": s["neighborhood"],
            "Αγγελίες": s["count"],
            "Διάμεση τιμή": fmt.euro(s["median_price"]),
            "Διάμεσο €/τ.μ.": fmt.euro_per_m2(s["median_ppm2"]),
            "Διάμεση μικτή απόδοση": (
                f"{s['median_yield_pct']:.1f}%" if s["median_yield_pct"] is not None else "—"
            ),
            "Ευκαιρίες": s["opportunities"],
            "Πάνω από 180 μέρες": s["long_sitting"],
            "Κάτω από αξία": s["below_model"],
            "Νοικιασμένα": s["rented"],
        }
        for s in stats
    ]
    st.dataframe(pd.DataFrame(records), width="stretch", hide_index=True)

    # Rental market by area — REAL asked rents (scraped rental listings), joined with the
    # sale market to show where yield is structurally high vs low. This is the aggregation
    # a free portal never gives: the rent gradient (e.g. Vouliagmeni ~€22/m² vs Kamatero
    # ~€8/m²) next to what flats cost to buy there.
    try:
        import statistics as _stats

        from scout.rent_comps import OVERALL_KEY, load_rent_comps

        comps = load_rent_comps()
        sale_by_area: dict[str, list[float]] = {}
        for d in _eligible(listings):
            if d.get("price_per_m2") and d.get("search_area"):
                sale_by_area.setdefault(d["search_area"], []).append(d["price_per_m2"])
        rent_rows = []
        for area, per_hood in sorted(comps.items()):
            rent = per_hood.get(OVERALL_KEY)
            sales = sale_by_area.get(area) or []
            if not rent or len(sales) < 5:
                continue
            sale_med = _stats.median(sales)
            rent_rows.append(
                {
                    "Περιοχή": area,
                    "Διάμεσο ενοίκιο (€/τ.μ./μήνα)": round(rent, 1),
                    "Διάμεση τιμή πώλησης (€/τ.μ.)": int(sale_med),
                    "Τεκμαρτή μικτή απόδοση": f"{rent * 12 / sale_med * 100:.1f}%",
                }
            )
        if rent_rows:
            st.markdown("#### 🏠 Αγορά ενοικίων ανά περιοχή — πραγματικά ζητούμενα ενοίκια")
            rent_rows.sort(key=lambda r: -float(r["Τεκμαρτή μικτή απόδοση"].rstrip("%")))
            st.dataframe(pd.DataFrame(rent_rows), width="stretch", hide_index=True)
            st.caption(
                "Διάμεσο ζητούμενο ενοίκιο ÷ διάμεση τιμή πώλησης €/τ.μ. = η δομική μικτή "
                "απόδοση της περιοχής — πού η ζήτηση ενοικίων ξεπερνά τις τιμές."
            )
    except Exception:  # rent table must never break the page
        pass
    st.caption(
        "**Πάνω από 180 μέρες** = πωλητές πιθανώς πρόθυμοι για διαπραγμάτευση · **Κάτω από "
        "αξία** = σπίτια κάτω από την εκτιμώμενη αξία (πέρα από το ± εύρος) — εκεί ψάχνεις."
    )

    st.markdown("#### 📈 Δείκτης τιμών αγοράς (μηνιαία διάμεσος)")
    idx = analytics.market_price_index(get_all_price_history())
    if len(idx) >= 2:
        idx_df = (
            pd.DataFrame(idx)
            .set_index("month")[["median_price"]]
            .rename(columns={"median_price": "Διάμεση τιμή"})
            .rename_axis("Μήνας")
        )
        st.line_chart(idx_df)
        st.caption("Διάμεση καταγεγραμμένη τιμή όλων των αγγελιών, ανά μήνα.")
    else:
        st.caption("Ο δείκτης τιμών χτίζεται με τις ημερήσιες ενημερώσεις.")


def page_deals(listings: list[dict]) -> None:
    """Motivated-seller intelligence — the sellable core: owners most likely to negotiate,
    ranked by the negotiation signal, with an exportable agent lead list."""
    import csv
    import io

    st.subheader("💰 Deals — πρόθυμοι πωλητές")
    st.caption(
        "Ιδιοκτήτες που πιθανότατα θα διαπραγματευτούν, κατά μέρες στην αγορά, μειώσεις "
        "τιμής, υψηλή τιμή που δεν πουλάει και επαναδημοσιεύσεις. Γίνεται πιο ακριβές κάθε "
        "μέρα που συγκεντρώνεται ιστορικό."
    )
    eligible = _eligible(listings)
    ranked = sorted(eligible, key=lambda d: d.get("negotiation_score") or 0, reverse=True)
    motivated = [d for d in ranked if (d.get("negotiation_score") or 0) >= 45]

    c = st.columns(3)
    c[0].metric("Πρόθυμοι πωλητές", len(motivated))
    c[1].metric("Αγγελίες που παρακολουθούνται", len(eligible))
    tracked_days = None
    seens = [d["first_seen"] for d in eligible if d.get("first_seen")]
    if seens:
        tracked_days = (datetime.utcnow() - min(seens)).days
    c[2].metric(
        "Παρακολούθηση αγοράς", f"{tracked_days} μέρες" if tracked_days is not None else "—"
    )

    # Agent lead export (the Pro product — a per-territory motivated-seller list).
    buf = io.StringIO()
    from scout import metrics as _m

    w = csv.writer(buf)
    w.writerow(
        [
            "negotiation_score",
            "deal_grade",
            "price_eur",
            "suggested_offer_eur",
            "area_m2",
            "eur_per_m2",
            "neighborhood",
            "region",
            "days_on_market",
            "price_cut_pct",
            "below_model_pct",
            "net_yield_pct",
            "cap_rate_pct",
            "energy_class",
            "private_seller",
            "strategy_tags",
            "url",
        ]
    )
    for d in ranked:
        dom = fmt.days_on_market(d.get("first_seen"), d.get("last_seen"))
        fp, cp = d.get("first_price"), d.get("price", 0)
        cut = (fp - cp) / fp if (fp and cp < fp) else 0.0
        monthly = d.get("listed_rent") or d.get("est_monthly_rent")
        cap = _m.cap_rate(d["price"], monthly * 12, d.get("area_m2")) if monthly else None
        gap = d.get("value_gap_pct")
        ny = d.get("net_yield")
        w.writerow(
            [
                round(d.get("negotiation_score") or 0, 1),
                d.get("deal_grade") or "",
                d["price"],
                d.get("suggested_offer") or "",
                f"{d['area_m2']:.0f}",
                f"{d['price_per_m2']:.0f}" if d.get("price_per_m2") else "",
                d.get("neighborhood") or "",
                d.get("region") or "",
                dom if dom is not None else "",
                f"{cut * 100:.0f}%",
                f"{gap * 100:.0f}%" if gap is not None else "",
                f"{ny * 100:.1f}%" if ny is not None else "",
                f"{cap * 100:.1f}%" if cap is not None else "",
                d.get("energy_class") or "",
                "yes" if d.get("is_private_seller") else "no",
                " | ".join(d.get("strategy_tags") or []),
                d["url"],
            ]
        )
    st.download_button(
        "⬇  Εξαγωγή λίστας πρόθυμων πωλητών (CSV)",
        buf.getvalue(),
        "motivated_sellers.csv",
        "text/csv",
        help="Η λίστα πρόθυμων πωλητών σε μορφή CSV (για Excel).",
    )

    if not motivated:
        st.info(
            "Δεν υπάρχουν ακόμα ισχυρές ενδείξεις πρόθυμων πωλητών — αναμενόμενο σε νέα "
            "παρακολούθηση. Η ένδειξη χτίζεται από **αλλαγές στον χρόνο** (μειώσεις τιμής, "
            "μέρες στην αγορά, επαναδημοσιεύσεις) και συμπληρώνεται καθημερινά. Παρακάτω η "
            "τρέχουσα κατάταξη."
        )
    components.listing_grid(ranked[:60], metric="negotiation_score")


def page_saved_searches(listings: list[dict]) -> None:
    """Saved searches — the recurring investor mandate. Create one, see live matches, and
    (with an alert sink configured) get only these delivered daily. The €19/mo core loop."""
    from scout import saved_search as ss

    st.subheader("🔔 Saved searches")
    st.caption(
        "Define your mandate once — region, budget, min net yield, min deal grade. The daily "
        "digest then delivers only what matches, before you'd find it yourself."
    )
    eligible = _eligible(listings)

    with st.form("new_saved_search"):
        name = st.text_input("Name", placeholder="e.g. Centre ≤€200k, ≥4% net")
        regions = st.multiselect("Regions", list(REGIONS.keys()))
        c = st.columns(3)
        max_price = c[0].number_input("Max price (€)", 0, 2_000_000, 250_000, step=10_000)
        min_ny = c[1].slider("Min net yield (%)", 0.0, 8.0, 3.0, step=0.5) / 100
        min_grade = c[2].selectbox("Min grade", ["", "A", "B", "C"], index=0)
        if st.form_submit_button("💾 Save search") and name:
            ss.create_saved_search(
                ss.SavedSearch(
                    id=None,
                    name=name,
                    regions=regions,
                    max_price=int(max_price) or None,
                    min_net_yield=min_ny or None,
                    min_grade=min_grade or None,
                )
            )
            st.success(f"Saved '{name}'. It will appear below.")
            st.rerun()

    searches = ss.list_saved_searches()
    if not searches:
        st.info("No saved searches yet — create one above.")
        return
    for s in searches:
        matched = ss.matching_listings(s, eligible)
        new = [d for d in matched if d.get("is_new")]
        with st.expander(
            f"**{s.name}** — {len(matched)} matches · {len(new)} new today", expanded=False
        ):
            bits = []
            if s.regions:
                bits.append("/".join(s.regions))
            if s.max_price:
                bits.append(f"≤{fmt.euro(s.max_price)}")
            if s.min_net_yield:
                bits.append(f"≥{s.min_net_yield * 100:.1f}% net")
            if s.min_grade:
                bits.append(f"≥grade {s.min_grade}")
            st.caption(" · ".join(bits) or "no filters")
            if matched:
                components.listing_grid(matched[:12])
            if st.button("🗑 Delete", key=f"del-{s.id}"):
                ss.delete_saved_search(s.id)
                st.rerun()


def _go_find() -> None:
    st.session_state["page"] = HOME


def _compare_rows(d: dict, adv: dict) -> dict[str, str]:
    """One flat's facts as text (field -> value). Every figure names its basis in the field."""
    from scout import finance, picks

    cmp, age = adv["cmp"], adv["age"]
    built = d.get("renovated_year") or d.get("year_built")
    rent = d.get("listed_rent") or d.get("est_monthly_rent")
    gy = buyer.gross_yield(d)
    ny = (
        finance.net_yield(d["price"], rent * 12, d.get("area_m2"), bool(d.get("is_private_seller")))
        if rent
        else None
    )
    if d.get("is_unfinished"):
        status = "Υπό κατασκευή"
    else:
        status = "Ελέγχθηκε η περιγραφή" if d.get("page_checked") else "Δεν έχει ελεγχθεί ακόμα"
    return {
        "Τιμή": fmt.euro(d["price"]),
        "€/τ.μ.": fmt.euro_per_m2(d.get("price_per_m2")),
        "Εμβαδόν": f"{d['area_m2']:g} τ.μ." if d.get("area_m2") else "—",
        "Όροφος": buyer._floor(d["floor"]) if d.get("floor") is not None else "—",
        "Έτος": f"{built} ({age} ετών)" if built and age is not None else "—",
        "Ενοίκιο (εκτίμηση)": (
            f"~{fmt.euro(round(rent, -1))}/μήνα"
            + ("" if not d.get("listed_rent") else " (αγγελία)")
            if rent
            else "—"
        ),
        "Μικτή απόδοση": buyer.pct1(gy) if gy else "—",
        "Καθαρή απόδοση": buyer.pct1(ny) if ny else "—",
        "Παρόμοια": (
            f"{cmp['pct']:+.0%} €/τ.μ. · {cmp['n']} παρόμοια, {buyer.confidence(cmp).lower()}"
            if cmp
            else "—"
        ).replace("-", "−"),
        "Κατάσταση": status,
        "Σταθμός": picks.station(d) or "—",
        "Στην αγορά": (
            f"{d['days_on_market']} μέρες" if d.get("days_on_market") is not None else "—"
        ),
    }


def page_compare(listings: list[dict]) -> None:
    """Two flats side by side as a field · Α · Β facts table (3 columns fits a phone)."""

    st.subheader("Σύγκριση")
    st.caption("Διάλεξε 2 αγγελίες (τα αγαπημένα πρώτα).")
    from scout import nl_search, shortlist

    starred = buyer.watch_keys()
    elig = sorted(  # starred first — the usual "which of my favourites?" question
        nl_search.candidates(listings), key=lambda d: shortlist.lkey(d) not in starred
    )
    if not elig:
        st.info("Δεν υπάρχουν ακόμα αγγελίες για σύγκριση.")
        return

    def _name(d: dict) -> str:
        # Unique per listing: two flats in one neighbourhood at the same price must not
        # collapse into one option.
        size = f" · {d['area_m2']:g} τ.μ." if d.get("area_m2") else ""
        where = d.get("neighborhood") or d["source_id"]
        return f"{where}{size} · {fmt.euro(d['price'])} · #{d['id']}"

    by_id = {d["id"]: d for d in elig}
    opts = {("★ " if shortlist.lkey(d) in starred else "") + _name(d): d["id"] for d in elig}
    favs = [o for o, i in opts.items() if shortlist.lkey(by_id[i]) in starred]
    # Two selectboxes, not a multiselect: its built-in "select up to 2" notice is English.
    names = list(opts)
    if len(favs) >= 2:
        default = favs[:2]
    else:  # no favourites yet: start from the two best-scoring finished flats
        scores = buyer.buyer_scores(elig)
        best = sorted(
            (d for d in elig if not d.get("is_unfinished")), key=lambda d: -scores[d["id"]]
        )[:2]
        by_name = {i: n for n, i in opts.items()}
        default = [by_name[d["id"]] for d in best]
    default = default if len(default) == 2 else [None, None]
    pick_a = st.selectbox(
        "Α",
        names,
        index=names.index(default[0]) if default[0] else None,
        key="compare_a",
        placeholder="Γράψε περιοχή, τ.μ. ή τιμή",
    )
    pick_b = st.selectbox(
        "Β",
        names,
        index=names.index(default[1]) if default[1] else None,
        key="compare_b",
        placeholder="Γράψε περιοχή, τ.μ. ή τιμή",
    )
    if not pick_a or not pick_b:
        st.info("Διάλεξε δύο αγγελίες — ή άνοιξε «Βρες μου σπίτι» για να δεις τις καλύτερες.")
        st.button(HOME, key="cmp_to_find", on_click=_go_find)
        return
    if pick_a == pick_b:
        st.info("Διάλεξε δύο διαφορετικές αγγελίες.")
        return
    chosen = [by_id[opts[pick_a]], by_id[opts[pick_b]]]

    from scout import market_intel

    intel = market_intel.build(listings)
    views = [_compare_rows(d, buyer.buyer_view(d, intel)) for d in chosen]
    st.markdown(
        "\n\n".join(
            f"**{tag}** · {_name(d).rsplit(' · #', 1)[0]}"
            for tag, d in zip("ΑΒ", chosen, strict=True)
        )
    )
    rows = "".join(f"| {k} | {views[0][k]} | {views[1][k]} |\n" for k in views[0])
    st.markdown(f"| | Α | Β |\n|---|---|---|\n{rows}")
    st.caption(
        "Ενοίκιο: εκτίμηση από ζητούμενα ενοίκια της περιοχής (εκτός αν αναφέρεται στην αγγελία). "
        "Μικτή απόδοση = 12 × ενοίκιο ÷ τιμή. Καθαρή = μετά από κόστη αγοράς και λειτουργίας. "
        "Παρόμοια: €/τ.μ. σε σχέση με τη διάμεσο ίδιας περιοχής, ηλικίας και μεγέθους· "
        "αρνητικό = φθηνότερο.",
    )
    for tag, d in zip("ΑΒ", chosen, strict=True):
        st.link_button(f"Άνοιγμα {tag} στο {d['source'].upper()} ↗", d["url"], width="stretch")


# The home page: the guided flow (W8) when present, else «Βρες μου σπίτι».
if guide is not None:
    HOME, _home_page = guide.TITLE, getattr(guide, "page_guide", None) or guide.page
elif find is not None:
    HOME, _home_page = find.TITLE, find.page_find
else:  # neither module: start on the search page
    HOME, _home_page = "Αναζήτηση", buyer.page_search

# What a buyer uses. The older rental-investor tools (yields, cap rate, Airbnb, Golden Visa)
# stay reachable for the owner with ?admin=1.
NAV = {
    HOME: _home_page,
    "Πού να αγοράσω": areas.page_areas,
    "Αναζήτηση": buyer.page_search,
    "Χάρτης": page_map,
    "Αγαπημένα": buyer.page_watchlist,
    "Αποθηκευμένες αναζητήσεις": buyer.page_shortlist,
    "Σύγκριση": page_compare,
    buyer.NAV_DETAIL: buyer.page_listing,
}
ADMIN_NAV = {  # open with ?admin=1
    "🧮 Ανάλυση επενδυτή": page_detail,
    "📊 Αγορά": page_neighborhoods,
    "🏆 Ευκαιρίες": page_opportunities,
    "📰 Σήμερα": page_today,
    "💼 Deals": page_deals,
    "⚙️ Strategy": page_strategy,
    "🛠 Debug": page_debug,
}


# Phone navigation: one tap, short labels. Each maps to an existing NAV key (never renamed).
# «Αποθηκευμένες αναζητήσεις» and «Αγγελία» are reached from their pages, so no pill.
SHORT_NAV = {
    ("Οδηγός" if guide is not None else HOME): HOME,
    "Περιοχές": "Πού να αγοράσω",
    "Αναζήτηση": "Αναζήτηση",
    "Χάρτης": "Χάρτης",
    "Αγαπημένα": "Αγαπημένα",
    "Σύγκριση": "Σύγκριση",
}
_PILL_OF = {key: short for short, key in SHORT_NAV.items()}


def _pick_page() -> None:
    """Pill tapped -> go to its page. Deselecting (None) keeps the current page."""
    pick = st.session_state.get("nav_pill")
    if pick in SHORT_NAV:
        st.session_state["page"] = SHORT_NAV[pick]


def _data_status(listings: list[dict]) -> str:
    """One line: «XE.gr, Golden Home · ΗΗ/ΜΜ · N ενεργές · M ελεγμένες» — the sources actually
    present in the loaded listings, then the data's date and counts."""
    last_up = _last_updated(listings)
    if last_up is None:
        return "Δεν υπάρχουν δεδομένα ακόμα."
    active = sum(1 for d in listings if d.get("is_fresh", True))
    checked = sum(1 for d in listings if d.get("page_checked"))
    present = sorted({d.get("source") or "xe" for d in listings}, key=lambda k: (k != "xe", k))
    sources = ", ".join(SOURCE_LABELS.get(k, k) for k in present)
    return (
        f"{sources} · {last_up:%d/%m} · {fmt._gr_int(active)} ενεργές · "
        f"{fmt._gr_int(checked)} ελεγμένες"
    )


def _refresh_data() -> None:
    """Fetch the latest published data and drop every cache."""
    from scout import remote_db

    st.session_state.pop("watch", None)
    remote_db.ensure_local_db(max_age_s=0)
    st.cache_data.clear()
    st.cache_resource.clear()


def main() -> None:
    admin = bool(st.query_params.get("admin"))
    pages = {**NAV, **(ADMIN_NAV if admin else {})}
    with st.sidebar:  # desktop / keyboard navigation; on a phone the pills below do the job
        st.markdown("### Σκάουτ ακινήτων")
        account.login_ui()
        # «Αγγελία» needs a selected listing: reachable from cards only, listed only while open.
        shown = [p for p in pages if p != buyer.NAV_DETAIL or st.session_state.get("page") == p]
        page = st.radio("Σελίδα", shown, key="page", label_visibility="collapsed")
        st.button("Ανανέωση δεδομένων", key="refresh", on_click=_refresh_data, width="stretch")
    # Pills mirror the current page (pages also navigate by setting session_state["page"]).
    st.session_state["nav_pill"] = _PILL_OF.get(page)
    st.pills(
        "Σελίδα",
        list(SHORT_NAV),
        key="nav_pill",
        on_change=_pick_page,
        label_visibility="collapsed",
    )
    listings = get_listings()
    st.caption(_data_status(listings))

    if pages[page] in (page_opportunities, page_today):
        st.markdown(f"## {page}")
        _kpi_header(listings)
        st.divider()
    if pages[page] in (page_strategy, page_debug):
        pages[page]()
    else:
        pages[page](listings)


main()
