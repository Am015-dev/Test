"""Free-text home search: text -> SearchFilters (Claude) -> match % over listing dicts."""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from scout.config import get_settings

Want = Literal["elevator", "parking", "balcony", "renovated"]

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
    wants: list[Want] = Field(default_factory=list)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def match(d: dict, f: SearchFilters) -> tuple[int, list[str]] | None:
    """Return (match %, reasons), or None if a hard criterion fails.

    Unknown (None) listing fields never exclude. Wants are soft: 60 + 40 * confirmed/total.
    """
    reasons: list[str] = []
    where = _norm(" ".join(str(d.get(k) or "") for k in ("neighborhood", "address", "search_area")))
    if f.areas:
        hit = next((a for a in f.areas if _norm(a) in where), None)
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
    if f.private_only and d.get("is_private_seller") is False:
        return None
    text = _norm(f"{where} {d.get('title') or ''}")
    confirmed = [
        w
        for w in f.wants
        if any(k in text for k in WANT_WORDS[w]) or (w == "renovated" and d.get("renovated_year"))
    ]
    reasons += [WANT_LABEL[w] for w in confirmed]
    pct = 100 if not f.wants else 60 + 40 * len(confirmed) // len(f.wants)
    return pct, reasons


MAX_CHARS = 500
MODEL = "claude-haiku-5-5"
SYSTEM = (
    "Convert a Greek home-BUYING search request into filters by calling set_filters. "
    "Prices are purchase prices in EUR ('180Χ' = 180000). Only set fields the user stated."
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
