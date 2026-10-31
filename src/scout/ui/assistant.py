"""Ο βοηθός «Ρώτα με» και το «Σημείωμα επενδυτή».

Τι κάνει: διαβάζει μόνο τους αριθμούς που έχουμε ήδη βγάλει για τα σπίτια που βλέπεις:
τιμή, €/τ.μ., τι ζητούν τα παρόμοια και πόσα είναι, ενοίκιο (εκτίμηση) και από πού βγαίνει,
μικτή και καθαρή απόδοση, μέρες στην αγορά, αν ελέγχθηκε η περιγραφή, φωτογραφίες, σταθμό,
στοιχεία της περιοχής και τους κανόνες για βραχυχρόνια ενοικίαση. Απαντά στα ελληνικά, σε
έως 120 λέξεις.

Τι θα σου πει: τι κερδίζεις και τι χάνεις ανάμεσα στις καλύτερες επιλογές, με αριθμούς. Τι
να ελέγξεις σε κάθε σπίτι πριν το δεις. Από πού να ξεκινήσεις την προσφορά: 3 % κάτω από
την τιμή, άλλο 3 % αν είναι 90 μέρες και πάνω στην αγορά, άλλο 2 % αν πουλά ιδιώτης.

Τι δεν θα σου πει: αριθμούς που δεν έχουμε, επίθετα όπως «ιδανικό», ούτε όσα γράφει ήδη η
κάρτα χωρίς σύγκριση. Αν κάτι λείπει, το λέει («δεν το ξέρω από τα δεδομένα») και σου λέει
πώς να το μάθεις, π.χ. ζήτα από τον μεσίτη το ενεργειακό πιστοποιητικό, το μισθωτήριο, την
οικοδομική άδεια. Ελέγχουμε κάθε αριθμό της απάντησης. Αν κάποιος δεν υπάρχει στα στοιχεία
μας, τον σημειώνουμε με «(έλεγξε: …)».
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from datetime import date, datetime

from scout import picks
from scout.area_insights import area_name

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 400  # «Ρώτα με» answers
BRIEF_MAX_TOKENS = 700  # Greek runs ~3 tokens a word; 120 words + headroom, never cut mid-line
# Sampling: the API rejects ``temperature`` for this model family (400 «Extra inputs are not
# permitted»), so determinism comes from low effort and thinking off instead.
OUTPUT_CONFIG = {"effort": "low"}
THINKING_OFF = {"type": "between_tools"}  # this model's spelling of "no thinking" (no tools)
MAX_LISTINGS = 10
SELLER_TEXT_CHARS = 300
HISTORY_TURNS = 6  # question + answer pairs kept per panel
TOLERANCE = 0.01  # ±1 % for the grounding check
LOAN_SHARE, LOAN_RATE, LOAN_YEARS = 0.70, 0.04, 25  # spec §1 step 1

SUGGESTIONS = (
    "Γιατί αυτό και όχι το φθηνότερο;",
    "Τι να προσέξω στη διαπραγμάτευση;",
    "Τι ρίσκο έχει αυτή η περιοχή;",
    "Πόσο θα νοικιάσει;",
)
UNKNOWN = "δεν το ξέρω από τα δεδομένα"

_STR_TEXT = {
    "FROZEN": "δεν επιτρέπεται νέα βραχυχρόνια μίσθωση (πάγωμα κέντρου Αθήνας, ν. 5170/2025)",
    "EXPANDING_RISK": "επιτρέπεται σήμερα, κίνδυνος επέκτασης του παγώματος",
    "ALLOWED": "επιτρέπεται σήμερα (με ΑΜΑ)",
}
_DOM_BASIS = {"listed": "από την ημερομηνία ανάρτησης", "seen": "από την πρώτη φορά που την είδαμε"}


def model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)


def _api_key() -> str:
    from scout.config import get_settings

    return get_settings().anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")


def enabled() -> bool:
    return bool(_api_key())


# ---- facts --------------------------------------------------------------------------------


def _r1(x: float | None) -> float | None:
    return None if x is None else round(float(x), 1)


def _pct(x: float | None) -> float | None:
    """0.0473 → 4.7 (percent, one decimal)."""
    return None if x is None else round(float(x) * 100, 1)


def _day(v) -> str | None:
    return v.date().isoformat() if isinstance(v, datetime) else v.isoformat() if v else None


def _status(d: dict) -> str:
    if d.get("is_unfinished"):
        return "Υπό κατασκευή"
    if d.get("page_checked"):
        when = d.get("page_checked_at")
        return "Ελέγχθηκε η περιγραφή" + (f" στις {_day(when)}" if when else "")
    return "Δεν έχει ελεγχθεί ακόμα"


def offer(d: dict) -> dict:
    """The opening offer and why: −3 %, −3 % more at ≥90 days on market, −2 % private seller
    (the same rule as ``picks._build``)."""
    dom = d.get("days_on_market") or 0
    why = ["−3 % από την τιμή"]
    cut = 0.03
    if dom >= 90:
        cut += 0.03
        why.append(f"−3 % ακόμα, γιατί είναι {dom} μέρες στην αγορά")
    if d.get("is_private_seller"):
        cut += 0.02
        why.append("−2 % γιατί πουλά ιδιώτης")
    return {"eur": picks._r(d["price"] * (1 - cut), 1000), "cut_pct": _pct(cut), "why": why}


def _instalment(principal: float) -> int:
    r, n = LOAN_RATE / 12, LOAN_YEARS * 12
    return round(principal * r / (1 - (1 + r) ** -n))


def _listing(item, intel, rents: dict | None, year: int, loan: bool) -> dict:
    p = item if isinstance(item, picks.Pick) else None
    d = p.listing if p else item
    price, m2 = d.get("price"), d.get("area_m2")
    ppm = d.get("price_per_m2") or (price / m2 if price and m2 else None)
    f: dict = {
        "id": f"{d.get('source')}:{d.get('source_id')}",
        "price_eur": price,
        "area_m2": m2,
        "eur_per_m2": round(ppm) if ppm else None,
        "floor": d.get("floor"),
        "year_built": d.get("year_built"),
        "renovated_year": d.get("renovated_year"),
        "bedrooms": d.get("bedrooms"),
        "area": area_name(d.get("neighborhood")),
        "neighborhood": d.get("neighborhood"),
        "station": (p.station if p else picks.station(d)),
        "status": _status(d),
        "photo_count": d.get("photo_count"),
        "energy_class": (d.get("energy_class") or "").strip() or None,
        "private_seller": bool(d.get("is_private_seller")),
        "source": d.get("source"),
    }
    # Rent: the one stored figure (picks.listing_rent); ``rents`` only names its basis.
    basis = rents is not None and price and m2 and picks.rent_basis(d, rents)
    if p:
        f["rent"] = {"eur_month": p.rent, "low": p.rent_low, "high": p.rent_high}
        f["gross_yield_pct"], f["net_yield_pct"] = _pct(p.gross), _pct(p.net)
    elif d.get("est_monthly_rent"):
        f["rent"] = {"eur_month": picks._r(d["est_monthly_rent"], 10)}
        f["gross_yield_pct"], f["net_yield_pct"] = _pct(d.get("gross_yield")), _pct(
            d.get("net_yield")
        )
    if f.get("rent"):
        if basis:
            per_m2, n, where = basis
            f["rent"]["basis"] = (
                f"ζητούμενα ενοίκια XE στη «{where}»: {round(per_m2, 1)} €/τ.μ./μήνα"
                + (f" ({n} αγγελίες)" if n else "")
                + f" × {m2:g} τ.μ."
            )
        elif d.get("rent_estimated", True):
            f["rent"]["basis"] = "εκτίμηση από ζητούμενα ενοίκια XE της περιοχής × τ.μ."
        else:
            f["rent"]["basis"] = "ενοίκιο που δηλώνει η αγγελία"
        f["rent"]["kind"] = "ζητούμενα ενοίκια, όχι συμβόλαια"
    if d.get("days_on_market") is not None:
        f["days_on_market"] = {
            "days": d["days_on_market"],
            "basis": _DOM_BASIS.get(d.get("dom_basis"), "άγνωστη βάση"),
        }
    cmp = intel.comps(d) if intel is not None else None
    if cmp:
        f["comps"] = {
            "median_eur_per_m2": round(cmp["ppm"]),
            "n": cmp["n"],
            "vs_median_pct": _pct(cmp["pct"]),
            "compared_with": cmp["label"],
        }
    first = d.get("first_price")
    if first and price and first > price:
        f["price_history"] = {
            "first_price_eur": first,
            "drop_eur": first - price,
            "drop_pct": _pct(1 - price / first),
        }
    if price:
        f["opening_offer"] = offer(d)
        if loan:
            principal = price * LOAN_SHARE
            pay = _instalment(principal)
            f["loan"] = {"amount_eur": round(principal), "monthly_eur": pay}
            if f.get("rent"):
                f["loan"]["rent_minus_instalment_eur"] = f["rent"]["eur_month"] - pay
    from scout.regulatory import str_legality

    s = str_legality(d.get("neighborhood")).status
    if s in _STR_TEXT:
        f["short_term_rental"] = _STR_TEXT[s]
    if text := picks.excerpt(d.get("description"), SELLER_TEXT_CHARS):
        f["seller_text"] = text
    missing = [
        label
        for key, label in (
            ("energy_class", "ενεργειακή κλάση"),
            ("year_built", "έτος κατασκευής"),
            ("floor", "όροφος"),
            ("rent", "ενοίκιο"),
            ("comps", "παρόμοια"),
        )
        if f.get(key) is None
    ]
    if missing:
        f["missing"] = missing
    return {k: _plain(v) for k, v in f.items() if v is not None}


# AreaInsight field → (fact key, kind). "pct" = a fraction shown as percent.
_AREA_FIELDS = {
    "area": ("area", None),
    "n_fresh": ("active_listings", None),
    "median_ppm": ("median_eur_per_m2", "int"),
    "trend_pct": ("eur_per_m2_trend_pct", "pct"),
    "trend_early_ppm": ("trend_from_eur_per_m2", "int"),
    "trend_late_ppm": ("trend_to_eur_per_m2", "int"),
    "median_dom": ("median_days_on_market", "int"),
    "cut_share": ("share_with_price_cut_pct", "pct"),
    "rent_ppm": ("rent_eur_per_m2_month", "r1"),
    "rent_samples": ("rent_listings", None),
    "gross_yield": ("gross_yield_pct", "pct"),
    "gross_yield_new": ("gross_yield_new_builds_pct", "pct"),
    "yield_rank": ("yield_rank", None),
    "yield_of": ("yield_rank_of", None),
    "ppm_new": ("new_builds_eur_per_m2", "int"),
    "ppm_old": ("older_16y_plus_eur_per_m2", "int"),
    "new_premium": ("new_build_premium_pct", "pct"),
    "old_share": ("share_over_30y_pct", "pct"),
    "stations": ("stations", None),
}
_AREA_SKIP = {
    "why", "reasons", "risks", "components", "score", "n_recent", "median_ppm_recent",
    "trend_early_n", "trend_late_n", "value_band", "value_band_discount", "good_stock",
    "unknown_age_share", "n_new", "n_old", "uc_unfinished", "uc_checked", "median_cut_pct",
    "near_station_in_budget", "near_station_in_budget_checked",
}  # fmt: skip


def _plain(v):
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v, 3) if abs(v) < 1 else round(v, 1)
    return v


def _area(x) -> dict:
    """An AreaInsight (or a dict) as plain facts with self-explaining keys. Fields this module
    does not know (round-3 additions: trend by month, liquidity, Line 4 …) pass through under
    their own name when they are JSON-able."""
    raw = dataclasses.asdict(x) if dataclasses.is_dataclass(x) else dict(x)
    out: dict = {}
    for k, v in raw.items():
        if k in _AREA_SKIP or v is None or v == [] or v == "":
            continue
        name, kind = _AREA_FIELDS.get(k, (k, None))
        if kind == "pct":
            v = _pct(v)
        elif kind == "int":
            v = round(v)
        elif kind == "r1":
            v = _r1(v)
        try:
            json.dumps(v, default=None)
        except TypeError:
            continue
        out[name] = _plain(v)
    if raw.get("uc_checked"):
        out["under_construction_share_pct"] = _pct(raw.get("uc_unfinished", 0) / raw["uc_checked"])
        out["under_construction_of_checked_new_builds"] = raw["uc_checked"]
    return out


def facts_for(
    listings: list,
    intel,
    area_rank=None,
    answers: dict | None = None,
    *,
    rent_rows: list[dict] | None = None,
    year: int | None = None,
) -> dict:
    """Compact, JSON-able facts for the assistant: up to MAX_LISTINGS listings (listing dicts
    or ``picks.Pick``), in the given order, the areas they are in, and the buyer's answers.
    No free text except the seller's own description, cut to SELLER_TEXT_CHARS."""
    answers = dict(answers or {})
    year = year or date.today().year
    rents = picks.rent_index(rent_rows) if rent_rows else None
    loan = bool(answers.get("loan"))
    rows = [_listing(x, intel, rents, year, loan) for x in listings[:MAX_LISTINGS]]
    if rows and rows[0].get("price_eur"):
        top = rows[0]
        for r in rows[1:]:
            if r.get("price_eur"):
                r["vs_first"] = {"price_diff_eur": r["price_eur"] - top["price_eur"]}
                if r.get("gross_yield_pct") is not None and top.get("gross_yield_pct") is not None:
                    r["vs_first"]["gross_yield_diff_pts"] = round(
                        r["gross_yield_pct"] - top["gross_yield_pct"], 1
                    )
    compare = _compare(rows[:3])
    wanted = {r.get("area") for r in rows}
    areas = [_area(x) for x in (area_rank or [])]
    areas = [a for a in areas if not wanted - {None} or a.get("area") in wanted]
    buyer = {
        k: answers[k]
        for k in ("budget", "goal", "loan", "where", "areas", "max_age", "bedrooms")
        if answers.get(k) not in (None, "", [])
    }
    if loan:
        buyer["loan_terms"] = {
            "share_pct": _pct(LOAN_SHARE),
            "rate_pct": _pct(LOAN_RATE),
            "years": LOAN_YEARS,
        }
    out = {"today": date.today().isoformat(), "buyer": buyer, "listings": rows, "areas": areas}
    if compare:
        out["top3_compare"] = compare
    return out


