"""Greek 2026 regulatory layer — the differentiator no portal offers.

Pure functions, no DB/network/Streamlit. Given a listing's neighborhood, price, area,
energy class and build year, answer the questions that actually decide a cross-border
investment and that Spitogatos/Indomio/XE never touch:

  * ``str_legality``       — can a buyer legally SHORT-LET this (Airbnb) today?
  * ``golden_visa_status`` — does it qualify for the Golden Visa residence permit?
  * ``renovation_subsidy`` — is it a candidate for the Exoikonomo energy-upgrade subsidy?

Every constant here is sourced (see docs/PRODUCT_STRATEGY.md and the 2026 regulatory
research). These are INDICATIVE flags to shortlist and then verify with a lawyer — the
UI must say so; regulation shifts and a wrong call costs real money. Getting a status
wrong is worse than returning ``UNKNOWN``, so anything unresolved returns UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from unicodedata import category, normalize

from .ui.format import euro as _euro

# --- neighborhood normalization (matches enrich.py: lowercase + NFD accent strip) -------


def _norm(neighborhood: str | None) -> str | None:
    if not isinstance(neighborhood, str):
        return None
    stripped = "".join(c for c in normalize("NFD", neighborhood.lower()) if category(c) != "Mn")
    # collapse internal whitespace/hyphens so "neos kosmos" == "neos-kosmos" == "neoskosmos"
    token = "".join(ch for ch in stripped if ch.isalnum())
    return token or None


# --- SHORT-TERM-RENTAL (AMA / Airbnb) legality, 2026 -----------------------------------
# New-AMA registration freeze covers the Municipality of Athens' 1st/2nd/3rd municipal
# communities, EXTENDED through 31 Dec 2026 (Law context: lifo.gr, e-nomothesia.gr).
# AMA is non-transferable — it is deleted on any sale/gift/inheritance and the new owner
# cannot re-register (Law 5170/2025, in force 1 Oct 2025). Fines €5k → €10k → €20k.
# Source rosters: cityofathens.gr municipal-community list; getproofsnap.com; lifo.gr.
_STR_FROZEN = {
    _norm(n)
    for n in ("Koukaki", "Exarcheia", "Kolonaki", "Pagkrati", "Neos Kosmos", "Metaxourgeio")
}
# In the Municipality of Athens but OUTSIDE the frozen 1/2/3 districts (6th/7th communities).
# Legally ALLOWED today — flagged only as elevated regulatory watch (analytical, not legal).
_STR_EXPANDING_RISK = {_norm(n) for n in ("Kypseli", "Gkyzi", "Ampelokipoi")}

_STR_SOURCE = "Municipality of Athens district freeze, extended to 31 Dec 2026; Law 5170/2025"


@dataclass(frozen=True)
class StrLegality:
    status: str  # FROZEN | EXPANDING_RISK | ALLOWED | UNKNOWN
    can_new_short_let: bool | None  # can a BUYER start a new Airbnb? None when unknown
    headline: str
    detail: str
    source: str


def str_legality(neighborhood: str | None) -> StrLegality:
    """Short-let legality for a buyer, by neighborhood. Conservative: unknown → UNKNOWN."""
    key = _norm(neighborhood)
    if key is None:
        return StrLegality(
            "UNKNOWN",
            None,
            "Άγνωστο αν επιτρέπεται",
            "Δεν εντοπίστηκε η γειτονιά.",
            _STR_SOURCE,
        )
    if key in _STR_FROZEN:
        return StrLegality(
            "FROZEN",
            False,
            "❌ Δεν επιτρέπεται νέα βραχυχρόνια μίσθωση",
            "Εντός του «παγώματος» των κεντρικών διαμερισμάτων της Αθήνας (έως το 2026). Δεν "
            "εκδίδεται νέο ΑΜΑ (Airbnb) και όποιο υπάρχει διαγράφεται με την πώληση "
            "(ν. 5170/2025) — ο αγοραστής δεν μπορεί να το νοικιάσει βραχυχρόνια. "
            "Υπολόγισέ το μόνο για μακροχρόνια μίσθωση.",
            _STR_SOURCE,
        )
    if key in _STR_EXPANDING_RISK:
        return StrLegality(
            "EXPANDING_RISK",
            True,
            "⚠️ Επιτρέπεται — αλλά με αυξημένο κίνδυνο",
            "Επιτρέπεται σήμερα, αλλά βρίσκεται στον Δήμο Αθηναίων κοντά στα «παγωμένα» "
            "κεντρικά διαμερίσματα και το πάγωμα μπορεί να επεκταθεί. Υπολόγισε τον "
            "ρυθμιστικό κίνδυνο σε κάθε σχέδιο βραχυχρόνιας μίσθωσης.",
            _STR_SOURCE,
        )
    return StrLegality(
        "ALLOWED",
        True,
        "✓ Επιτρέπεται σήμερα",
        "Άλλος δήμος, εκτός του παγώματος του κέντρου της Αθήνας. Η βραχυχρόνια μίσθωση "
        "επιτρέπεται σήμερα (με εγγραφή ΑΜΑ πριν τη μίσθωση).",
        _STR_SOURCE,
    )


# --- GOLDEN VISA qualification (art. 64, Law 5100/2024, in force 31 Aug 2024) -----------
# €800,000 minimum across the ENTIRE Region of Attica (all coverage areas), single
# property ≥120 m². Short-term rental of the GV property is banned. €250k reduced tier
# only for commercial→residential conversion / listed-building restoration.
# Sources: stegasi.gov.gr; wfw.com; zeya.com; ot.gr.
GV_THRESHOLD_ATTICA = 800_000
GV_MIN_AREA_M2 = 120
_GV_SOURCE = "Golden Visa art. 64 Law 5100/2024 — €800k / ≥120 m² across Attica"


@dataclass(frozen=True)
class GoldenVisa:
    status: str  # QUALIFIES | BELOW_THRESHOLD | TOO_SMALL | UNKNOWN
    qualifies: bool | None
    headline: str
    detail: str
    source: str


def golden_visa_status(price: float | None, area_m2: float | None) -> GoldenVisa:
    """Golden Visa eligibility for a single property in Attica (all coverage is €800k zone)."""
    if not isinstance(price, (int, float)) or price <= 0:
        return GoldenVisa("UNKNOWN", None, "άγνωστη τιμή", "", _GV_SOURCE)
    reasons = []
    price_ok = price >= GV_THRESHOLD_ATTICA
    area_ok = isinstance(area_m2, (int, float)) and area_m2 >= GV_MIN_AREA_M2
    if not price_ok:
        reasons.append(f"τιμή κάτω από το όριο των {_euro(GV_THRESHOLD_ATTICA)} για την Αττική")
    if area_m2 is None:
        reasons.append("άγνωστο εμβαδόν (απαιτούνται ≥120 τ.μ.)")
    elif not area_ok:
        reasons.append(f"{area_m2:.0f} τ.μ. < 120 τ.μ. ελάχιστο")
    if price_ok and area_ok:
        return GoldenVisa(
            "QUALIFIES",
            True,
            "🛂 Επιλέξιμο",
            "Καλύπτει το όριο 800.000 € / ≥120 τ.μ. ανά ακίνητο για την Αττική. Σημείωση: "
            "ακίνητο Golden Visa δεν επιτρέπεται να νοικιαστεί βραχυχρόνια.",
            _GV_SOURCE,
        )
    status = "TOO_SMALL" if price_ok and not area_ok else "BELOW_THRESHOLD"
    return GoldenVisa(status, False, "Μη επιλέξιμο", "; ".join(reasons), _GV_SOURCE)


# --- RENOVATION SUBSIDY (Exoikonomo 2026) candidate ------------------------------------
# Expected H2 2026, ~62k homes, 50–80% subsidy (up to ~90% vulnerable). Eligibility:
# first EPC class C or lower, mandatory upgrade of ≥3 classes / >30% saving; pre-1980
# buildings score higher; income affects the RATE, not access. Rates are PROVISIONAL
# (press previews, final ΦΕΚ not yet open). Sources: selectra.gr; powergame.gr; espa.io.
_SUBSIDY_CLASSES = {"c", "d", "e", "f", "g", "h"}  # EPC C or lower = eligible starting point
# Greek EPC bands map straight onto the Latin scale: Α+ Α Β+ Β Γ Δ Ε Ζ Η → A+ A B+ B C D E F G.
_EPC_GREEK_TO_LATIN = {"α": "a", "β": "b", "γ": "c", "δ": "d", "ε": "e", "ζ": "f", "η": "g"}
_EPC_LATIN_TO_GREEK = {v: k for k, v in _EPC_GREEK_TO_LATIN.items()}  # for display
_RENO_SOURCE = "Exoikonomo 2026 (provisional — final decree pending)"


def _epc_latin(energy_class: str | None) -> str | None:
    """Latin EPC letter for a listing's class, accepting the Greek letters the data uses.
    Returns None for exempt/blank/unrecognized (never guesses)."""
    if not isinstance(energy_class, str):
        return None
    s = energy_class.strip().lower()
    if not s or s.startswith("εξαιρ"):  # "Εξαιρείται" = exempt from EPC (starts with Ε — guard it)
        return None
    first = s[0]
    if first in _EPC_GREEK_TO_LATIN:
        return _EPC_GREEK_TO_LATIN[first]
    return first if first in "abcdefgh" else None


@dataclass(frozen=True)
class RenovationSubsidy:
    candidate: bool
    headline: str
    detail: str
    source: str


def renovation_subsidy(energy_class: str | None, build_year: int | None) -> RenovationSubsidy:
    """Flag likely Exoikonomo-2026 energy-upgrade-subsidy candidates. Needs an EPC class."""
    cls = _epc_latin(energy_class)
    if cls not in _SUBSIDY_CLASSES:
        return RenovationSubsidy(
            False,
            "",  # not a candidate / unknown class → surface nothing
            "",
            _RENO_SOURCE,
        )
    old = isinstance(build_year, int) and build_year and build_year < 1980
    bonus = " Κτίριο πριν το 1980 παίρνει περισσότερους πόντους στη μοριοδότηση." if old else ""
    return RenovationSubsidy(
        True,
        "🔧 Πιθανός δικαιούχος επιδότησης",
        f"Η ενεργειακή κλάση {_EPC_LATIN_TO_GREEK.get(cls, cls).upper()} πληροί το «Εξοικονομώ 2026» (50–80% του κόστους "
        f"αναβάθμισης, απαιτεί άνοδο ≥3 ενεργειακών κλάσεων).{bonus} Τα ποσοστά είναι "
        "προσωρινά μέχρι την τελική ΚΥΑ.",
        _RENO_SOURCE,
    )
