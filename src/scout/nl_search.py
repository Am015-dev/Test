"""Free-text home search: text -> SearchFilters (Claude) -> match % over listing dicts."""

from __future__ import annotations

import unicodedata
from datetime import date
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
NOT_A_HOME = ("πολυκατοικια", "συγκρ", "αερα", "οικοπεδο", "κτιριο", "μπλοκ")

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
    year_min: int | None = Field(
        None,
        description="Built (or renovated) in or after this year, only if the user asks about age: "
        "'νεόδμητο' = 2020, 'μετά το 2000' = 2000, 'όχι πάνω από 20 χρόνια' = current year - 20, "
        "'όχι παλιό' = 1990.",
    )
    include_unfinished: bool = Field(
        False, description="True only if the user explicitly wants unfinished/under-construction."
    )
    include_undeclared: bool = Field(
        False,
        description="True only if the user explicitly also wants listings that do not state "
        "their floor or build year when a floor/year filter is set.",
    )
    budget: int | None = Field(
        None,
        description="Total capital the user wants to invest, EUR, when stated as an amount to "
        "invest ('έχω 200.000 να επενδύσω'). Not the same as price_max.",
    )
    wants: list[Want] = Field(default_factory=list)


def _gr(n: float) -> str:
    """Greek thousands separator: 180000 -> '180.000'."""
    return f"{n:,.0f}".replace(",", ".")


def describe(f: SearchFilters) -> str:
    """The parsed filters in plain Greek, so the user can check what was understood."""
    parts = []
    if f.areas:
        named = [a for a in f.areas if not a.isascii()] or f.areas  # "Χολαργός" over "Cholargos"
        parts.append("περιοχή: " + ", ".join(named))
    if f.budget:
        parts.append(f"κεφάλαιο {_gr(f.budget)} €")
    if f.price_min and f.price_max:
        parts.append(f"τιμή {_gr(f.price_min)}–{_gr(f.price_max)} €")
    elif f.price_min or f.price_max:
        parts.append(
            f"τιμή από {_gr(f.price_min)} €" if f.price_min else f"τιμή έως {_gr(f.price_max)} €"
        )
    if f.area_min and f.area_max:
        parts.append(f"{f.area_min:g}–{f.area_max:g} τ.μ.")
    elif f.area_min or f.area_max:
        parts.append(f"από {f.area_min:g} τ.μ." if f.area_min else f"έως {f.area_max:g} τ.μ.")
    if f.bedrooms_min is not None or f.bedrooms_max is not None:
        lo, hi = f.bedrooms_min, f.bedrooms_max
        parts.append(f"υπνοδωμάτια: {lo if lo == hi else f'{lo}–{hi}'}")
    if f.floor_min is not None:
        parts.append(f"από {f.floor_min:g}ο όροφο")
    if f.kinds:
        parts.append("τύπος: " + "/".join(KIND_LABEL[k] for k in f.kinds))
    if f.year_min:
        parts.append(f"κτίριο από {f.year_min}")
    if f.include_unfinished:
        parts.append("και υπό κατασκευή")
    if f.include_undeclared and (f.floor_min is not None or f.year_min):
        parts.append("και χωρίς δηλωμένο όροφο/έτος")
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
    return bool(words) and (
        all(_stem(w) in where for w in words) or all(_stem(_latin(w)) in where for w in words)
    )


def area_matches(area: str, place: str) -> bool:
    """Whether a typed/selected ``area`` names ``place`` (any case ending, Greek or Latin)."""
    where = _norm(place)
    return _area_in(area, f"{where} {_latin(where)}")


# Why a listing is hidden, in the order the reasons are checked: a listing that fails several
# filters is counted under the first. Floor/year come after everything else, and a missing
# floor/year after a known-but-wrong one, so "include undeclared" brings back exactly the
# "undeclared" group and dropping the floor/year filters brings back exactly those groups.
HIDE_ORDER = (
    "area",
    "not_home",
    "price",
    "size",
    "bedrooms",
    "kind",
    "private",
    "unfinished",
    "floor",
    "year",
    "undeclared",
)


def _where(d: dict) -> str:
    # Match on where the listing IS. `search_area` is only the area XE was searched for, and XE's
    # area search also returns neighbouring places (a Χαλάνδρι flat under "Cholargos"), so it is a
    # fallback for listings that carry no location of their own.
    # Only the municipality part: "Παπάγου (Σύνορα με Χολαργό)" is in Παπάγου, not Χολαργός.
    place = d.get("neighborhood") or d.get("address") or ""
    where = _norm(place.split(" (")[0])
    if where.strip():
        return f"{where} {_latin(where)}"  # so "Cholargos" also finds "Χολαργός"
    return _norm(str(d.get("search_area") or ""))