def _compare(rows: list[dict]) -> dict:
    """Which of #1–#3 is highest/lowest on each number, so the model never has to rank."""
    measures = {
        "gross_yield_pct": lambda r: r.get("gross_yield_pct"),
        "price_eur": lambda r: r.get("price_eur"),
        "comps_n": lambda r: (r.get("comps") or {}).get("n"),
        "days_on_market": lambda r: (r.get("days_on_market") or {}).get("days"),
    }
    out = {}
    for name, get in measures.items():
        have = [(get(r), i) for i, r in enumerate(rows, 1) if get(r) is not None]
        if len(have) >= 2:
            out[name] = {"highest": f"#{max(have)[1]}", "lowest": f"#{min(have)[1]}"}
    return out


def facts_hash(facts: dict, question: str = "") -> str:
    blob = json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str) + "\n" + question
    return hashlib.sha256(blob.encode()).hexdigest()


# ---- prompts ------------------------------------------------------------------------------

RULES = f"""Είσαι έμπειρος μεσίτης της Αθήνας. Κάθεσαι απέναντι από έναν αγοραστή 65 \
ετών που αγοράζει ΕΝΑ διαμέρισμα στη ΒΑ Αθήνα για να το νοικιάσει μακροχρόνια. Του μιλάς \
απλά, όπως στο τραπέζι: μία ιδέα σε κάθε πρόταση, πρώτα ο αριθμός και μετά ο λόγος.

Κανόνες (αυστηροί):
1. Χρησιμοποίησε ΜΟΝΟ αριθμούς που υπάρχουν αυτούσιοι στο JSON. Μην υπολογίζεις νέους \
(διαφορές, μέσους όρους, ποσοστά)· οι διαφορές από το #1 είναι ήδη στο vs_first και η \
προσφορά στο opening_offer.
2. Αν τα δεδομένα δεν το λένε, γράψε «{UNKNOWN}» και πες πώς μαθαίνεται: ενεργειακό \
πιστοποιητικό από τον μεσίτη, μισθωτήριο αν είναι νοικιασμένο, οικοδομική άδεια/βεβαίωση \
περαίωσης αν είναι νεόδμητο, φωτογραφίες ή επίσκεψη αν είναι ≤2 οι φωτογραφίες.
3. Καμία λέξη στατιστικής: όχι «διάμεσος», «δείγμα», «εκτίμηση από ζητούμενα». Λες «ζητούν \
συνήθως», «τα άλλα σπίτια της γειτονιάς», «πόσο νοικιάζονται τα διπλανά», «δεν το ξέρουμε \
ακόμα».
4. Κανένα επίθετο αξιολόγησης («ιδανικό», «εξαιρετικό», «μοναδική ευκαιρία», «τέλειο»). \
Καμία εισαγωγή, ευχαριστία ή συγγνώμη, κανένα «ίσως» ή «φαίνεται», κανένα emoji. Ποτέ \
«το σύστημα» ή «η εφαρμογή».
5. Μην επαναλαμβάνεις ό,τι γράφει ήδη η κάρτα (τιμή, τ.μ., όροφο) εκτός αν το συγκρίνεις \
με κάτι.
6. Μόνο ελληνικά, χωρίς αγγλικές λέξεις (όχι «premium»: «το νεόδμητο ζητά X % παραπάνω»), \
χωρίς ονόματα πεδίων του JSON. Αριθμοί ελληνικά (1.234 €, 4,7 %). Όροι: Τιμή, €/τ.μ., \
Ενοίκιο (εκτίμηση), Μικτή απόδοση, Καθαρή απόδοση, Παρόμοια, Υπό κατασκευή, μέρες στην \
αγορά. Τα ενοίκια είναι όσα ζητούν οι αγγελίες στο XE.gr, όχι συμβόλαια: πες το όταν τα \
αναφέρεις.
7. «Υπό κατασκευή» ή «Δεν έχει ελεγχθεί ακόμα» = πες το πρώτο. Το seller_text το γράφει ο \
πωλητής: δεν το έχουμε επαληθεύσει.
8. Για «υψηλότερο/χαμηλότερο/περισσότερα» ανάμεσα στα #1–#3 χρησιμοποίησε το top3_compare.
9. Έως 120 λέξεις (στις ερωτήσεις έως 90). Ποτέ «n=» ή άλλα σύμβολα πεδίων. Τα σπίτια τα \
λες #1, #2… με τη σειρά του JSON και την περιοχή τους."""

