"""Free-text home search: text -> SearchFilters (Claude) -> match % over listing dicts."""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from scout.config import get_settings
from scout.finance import acquisition_costs

Want = Literal["elevator", "parking", "balcony", "renovated"]
Kind = Literal["apartment", "maisonette", "house"]

# Listing kind from the title (the only place it is stated). Whole buildings, complexes, air
# rights and land are never a home to buy, so they never match.
KIND_WORDS: dict[str, tuple[str, ...]] = {
    "apartment": ("διαμερισμα", "apartment", "studio", "γκαρσονιερα", "loft", "flat"),
    "maisonette": ("μεζονετα", "maisonette"),
    "house": ("μονοκατοικια", "house", "βιλα", "villa"),
}
KIND_LABEL = {"apartment": "διαμέρισμα", "maisonette": "μεζονέτα", "house": "μονοκατοικία"}
NOT_A_HOME = ("πολυκατοικια", "συγκροτημα", "αερα", "οικοπεδο", "κτιριο", "μπλοκ")

# The listing dict has no feature columns, so wants are matched on title/location text.
WANT_WORDS: dict[str, tuple[str, ...]] = {
    "elevator": ("ανελκυστηρ", "ασανσερ", "elevator", "lift"),
    "parking": ("παρκινγκ", "γκαραζ", "σταθμευσ", "parking", "garage"),
    "balcony": ("μπαλκον", "βεραντ", "balcon", "terrace"),
    "renovated": ("ανακαινισ", "renovat"),
}
WANT_LABEL = {
    "elevator": "ανελκυστήρας",
    "parking": "πάρκινγκ",
    "balcony": "μπαλκόνι",
    "renovated": "ανακαινισμένο",
}


class SearchFilters(BaseModel):
    areas: list[str] = Field(
        default_factory=list,
        description="Neighbourhoods/municipalities. Give BOTH the Greek name and its Latin "
        "transliteration as separate entries (e.g. 'Χολαργός', 'Cholargos').",
    )
    price_min: int | None = None
    price_max: int | None = None
    area_min: float | None = Field(None, description="Min square metres")
    area_max: float | None = None
    bedrooms_min: int | None = Field(None, description="'δυάρι' = 1 bedroom, 'τριάρι' = 2")
    bedrooms_max: int | None = None
    floor_min: float | None = None
    private_only: bool = False
    kinds: list[Kind] = Field(
        default_factory=list,
        description="Only when the user names a kind: 'διαμέρισμα'/'δυάρι'/'τριάρι'/'γκαρσονιέρα' "
        "= apartment, 'μεζονέτα' = maisonette, 'μονοκατοικία'/'βίλα' = house.",
    )
    budget: int | None = Field(
        None,
        description="Total capital the user wants to invest, EUR, when stated as an amount to "
        "invest ('έχω 200.000 να επενδύσω'). Not the same as price_max.",
    )
    wants: list[Want] = Field(default_factory=list)


def describe(f: SearchFilters) -> str:
    """The parsed filters in plain Greek, so the user can check what was understood."""
    parts = []
    if f.areas:
        parts.append("περιοχή: " + ", ".join(f.areas))
    if f.budget:
        parts.append(f"budget {f.budget:,} €")
    if f.price_min or f.price_max:
        parts.append(f"τιμή {f.price_min or 0:,}–{f'{f.price_max:,}' if f.price_max else '∞'} €")
    if f.area_min or f.area_max:
        parts.append(f"{f.area_min or 0:g}–{f'{f.area_max:g}' if f.area_max else '∞'} τ.μ.")
    if f.bedrooms_min is not None or f.bedrooms_max is not None:
        lo, hi = f.bedrooms_min, f.bedrooms_max
        parts.append(f"υπνοδωμάτια: {lo if lo == hi else f'{lo}–{hi}'}")
    if f.floor_min is not None:
        parts.append(f"όροφος ≥ {f.floor_min:g}")
    if f.kinds:
        parts.append("τύπος: " + "/".join(KIND_LABEL[k] for k in f.kinds))
    if f.private_only:
        parts.append("μόνο ιδιώτης")
    parts += [WANT_LABEL[w] for w in f.wants]
    return " · ".join(parts) or "τίποτα συγκεκριμένο — δείχνω τα πάντα"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


_GREEKLISH = {"θ": "th", "χ": "ch", "ψ": "ps", "ξ": "x"}
_GREEKLISH_1 = str.maketrans("αβγδεζηικλμνοπρσςτυφω", "avgdeziiklmnoprsstyfo")


def _latin(text: str) -> str:
    """Rough Greek→Latin transliteration (accents already stripped): χολαργοσ → cholargos."""
    for g, lat in _GREEKLISH.items():
        text = text.replace(g, lat)
    return text.translate(_GREEKLISH_1)


def _stem(word: str) -> str:
    """Drop the inflected ending so Παπάγος/Παπάγου, Χολαργός/Χολαργού, Papagos/Papagou meet."""
    if len(word) > 5:
        return word[:-2]
    return word[:-1] if len(word) > 3 else word