def why_hidden(d: dict, f: SearchFilters) -> str | None:
    """The first filter ``d`` fails (a ``HIDE_ORDER`` code), or None when it matches.

    Unknown size/bedrooms never exclude. Floor and build year are what this buyer filters on
    most, so a listing that does not state them fails a floor/year filter as "undeclared" —
    unless ``f.include_undeclared``. The year filter is the BUILD year: a renovated flat in a
    1970s block is still a 1970s block.
    """
    if f.areas and not any(_area_in(a, _where(d)) for a in f.areas):
        return "area"
    title = _norm(d.get("title") or "")
    if title.startswith(NOT_A_HOME):
        return "not_home"
    price = d.get("price")
    if price is not None:
        if (f.price_min and price < f.price_min) or (f.price_max and price > f.price_max):
            return "price"
        if f.budget:
            cash = price + (acquisition_costs(price, bool(d.get("is_private_seller"))) or 0)
            if cash > f.budget:
                return "price"
    m2 = d.get("area_m2")
    if m2 is not None and ((f.area_min and m2 < f.area_min) or (f.area_max and m2 > f.area_max)):
        return "size"
    beds = d.get("bedrooms")
    if beds is not None and (
        (f.bedrooms_min is not None and beds < f.bedrooms_min)
        or (f.bedrooms_max is not None and beds > f.bedrooms_max)
    ):
        return "bedrooms"
    # An unstated kind (no title) is not proof of a house: it never excludes.
    if title and f.kinds and not any(title.startswith(w) for k in f.kinds for w in KIND_WORDS[k]):
        return "kind"
    if f.private_only and d.get("is_private_seller") is False:
        return "private"
    if d.get("is_unfinished") and not f.include_unfinished:
        return "unfinished"
    floor, built = d.get("floor"), d.get("year_built")
    if f.floor_min is not None and floor is not None and floor < f.floor_min:
        return "floor"
    if f.year_min and built is not None and built < f.year_min:
        return "year"
    if not f.include_undeclared and (
        (f.floor_min is not None and floor is None) or (f.year_min and built is None)
    ):
        return "undeclared"
    return None


def match(d: dict, f: SearchFilters) -> tuple[int, list[str]] | None:
    """Return (match %, reasons), or None if a hard criterion fails (see ``why_hidden``).

    Wants are soft: 60 + 40 * confirmed/total.
    """
    if why_hidden(d, f) is not None:
        return None
    where = _where(d)
    reasons: list[str] = []
    if f.areas:
        reasons.append("περιοχή: " + next(a for a in f.areas if _area_in(a, where)))
    for key, lo, hi, label in (
        ("price", f.price_min, f.price_max, "τιμή"),
        ("area_m2", f.area_min, f.area_max, "τ.μ."),
        ("bedrooms", f.bedrooms_min, f.bedrooms_max, "υπνοδωμάτια"),
        ("floor", f.floor_min, None, "όροφος"),
    ):
        if (lo is not None or hi is not None) and d.get(key) is not None:
            reasons.append(f"{label}: {d[key]:g}")
    if f.year_min and d.get("year_built"):
        reasons.append(f"έτος {d['year_built']}")
    if f.budget and d.get("price"):
        cash = d["price"] + (acquisition_costs(d["price"], bool(d.get("is_private_seller"))) or 0)
        reasons.append(f"συνολικό κόστος {_gr(cash)} €")
    text = _norm(f"{where} {d.get('title') or ''}")
    confirmed = [
        w
        for w in f.wants
        if any(k in text for k in WANT_WORDS[w]) or (w == "renovated" and d.get("renovated_year"))
    ]
    reasons += [WANT_LABEL[w] for w in confirmed]
    pct = 100 if not f.wants else 60 + 40 * len(confirmed) // len(f.wants)
    return pct, reasons


def building_age(d: dict, today_year: int | None = None) -> int | None:
    """Years since construction or the last stated renovation; None when unknown."""
    if d.get("building_age") is not None:
        return d["building_age"]
    built = d.get("renovated_year") or d.get("year_built")
    if not built:
        return None
    age = (today_year or date.today().year) - int(built)
    return age if 0 <= age < 200 else None


def age_factor(age: int | None) -> float:
    """How much the building's age discounts a buy score. A 60-year-old block (old wiring and
    plumbing, no insulation, pre-1985 seismic code) is not a top buy however cheap it looks."""
    if age is None:
        return 0.9  # unknown age: a little caution, not a verdict
    if age <= 15:
        return 1.0
    if age <= 30:
        return 0.95
    if age <= 40:
        return 0.8
    if age <= 50:
        return 0.6
    return 0.45