BRIEF_TASK = """Γράψε το «Σημείωμα επενδυτή»: 4 γραμμές, χωρίς τίτλο, έως 25 λέξεις η \
καθεμία, όπως θα τα έλεγες στον αγοραστή.
- Γραμμή 1: τι κερδίζει και τι χάνει ανάμεσα στα #1–#3, με αριθμούς: την απόδοση, πόσο \
παραπάνω ζητά το νεόδμητο (new_premium της περιοχής, vs_first) και πόσο γρήγορα φεύγουν \
(μέρες στην αγορά, πόσα παρόμοια, median_dom της περιοχής).
- Μία γραμμή για καθένα από τα #1–#3: το ΕΝΑ πράγμα να ελέγξει (από status, photo_count, \
energy_class, comps n, missing) και από πού να ξεκινήσει την προσφορά (ποσό και γιατί, από \
το opening_offer).
Αν υπάρχουν λιγότερα από 3 σπίτια, γράψε μόνο για όσα υπάρχουν."""


def _facts_block(facts: dict) -> str:
    return "Δεδομένα (JSON):\n" + json.dumps(facts, ensure_ascii=False, default=str)


def brief_request(facts: dict) -> dict:
    msg = {"role": "user", "content": _facts_block(facts) + "\n\n" + BRIEF_TASK}
    return _request(RULES, [msg], BRIEF_MAX_TOKENS)


