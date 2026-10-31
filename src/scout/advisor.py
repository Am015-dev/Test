"""AI buying advisor: Claude reviews a search's top listings and gives an honest verdict each.

The ranking formula can't tell a 60-year-old flat or an unfinished shell from a bargain; this
module asks a capable model to judge the shortlist the way a skeptical Athens buying advisor
would. ``red_flags`` is the cheap deterministic part, shared by the prompt and the UI.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator

from scout.config import get_settings

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_REASON = 160
OLD_BUILDING_YEARS = 40

Label = Literal["Αξίζει", "Με επιφύλαξη", "Απόφυγε"]


class Verdict(BaseModel):
    key: str
    label: Label
    reason: str

    @field_validator("reason")
    @classmethod
    def _short(cls, v: str) -> str:
        v = " ".join(v.split())
        return v if len(v) <= MAX_REASON else v[: MAX_REASON - 1].rstrip() + "…"


class Review(BaseModel):
    summary: str
    verdicts: list[Verdict]


class AdvisorError(Exception):
    """The review could not be produced (message is Greek, shown to the user)."""


def key_of(d: dict) -> str:
    return f"{d.get('source')}:{d.get('source_id')}"


def _age(d: dict) -> int | None:
    if d.get("building_age") is not None:
        return int(d["building_age"])
    if d.get("year_built"):
        return date.today().year - int(d["year_built"])
    return None


def red_flags(d: dict) -> list[str]:
    """Short Greek warning tags from the listing's own data. Missing data is not a flag,
    except a missing build year (the single most important fact for an Athens flat)."""
    flags: list[str] = []
    age = _age(d)
    if age is None:
        flags.append("Χωρίς έτος κατασκευής")
    elif age >= OLD_BUILDING_YEARS and not d.get("renovated_year"):
        flags.append(f"Κτίριο {age} ετών")
    if d.get("is_unfinished"):
        flags.append("Ημιτελές")
    floor = d.get("floor")
    if floor is None:
        flags.append("Όροφος δεν δηλώνεται (συχνά ισόγειο)")
    elif floor < 0:
        flags.append("Υπόγειο")
    elif floor == 0:
        flags.append("Ισόγειο")
    if (d.get("energy_class") or "").strip().upper() in ("Η", "Ζ", "H", "Z"):
        flags.append(f"Ενεργειακή {d['energy_class'].strip().upper()}")
    ppm2, median = d.get("price_per_m2"), d.get("area_median_ppm2")
    if ppm2 and median and ppm2 < 0.6 * median:
        flags.append("Πολύ φθηνό για την περιοχή — έλεγξε γιατί")
    return flags


# Fields worth the model's attention (everything else is noise or internal scoring detail).
FIELDS = (
    "title",
    "neighborhood",
    "price",
    "area_m2",
    "price_per_m2",
    "area_median_ppm2",
    "comps_label",
    "comps_n",
    "comps_median_ppm2",
    "comps_p25_ppm2",
    "comps_p75_ppm2",
    "comps_pct",
    "same_flat_other_prices",
    "area_ppm2_by_age",
    "bedrooms",
    "floor",
    "year_built",
    "renovated_year",
    "building_age",
    "is_unfinished",
    "energy_class",
    "heating",
    "is_private_seller",
    "est_monthly_rent",
    "rent_estimated",
    "gross_yield",
    "days_on_market",
    "price_dropped",
    "first_price",
    "metro_distance_m",
    "location_precision",
    "nearest_metro",
    "deal_grade",
    "score",
)


def with_market(d: dict, adv: dict, intel) -> dict:
    """``d`` plus the market evidence the advisor should reason from (see ``market_intel``)."""
    out = dict(d)
    if cmp := adv.get("cmp"):
        out |= {
            "comps_label": cmp["label"],
            "comps_n": cmp["n"],
            "comps_median_ppm2": round(cmp["ppm"]),
            "comps_p25_ppm2": round(cmp["p25"]),
            "comps_p75_ppm2": round(cmp["p75"]),
            "comps_pct": round(cmp["pct"], 3),
        }
    if twins := adv.get("twins"):
        out["same_flat_other_prices"] = [t["price"] for t in twins]
    from scout.market_intel import municipality

    if table := intel.age_table(municipality(d)):
        out["area_ppm2_by_age"] = {r["band"]: round(r["ppm"]) for r in table}
    return out


def _compact(d: dict) -> dict:
    out: dict = {"key": key_of(d)}
    for f in FIELDS:
        v = d.get(f)
        if v is None or v == "":
            continue
        out[f] = round(v, 3) if isinstance(v, float) else v
    flags = red_flags(d)
    if flags:
        out["red_flags"] = flags
    return out


SYSTEM = """Είσαι έμπειρος, σκεπτικιστής σύμβουλος αγοράς κατοικίας στην Αθήνα (Β/ΒΑ προάστια). \
Ο πελάτης ΑΓΟΡΑΖΕΙ διαμέρισμα ως ΕΠΕΝΔΥΣΗ για να το ΝΟΙΚΙΑΣΕΙ μακροχρόνια. \
Κρίνεις κάθε αγγελία με ειλικρίνεια· προτιμάς να χάσει μια ευκαιρία παρά να αγοράσει πρόβλημα.