YIELD_GOOD, YIELD_WEAK = 0.055, 0.04  # gross yield: ▲ at/above, ▼ below (scoring's 2–8% scale)
OFF_PLAN_FACTOR = 0.6  # built "this year": often still a shell sold off-plan — unconfirmed
UNFINISHED_FACTOR = 0.25  # an unfinished shell needs more capital before it can be let


TOO_CHEAP = 0.35  # this far under the like-for-like median = check why before believing it


def advise(d: dict, comp_pct: float | None = None) -> dict:
    """Buyer view of one listing: a 0-100 score plus the facts behind it.

    Score = 60% the thesis score already on the listing (rental yield, energy class, metro…)
    + 40% buy-value, then discounted by building age (see ``age_factor``). Buy-value comes
    from ``comp_pct`` — this flat's €/m² against like-for-like listings (same area, age band,
    size; see ``market_intel``): 20% under = full marks — plus seller motivation and a price
    cut. Without comparables it falls back to a confident model value, else it is skipped.
    Off-plan (built this year) × 0.6; unfinished × 0.25.

    ``parts`` is the visible breakdown: (label, +1 helps / 0 neutral / -1 hurts / None unknown).
    """
    base = d.get("score") or 0
    gap = -comp_pct if comp_pct is not None else None
    if gap is None and d.get("value_confident"):
        gap = d.get("value_gap_pct")
    parts: list[tuple[str, int | None]] = []
    # Far under every comparable is a question (wrong m², a shell, legal trouble), not a deal:
    # it earns no value credit — and its "yield" (area rent ÷ that price) none either.
    too_cheap = gap is not None and gap > TOO_CHEAP
    if gap is None:
        score = base
    else:
        credit = 0.0 if too_cheap else min(max(gap / 0.20, 0), 1)
        value = credit * 70 + min(d.get("negotiation_score") or 0, 100) * 0.2
        value += 10 if d.get("price_dropped") else 0
        score = 0.6 * base + 0.4 * value
        sign = None if too_cheap else 1 if gap >= 0.10 else -1 if gap <= -0.10 else 0
        parts.append(("τιμή vs παρόμοια", sign))
    if too_cheap:
        score *= 0.7
    age = building_age(d)
    factor = age_factor(age)
    score *= factor
    sign = None if age is None else 1 if factor >= 0.95 else 0 if factor >= 0.8 else -1
    parts.append(("ηλικία", sign))
    if (gy := d.get("gross_yield")) and not too_cheap:
        parts.append(("απόδοση", 1 if gy >= YIELD_GOOD else -1 if gy < YIELD_WEAK else 0))
    if (d.get("year_built") or 0) >= date.today().year:
        score *= OFF_PLAN_FACTOR
        parts.append(("υπό παράδοση", -1))
    if d.get("is_unfinished"):
        score *= UNFINISHED_FACTOR
        parts.append(("ημιτελές", -1))
    return {
        "score": round(score),
        "gap": gap,
        "age": age,
        "parts": parts,
        "too_cheap": too_cheap,
    }


def candidates(listings: list[dict], include_stale: bool = False) -> list[dict]:
    """Listings worth showing a buyer: not excluded, not data-suspect, and (by default) seen
    recently — old snapshot rows are often already sold and their links dead."""
    return [
        d
        for d in listings
        if not d.get("excluded")
        and not d.get("is_suspect")
        and (include_stale or d.get("is_fresh", True))
    ]


MAX_CHARS = 500
MODEL = "claude-haiku-5-5"
SYSTEM = (
    "Convert a Greek home-BUYING search request into filters by calling set_filters. "
    "Prices are purchase prices in EUR ('180Χ' = 180000). Only set fields the user stated. "
    "Area names go in the NOMINATIVE case ('Παπάγος', not 'Παπάγου'), each with its Latin "
    "transliteration. An amount the user says they want to invest is budget, not price_max. "
    "Never set year_min or include_unfinished unless the user talks about age or construction."
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
            raise SearchParseError("Η αναζήτηση με ελεύθερο κείμενο δεν είναι διαθέσιμη εδώ.")
        import anthropic

        client = anthropic.Anthropic(api_key=key)
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=f"{SYSTEM} The current year is {date.today().year}.",
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
        raise SearchParseError("Δεν κατάλαβα την αναζήτηση — δοκίμασε να τη γράψεις αλλιώς.") from e