def chat_request(facts: dict, question: str, history: list[dict] | None = None) -> dict:
    """The facts go in the system prompt (stable across turns), then the last turns."""
    past = (history or [])[-2 * HISTORY_TURNS :]
    msgs = [{"role": m["role"], "content": m["content"]} for m in past]
    msgs.append({"role": "user", "content": question})
    return _request(RULES + "\n\n" + _facts_block(facts), msgs)


def _request(system: str, messages: list[dict], max_tokens: int = MAX_TOKENS) -> dict:
    return {
        "model": model(),
        "max_tokens": max_tokens,
        "output_config": OUTPUT_CONFIG,
        "thinking": THINKING_OFF,
        "system": system,
        "messages": messages,
    }


# ---- grounding ----------------------------------------------------------------------------

# 1.234.567 / 1.234,5 / 4,7 / 4.7 / 300 — then an optional unit.
_NUM = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)\s*(%|€|ευρώ|χιλ\.?|k\b)?",
    re.IGNORECASE,
)


def _parse(tok: str) -> tuple[float, float]:
    """(value, half a unit of the last written digit)."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", tok):
        tok = tok.replace(".", "")
    tok = tok.replace(",", ".")
    decimals = len(tok.split(".")[1]) if "." in tok else 0
    return float(tok), 0.5 * 10**-decimals


def _fact_numbers(obj, out: list[float]) -> list[float]:
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(abs(float(obj)))
        if abs(obj) < 1:
            out.append(abs(float(obj)) * 100)
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            out.append(_parse(m.group(1))[0])
        out.extend(float(y) for y in re.findall(r"\d{4}", obj))  # dates: 2026-10-31
    elif isinstance(obj, dict):
        for v in obj.values():
            _fact_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _fact_numbers(v, out)
    return out


def ungrounded_numbers(answer: str, facts: dict) -> list[str]:
    """Numbers in ``answer`` that are not in ``facts`` (±1 %, or the rounding of the digits
    written). Bare integers under 10 without a unit are ignored (#1, «τα 3», Γραμμή 2)."""
    known = _fact_numbers(facts, [])
    bad: list[str] = []
    for m in _NUM.finditer(answer):
        tok, unit = m.group(1), (m.group(2) or "").lower()
        value, half = _parse(tok)
        if unit.startswith("χιλ") or unit == "k":
            value, half = value * 1000, half * 1000
        if not unit and value < 10 and half == 0.5:
            continue
        if m.start() > 0 and answer[m.start() - 1] == "#":
            continue
        if not any(abs(value - k) <= max(TOLERANCE * k, half) for k in known):
            bad.append(m.group(0).strip())
    return list(dict.fromkeys(bad))


def checked(answer: str, facts: dict) -> str:
    """``answer`` with «(έλεγξε: X, Y)» appended when it quotes numbers we do not have."""
    bad = ungrounded_numbers(answer, facts)
    return answer if not bad else f"{answer.rstrip()} (έλεγξε: {', '.join(bad)})"


# ---- model calls --------------------------------------------------------------------------

_LOCAL_CACHE: dict[str, str] = {}


def _cache() -> dict:
    import streamlit as st

    if not st.runtime.exists():  # scripts, tests
        return _LOCAL_CACHE
    return st.session_state.setdefault("_assistant_cache", {})


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=_api_key())