Κριτήρια (με αυτή τη σειρά βαρύτητας):
1. Ηλικία κτιρίου: κτίριο ≥40 ετών χωρίς δηλωμένη ανακαίνιση = πραγματικός κίνδυνος (παλιές \
υδραυλικές/ηλεκτρικές εγκαταστάσεις, χωρίς θερμομόνωση, αντισεισμικός κανονισμός πριν το 1985). \
Ανέφερε το έτος. Χωρίς ανακαίνιση δεν μπορεί να είναι «Αξίζει». Αν λείπει το έτος, γράψε \
«έτος δεν δηλώνεται» και μην δώσεις «Αξίζει» χωρίς άλλο ισχυρό στοιχείο.
2. Κατάσταση: ημιτελές/υπό κατασκευή → «Απόφυγε», εκτός αν ο αγοραστής το ζήτησε ρητά.
3. Όροφος: ισόγειο/υπόγειο/ημιυπόγειο είναι μειονέκτημα για κατοικία (υγρασία, ασφάλεια, φως).
4. Τιμή — κύρια απόδειξη τα comps_*: ομοειδή ακίνητα (ίδια περιοχή, ίδια ηλικία κτιρίου, \
παρόμοιο μέγεθος/όροφος· comps_label λέει ακριβώς με τι συγκρίθηκε, comps_n πόσα). comps_pct = \
πόσο πάνω (+) ή κάτω (−) από τη διάμεσο των ομοειδών· κάτω από comps_p25 = πραγματικά φθηνό \
για αυτό που είναι, πάνω από comps_p75 = ακριβό. Αν comps_n < 8 πες ότι το δείγμα είναι μικρό. \
area_ppm2_by_age δείχνει τη διάμεση €/τ.μ. ανά ηλικία στην περιοχή: χρησιμοποίησέ το για να \
πεις αν η ηλικία δικαιολογεί την τιμή (π.χ. 30ετές στην τιμή νεόδμητου = κακή αγορά). \
Μεγάλη «έκπτωση» (>25%) χωρίς εξήγηση είναι προειδοποίηση (υπόγειο, ιδιόκτητο οικόπεδο, \
νομικό θέμα, λάθος τ.μ.) — όχι ευκαιρία. Χωρίς comps, χρησιμοποίησε area_median_ppm2.
4β. same_flat_other_prices: το ίδιο σπίτι αγγελίεται κι από άλλους μεσίτες σε αυτές τις τιμές· \
ανέφερε τη χαμηλότερη — είναι το πραγματικό σημείο εκκίνησης της διαπραγμάτευσης.
5. Ενεργειακή κλάση (Η/Ζ = ακριβό σε θέρμανση και αναβάθμιση).
6. Διαπραγμάτευση: πολλές μέρες στην αγορά (days_on_market), μείωση από first_price, \
ιδιώτης πωλητής → περιθώριο· πρότεινε συγκεκριμένη τιμή προσφοράς μόνο αν τη στηρίζουν τα \
comps, ως ποσό σε € (π.χ. «προσφορά γύρω στις 205.000 €»).
6β. Ενοίκιο: est_monthly_rent = εκτίμηση μηνιαίου ενοικίου (αν rent_estimated = true είναι \
εκτίμηση από το διάμεσο ενοίκιο ανά τ.μ. της περιοχής, ΟΧΙ πραγματικό ενοίκιο — πες το). \
gross_yield = 12 × ενοίκιο ÷ τιμή (μικτή, πριν από φόρους/έξοδα). Ανέφερε την απόδοση μόνο ως \
εκτίμηση· ημιτελές ή υπό κατασκευή δεν νοικιάζεται χωρίς επιπλέον κεφάλαιο.
7. Ταίριασμα με το αίτημα: μέγεθος/υπνοδωμάτια/τιμή σε σχέση με όσα ζήτησε.