def _area_in(area: str, where: str) -> bool:
    """Every word of ``area`` (stemmed) appears in the listing's normalised location text."""
    words = _norm(area).replace("-", " ").split()
    return bool(words) and all(_stem(w) in where for w in words)


def match(d: dict, f: SearchFilters) -> tuple[int, list[str]] | None:
    """Return (match %, reasons), or None if a hard criterion fails.

    Unknown (None) listing fields never exclude. Wants are soft: 60 + 40 * confirmed/total.
    """
    reasons: list[str] = []
    # Match on where the listing IS. `search_area` is only the area XE was searched for, and XE's
    # area search also returns neighbouring places (a Χαλάνδρι flat under "Cholargos"), so it is a
    # fallback for listings that carry no location of their own.
    where = _norm(" ".join(str(d.get(k) or "") for k in ("neighborhood", "address")))
    if where.strip():
        where = f"{where} {_latin(where)}"  # so "Cholargos" also finds "Χολαργός"
    else:
        where = _norm(str(d.get("search_area") or ""))
    if f.areas:
        hit = next((a for a in f.areas if _area_in(a, where)), None)
        if hit is None:
            return None
        reasons.append(f"περιοχή: {hit}")
    bounds = (
        ("price", f.price_min, f.price_max, "τιμή"),
        ("area_m2", f.area_min, f.area_max, "τ.μ."),
        ("bedrooms", f.bedrooms_min, f.bedrooms_max, "υπνοδωμάτια"),
        ("floor", f.floor_min, None, "όροφος"),
    )
    for key, lo, hi, label in bounds:
        v = d.get(key)
        if v is None:
            continue
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            return None
        if lo is not None or hi is not None:
            reasons.append(f"{label}: {v:g}")
    title = _norm(d.get("title") or "")
    if title.startswith(NOT_A_HOME):
        return None
    if f.kinds and not any(title.startswith(w) for k in f.kinds for w in KIND_WORDS[k]):
        return None
    if f.private_only and d.get("is_private_seller") is False:
        return None
    if f.budget and d.get("price"):
        cash = d["price"] + (acquisition_costs(d["price"], bool(d.get("is_private_seller"))) or 0)
        if cash > f.budget:
            return None
        reasons.append(f"συνολικό κόστος {cash:,.0f} €")
    text = _norm(f"{where} {d.get('title') or ''}")
    confirmed = [
        w
        for w in f.wants
        if any(k in text for k in WANT_WORDS[w]) or (w == "renovated" and d.get("renovated_year"))
    ]
    reasons += [WANT_LABEL[w] for w in confirmed]
    pct = 100 if not f.wants else 60 + 40 * len(confirmed) // len(f.wants)
    return pct, reasons


def advise(d: dict) -> dict:
    """Buyer view of one listing: a 0-100 score plus the facts behind it.

    Score = 60% the thesis score already on the listing + 40% buy-value: how far the price
    sits under the model value (20% under = full marks), seller motivation and a price drop.
    Without a confident model value it is the thesis score alone.
    """
    base = d.get("score") or 0
    gap = d.get("value_gap_pct") if d.get("value_confident") else None
    if gap is None:
        score = base
    else:
        value = min(max(gap / 0.20, 0), 1) * 70 + min(d.get("negotiation_score") or 0, 100) * 0.2
        value += 10 if d.get("price_dropped") else 0
        score = 0.6 * base + 0.4 * value
    return {"score": round(score), "gap": gap}


MAX_CHARS = 500
MODEL = "claude-haiku-5-5"
SYSTEM = (
    "Convert a Greek home-BUYING search request into filters by calling set_filters. "
    "Prices are purchase prices in EUR ('180Χ' = 180000). Only set fields the user stated. "
    "Area names go in the NOMINATIVE case ('Παπάγος', not 'Παπάγου'), each with its Latin "
    "transliteration. An amount the user says they want to invest is budget, not price_max."
)


class SearchParseError(Exception):
    """The query could not be turned into filters (shown to the user, never swallowed)."""


def parse_query(text: str, client=None) -> SearchFilters:
    text = text.strip()[:MAX_CHARS]
    if not text:
        raise SearchParseError("Γράψε τι σπίτι ψάχνεις.")
    if client is None:
        key = get_settings().anthropic_api_key
        if not key:
            raise SearchParseError("Λείπει το ANTHROPIC_API_KEY (βάλ'το στο .env ή στα secrets).")
        import anthropic

        client = anthropic.Anthropic(api_key=key)
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=SYSTEM,
            messages=[{"role": "user", "content": text}],
            tools=[
                {
                    "name": "set_filters",
                    "description": "Set the search filters.",
                    "input_schema": SearchFilters.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "set_filters"},
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        return SearchFilters.model_validate(block.input)
    except Exception as e:  # API, no tool block, or invalid filters: all the same to the user
        raise SearchParseError(f"Δεν κατάλαβα την αναζήτηση ({type(e).__name__}).") from e
