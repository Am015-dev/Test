"""Greek-label parsing helpers shared across collectors.

Centralized so floor mapping, rent detection, and private-seller detection are
consistent and individually testable. Every helper fails soft (returns None/False
on anything unexpected).
"""

from __future__ import annotations

import re
import unicodedata

# Greek floor labels -> numeric floor. ground=0, semi-basement=-1, mezzanine=0.5.
_FLOOR_WORD_MAP = {
    "ισογειο": 0.0,
    "ημιυπογειο": -1.0,
    "υπογειο": -1.0,
    "ημιωροφος": 0.5,
    "ημιοροφος": 0.5,
    "πατάρι": 0.5,
}
_ORDINAL_RE = re.compile(r"(\d+)\s*ο[υς]?", re.IGNORECASE)  # "1ος", "3ου"


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def parse_floor(label: str | None) -> float | None:
    """Map a Greek floor label to a number. Returns None if unparseable."""
    if not label:
        return None
    norm = _strip_accents(label).lower().strip()

    for word, value in _FLOOR_WORD_MAP.items():
        if _strip_accents(word).lower() in norm:
            return value

    # "ρετιρέ" (penthouse) often carries a numeric floor — keep the number.
    m = _ORDINAL_RE.search(norm)
    if m:
        try:
            return float(int(m.group(1)))
        except ValueError:
            return None
    return None


_RENTED_HINT_RE = re.compile(r"μισθωμ[έε]ν|ενοικιασμ[έε]ν|αποδοσ", re.IGNORECASE)
# Any euro amount in the text, e.g. "850 €". We pick a plausible monthly rent
# (a year like "2027" carries no € and is naturally excluded).
_EURO_AMOUNT_RE = re.compile(r"(\d{2,5})\s*€")
# A monthly rent sits in this band; anything larger is a sale price, anything
# smaller is noise.
_MIN_RENT, _MAX_RENT = 100, 5000


def parse_rent(description: str | None) -> tuple[bool, int | None]:
    """Detect 'currently rented' and any stated monthly rent.

    Returns (is_currently_rented, listed_rent_eur). When a rent keyword is present
    and a euro amount in the monthly-rent band exists, that amount is the rent.
    """
    if not description:
        return False, None
    rented = bool(_RENTED_HINT_RE.search(description))
    rent = None
    if rented:
        for raw in _EURO_AMOUNT_RE.findall(description):
            amount = int(raw)
            if _MIN_RENT <= amount <= _MAX_RENT:
                rent = amount
                break
    return rented, rent


# Match the seller noun "ιδιώτης/ιδιώτη" (private individual) but NOT the adjective
# "ιδιωτικό" (private parking/pool/garden), which caused false private-seller badges.
_PRIVATE_RE = re.compile(r"ιδιωτη|οχι\s+μεσιτ|χωρις\s+μεσιτ", re.IGNORECASE)


def parse_private_seller(text: str | None) -> bool:
    """Detect a private (non-agency) seller from free text."""
    if not text:
        return False
    return bool(_PRIVATE_RE.search(_strip_accents(text)))


_INT_RE = re.compile(r"-?\d[\d.,]*")


def parse_int(text: str | None) -> int | None:
    """Extract an integer from messy text like '215.000 €' -> 215000."""
    if text is None:
        return None
    m = _INT_RE.search(text)
    if not m:
        return None
    digits = re.sub(r"[.,\s]", "", m.group(0))
    try:
        return int(digits)
    except ValueError:
        return None


def parse_float(text: str | None) -> float | None:
    """Extract a float like '82,5 m²' -> 82.5."""
    if text is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None