Το red_flags κάθε αγγελίας είναι ήδη επαληθευμένο από τα δεδομένα — λάβε το υπόψη.
Γράφεις για αγοραστή, όχι για προγραμματιστή: ΠΟΤΕ ονόματα πεδίων ή όρους όπως comps, p25, \
p75, n, value_confident — γράψε «παρόμοια σπίτια», «φθηνότερο από τα 3 στα 4 παρόμοια», «12 \
παρόμοια». Ποσά σε € με τελείες χιλιάδων.
metro_distance_m μετρά ΜΟΝΟ τις Γραμμές 2–3 (όχι τον ΗΣΑΠ/Γραμμή 1, ούτε τραμ/προαστιακό)· \
αν location_precision = "approx" η θέση είναι κατά προσέγγιση. Γι' αυτό μην γράφεις ποτέ ότι \
μια περιοχή «δεν έχει μετρό» — το πολύ «μακριά από τις Γραμμές 2–3».
Η ηλικία = building_age (έτη). «Νεόδμητο» λέγεται ΜΟΝΟ για κτίριο έως 5 ετών.
Κανόνες: να είσαι συγκεκριμένος με αριθμούς (έτος, €/τ.μ., % από διάμεσο, μέρες). ΜΗΝ \
επινοείς στοιχεία που δεν υπάρχουν στα δεδομένα (π.χ. ανακαίνιση, θέα, κατάσταση)· αν κάτι \
λείπει γράψε «δεν δηλώνεται». Ο τίτλος είναι μόνο τύπος + τ.μ., όχι περιγραφή. Αν τα \
υπνοδωμάτια δεν δηλώνονται, μην τα παρουσιάζεις ως γεγονός από τα τ.μ. (γράψε «πιθανώς»). \
«Αξίζει» μόνο όταν τα στοιχεία το στηρίζουν, όχι από προεπιλογή.

Απάντησε στα ελληνικά, ως JSON με:
- summary: 2–4 προτάσεις — τι αξίζει σε αυτά τα αποτελέσματα και γιατί, κύριοι κίνδυνοι.
- verdicts: ένα για ΚΑΘΕ αγγελία, με το ακριβές key της· reason έως 140 χαρακτήρες \
(σκληρό όριο), συγκεκριμένο."""


def _schema() -> dict:
    """Review's JSON schema, closed (additionalProperties: false) for structured outputs."""
    schema = Review.model_json_schema()
    for obj in [schema, *schema.get("$defs", {}).values()]:
        if obj.get("type") == "object":
            obj["additionalProperties"] = False
    return schema


def _payload(query: str, rows: list[dict]) -> str:
    listings = [_compact(d) for d in rows]
    ppm2 = [d["price_per_m2"] for d in rows if d.get("price_per_m2")]
    ctx = {"query": query, "today": date.today().isoformat()}
    if len(ppm2) >= 3:
        ctx["results_median_ppm2"] = round(statistics.median(ppm2))
    return json.dumps({"context": ctx, "listings": listings}, ensure_ascii=False)


def _parse(resp, sent: set[str]) -> Review | None:
    """The validated review, or None when the output is unusable (worth one retry)."""
    try:
        text = next(b.text for b in resp.content if b.type == "text")
        out = Review.model_validate_json(text)
    except Exception:  # no text block / bad JSON / schema mismatch
        return None
    out.verdicts = [v for v in out.verdicts if v.key in sent]
    return out if len(out.verdicts) * 2 >= len(sent) else None


def review(query: str, rows: list[dict], client=None, max_rows: int = 12) -> Review:
    rows = rows[:max_rows]
    if not rows:
        raise AdvisorError("Δεν υπάρχουν αγγελίες για αξιολόγηση.")
    if client is None:
        key = get_settings().anthropic_api_key
        if not key:
            raise AdvisorError("Λείπει το ANTHROPIC_API_KEY (βάλ'το στο .env ή στα secrets).")
        import anthropic

        client = anthropic.Anthropic(api_key=key)
    sent = {key_of(d) for d in rows}
    # Structured output (constrained JSON) rather than a tool call: Sonnet 5.5 rejects forced
    # tool_choice, and an unforced long tool call was seen garbling its own arguments.
    request = dict(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _schema()}},
        messages=[{"role": "user", "content": _payload(query, rows)}],
    )
    for _ in range(2):  # one retry on unusable output; the SDK already retries API errors
        try:
            resp = client.messages.create(**request)
        except Exception as e:
            raise AdvisorError(f"Ο σύμβουλος AI δεν είναι διαθέσιμος ({type(e).__name__}).") from e
        out = _parse(resp, sent)
        if out is not None:
            return out
    raise AdvisorError("Ο σύμβουλος AI δεν έδωσε έγκυρη αξιολόγηση. Δοκίμασε ξανά.")