def _text(resp) -> str:
    """The reply's text; when it hit max_tokens, cut back to the last complete line or
    sentence so a half-sentence never reaches the screen."""
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if getattr(resp, "stop_reason", None) == "max_tokens" and text:
        cut = max(text.rfind("\n"), text.rfind(". "), text.rfind("· "))
        text = text[: cut + 1].strip() if cut > 0 else text
    return text


def brief(facts: dict, client=None) -> str | None:
    """The 4–5 line «Σημείωμα επενδυτή», grounding-checked; None without a key, without
    listings, or when the API fails. Cached by sha256 of the facts."""
    if not facts.get("listings") or (client is None and not enabled()):
        return None
    cache, key = _cache(), "brief:" + facts_hash(facts)
    if key not in cache:
        try:
            resp = (client or _client()).messages.create(**brief_request(facts))
        except Exception:
            return None
        text = _text(resp)
        if not text:
            return None
        cache[key] = checked(text, facts)
    return cache[key]


def ask(facts: dict, question: str, history: list[dict] | None = None, client=None) -> str:
    """One grounded answer (no streaming), cached per (question, facts)."""
    cache, key = _cache(), "ask:" + facts_hash(facts, question)
    if key not in cache:
        resp = (client or _client()).messages.create(**chat_request(facts, question, history))
        cache[key] = checked(_text(resp) or UNKNOWN, facts)
    return cache[key]


