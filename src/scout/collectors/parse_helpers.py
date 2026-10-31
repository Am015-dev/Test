"""Greek-label parsing helpers shared across collectors.

Centralized so floor mapping, rent detection, and private-seller detection are
consistent and individually testable. Every helper fails soft (returns None/False
on anything unexpected).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urljoin, urlsplit

# Greek floor labels -> numeric floor. ground=0, semi-basement=-1, mezzanine=0.5.
_FLOOR_WORD_MAP = {  # prefixes: XE cards abbreviate ("Ισόγ.", "Υπόγ.", "Ημιυπ.")
    "ισογ": 0.0,
    "ημιυπ": -1.0,
    "υπογ": -1.0,
    "ημιωρ": 0.5,
    "ημιορ": 0.5,
    "παταρ": 0.5,
}
_ORDINAL_RE = re.compile(r"(\d+)\s*ο[υς]?", re.IGNORECASE)  # "1ος", "3ου"


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def parse_floor(label: str | None) -> float | None:
    """Map a Greek floor label to a number. Returns None if unparseable.

    A combined/maisonette label concatenates segments, e.g. "Ισόγειο,1ος" (ground +
    1st). An explicit numeric floor is more specific than the ground/basement word,
    so prefer it — otherwise the word match short-circuits and the numbered level is
    silently lost (a ground+1st maisonette would read as floor 0 and be wrongly
    dropped by the ground-floor hard filter). Multiple ordinals -> the highest level.
    """
    if not label:
        return None
    norm = _strip_accents(label).lower().strip()

    # "ρετιρέ" (penthouse) and maisonette labels carry a numeric floor — prefer it.
    ordinals = [int(n) for n in _ORDINAL_RE.findall(norm)]
    if ordinals:
        return float(max(ordinals))

    for word, value in _FLOOR_WORD_MAP.items():
        if _strip_accents(word).lower() in norm:
            return value

    return None


# "μισθωμένο"/"ενοικιασμένο" = currently let. The "απόδοση" (yield) alternative was
# dropped: it never matched real accented text AND a "great yield" sales pitch on a
# *vacant* flat is not evidence it is currently rented — matching it would flip
# is_currently_rented on false positives.
_RENTED_HINT_RE = re.compile(r"μισθωμ[έε]ν|ενοικιασμ[έε]ν", re.IGNORECASE)
# A euro amount, e.g. "850 €" or "1.200 €". Capture the WHOLE punctuated run so Greek
# thousands separators aren't truncated ("1.200 €" must read 1200, not 200); a year
# like "2027" carries no € and is naturally excluded.
_EURO_AMOUNT_RE = re.compile(r"(\d[\d.,]*)\s*€")
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
            # Strip Greek thousands separators the same way parse_int does, so a full
            # sale price (e.g. "92.500") reads 92500 (out of band, skipped) rather than
            # a stray "500" fragment that could be mistaken for the rent.
            digits = re.sub(r"[.,\s]", "", raw)
            try:
                amount = int(digits)
            except ValueError:
                continue
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


def source_id_from_url(url: str | None) -> str | None:
    """Derive a stable listing id from a URL's last path segment.

    Strips the query string and fragment first: portal search links carry tracking
    params (``?from=search_list&position=3``) that vary by page/crawl, so leaving them
    in makes the same listing look new every run and breaks de-duplication.
    """
    if not url:
        return None
    clean = url.split("?", 1)[0].split("#", 1)[0]
    return clean.rstrip("/").split("/")[-1] or None


DESCRIPTION_MAX_CHARS = 1500


def clean_description(text: str | None, limit: int = DESCRIPTION_MAX_CHARS) -> str | None:
    """A listing's own description as stored for display: whitespace collapsed to single
    spaces, cut to ``limit`` characters. None for missing/blank text."""
    if not text:
        return None
    collapsed = " ".join(text.split())
    return collapsed[:limit] or None


# Lazy-loading carousels keep the real URL in a data attribute and put a placeholder (or
# nothing) in ``src``, so the data attributes are read before ``src``.
_IMG_ATTRS = ("data-src", "data-lazy-src", "data-original", "src")
# A portal's own "no photo" stand-in is not a photo: XE's
# ``.../static/images/icons/placeholder_real_estate-….jpg``, Golden Home's
# ``/img/site/goldenhome_default.png``, RE/MAX's ``associate-blank-medium.png``.
_PLACEHOLDER_RE = re.compile(
    r"placeholder|_default\.|/default[-_.]|no[-_]?(?:image|photo)|blank|/icons?/", re.I
)


def card_image_url(nodes: Iterable, base: str, host: str) -> str | None:
    """The first ``<img>`` in ``nodes`` with an absolute https URL on the portal's own
    ``host`` (e.g. ``xe.gr`` also matches ``blob.cdn.xe.gr``); relative URLs are resolved
    against ``base``. Inline ``data:`` URIs, other hosts (ad networks, agency logo
    services) and the portal's "no photo" placeholder are skipped. None when the card has
    no such image."""
    for node in nodes:
        for attr in _IMG_ATTRS:
            url = portal_photo_url(node.attributes.get(attr), base, host)
            if url:
                return url
    return None


def portal_photo_url(value: str | None, base: str, host: str) -> str | None:
    """``value`` as an absolute https URL on the portal's own ``host`` (or a subdomain),
    resolved against ``base``; None for another host, plain http, or a placeholder."""
    if not value:
        return None
    url = urljoin(base, value.strip())
    parts = urlsplit(url)
    name = (parts.hostname or "").lower()
    if parts.scheme != "https" or not (name == host or name.endswith("." + host)):
        return None
    if _PLACEHOLDER_RE.search(parts.path):
        return None
    return url