# ---- UI -----------------------------------------------------------------------------------


def panel(facts: dict, key: str) -> None:
    """«Ρώτα με»: suggestion chips + a question box, the conversation kept per ``key``.
    Renders nothing when ANTHROPIC_API_KEY is not set."""
    if not enabled() or not facts.get("listings"):
        return
    import streamlit as st

    turns_key, chip_key = f"assistant_turns_{key}", f"assistant_chip_{key}"
    pending_key = f"assistant_pending_{key}"
    turns: list[dict] = st.session_state.setdefault(turns_key, [])

    def _chip() -> None:  # a chip is a one-shot question, not a sticky selection
        st.session_state[pending_key] = st.session_state.get(chip_key)
        st.session_state[chip_key] = None

    with st.container(border=True):
        st.markdown("**Ρώτα με**")
        for m in turns:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
        st.pills(
            "Προτάσεις",
            SUGGESTIONS,
            key=chip_key,
            on_change=_chip,
            label_visibility="collapsed",
        )
        typed = st.chat_input("Ρώτα με", key=f"assistant_input_{key}")
        question = typed or st.session_state.pop(pending_key, None)
        if question:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                answer = _answer_streaming(st, facts, question, turns)
            turns.extend(
                [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
            )
            del turns[: max(0, len(turns) - 2 * HISTORY_TURNS)]
        with st.expander("Πώς δουλεύει"):
            st.markdown(__doc__.split("\n", 2)[2])


def _answer_streaming(st, facts: dict, question: str, turns: list[dict]) -> str:
    cache, ckey = _cache(), "ask:" + facts_hash(facts, question)
    if ckey in cache:
        st.markdown(cache[ckey])
        return cache[ckey]
    box, text = st.empty(), ""
    try:
        with _client().messages.stream(**chat_request(facts, question, turns)) as stream:
            for chunk in stream.text_stream:
                text += chunk
                box.markdown(text + " ▌")
            final = stream.get_final_message()
    except Exception:  # one plain line; an exception class name means nothing to a buyer
        msg = "Ο βοηθός δεν απάντησε αυτή τη φορά. Δοκίμασε ξανά."
        box.caption(msg)
        return msg
    out = checked(_text(final) or UNKNOWN, facts)
    box.markdown(out)  # trimmed at a full sentence if it ran out of room, plus «(έλεγξε: …)»
    cache[ckey] = out
    return out
