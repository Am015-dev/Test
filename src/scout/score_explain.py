"""Human-readable "why this score" breakdown.

Pure and dependency-light: turns a listing's already-computed scoring signals into
an ordered list of ``{label, effect, detail}`` rows so a person can see *why* a
listing scored the way it did. It EXPLAINS the exact logic in ``scoring.py`` — the
same weighted signals (undervaluation vs the area model, rental yield, newness,
energy class, metro proximity) and, crucially, the same "renormalize over the
signals we actually know" honesty: a signal we couldn't evaluate for this listing
(no scraped energy/year, an imputed rent, a centroid-only location) is reported as
``"unknown"`` and explicitly *not scored* — never dressed up as a positive.

It invents no new signals and reuses ``scoring``'s public helpers / band constants
so the wording can never drift from what the score was actually computed on.
"""

from __future__ import annotations

from .config import ScoringReference
from .scoring import _ENERGY_SCORE, energy_class_score, newness_score

# The scoring bands the live engine uses (strategy.yaml overrides these at runtime, but
# the defaults are the honest reference for an explanation that doesn't carry a Strategy).
_REF = ScoringReference()

# Energy classes at/above this 0..1 score read as an asset (efficient, future-proof);
# below it they're a holding liability under the EU EPBD. C (0.6) is the break-even.
_ENERGY_GOOD = 0.6
# Newness 0..1 above this reads as modern stock; below it as older/dated.
_NEWNESS_GOOD = 0.5

Row = dict[str, str]

# Display text is Greek; the ``effect`` codes ("positive"/"negative"/"unknown") stay English.
_NOT_SCORED = "εκτός σκορ, δεν βαθμολογείται ως 0."


def _row(label: str, effect: str, detail: str) -> Row:
    return {"label": label, "effect": effect, "detail": detail}


def _undervaluation_row(d: dict) -> Row:
    """Mirrors ``_undervaluation_signal``: prefers the hedonic ``value_gap_pct`` (fraction,
    +ve = priced below the model's fair value). Absent → unknown, not scored."""
    gap = d.get("value_gap_pct")
    if gap is None:
        return _row(
            "Η υποτίμηση δεν εκτιμήθηκε",
            "unknown",
            f"Δεν υπάρχει εκτίμηση αξίας από το μοντέλο — {_NOT_SCORED}",
        )
    pct = round(gap * 100)
    if gap > 0:
        return _row(
            f"Τιμή {pct}% κάτω από το μοντέλο περιοχής",
            "positive",
            "Απόκλιση από την εκτιμώμενη αξία· στο "
            f"{round(_REF.target_undervaluation * 100)}% κάτω παίρνει πλήρη βαθμό.",
        )
    return _row(
        f"Τιμή {abs(pct)}% πάνω από το μοντέλο περιοχής" if gap < 0 else "Στην τιμή του μοντέλου",
        "negative",
        "Η ζητούμενη τιμή είναι ίση ή πάνω από την εκτιμώμενη αξία — καμία υποτίμηση.",
    )


def _yield_row(d: dict) -> Row:
    """Mirrors ``_yield_signal`` + the ``yield_known`` gate: a yield only counts when it
    comes from a REAL rent. An imputed/estimated rent (``rent_estimated``) makes gross
    yield a deterministic inverse of €/m², so it's reported unknown — never a positive."""
    # Match the Listing default: rent is treated as estimated unless proven otherwise.
    rent_estimated = d.get("rent_estimated", True)
    net = d.get("net_yield")
    gross = d.get("gross_yield")

    if rent_estimated:
        return _row(
            "Απόδοση από εκτιμώμενο ενοίκιο",
            "unknown",
            "Το ενοίκιο είναι εκτίμηση, όχι πραγματικό συγκρίσιμο — η απόδοση δεν βαθμολογείται.",
        )
    if net is not None:
        pct = round(net * 100, 1)
        # yield_percentile (set by relative_value.annotate_relative_value, when the pool
        # was annotated) is area-relative and mirrors what _yield_signal now scores on —
        # prefer it over the flat national floor so the explanation never contradicts the
        # score. Falls back to the flat floor when there aren't enough local peers to rank.
        local_pct = d.get("yield_percentile")
        if local_pct is not None:
            effect = "positive" if local_pct >= 0.5 else "negative"
            detail = (
                "Μετά από κόστη αγοράς/κατοχής και κενότητα — καλύτερη από το "
                f"{round(local_pct * 100)}% των συγκρίσιμων αγγελιών της περιοχής."
            )
        else:
            effect = "positive" if net >= _REF.net_yield_floor else "negative"
            detail = "Μετά από κόστη αγοράς/κατοχής και κενότητα — η πραγματική απόδοση."
        return _row(f"Καθαρή απόδοση {pct}%", effect, detail)
    if gross:
        pct = round(gross * 100, 1)
        effect = "positive" if gross >= _REF.yield_floor else "negative"
        return _row(
            f"Μικτή απόδοση {pct}%",
            effect,
            "Μικτή (δεν υπάρχει καθαρή) — υπερεκτιμά ό,τι μένει τελικά στον επενδυτή.",
        )
    return _row(
        "Η απόδοση δεν υπολογίστηκε",
        "unknown",
        f"Δεν υπάρχει ενοίκιο για να βγει απόδοση — {_NOT_SCORED}",
    )


def _newness_row(d: dict) -> Row:
    """Mirrors ``_newness_signal``/``newness_score``: newness from the later of build /
    renovation year. Neither reported → unknown, not scored."""
    yb = d.get("year_built")
    ry = d.get("renovated_year")
    if not (yb or ry):
        return _row(
            "Δεν δηλώνεται έτος κατασκευής",
            "unknown",
            f"Ούτε έτος κατασκευής ούτε ανακαίνισης — {_NOT_SCORED}",
        )
    year = max(y for y in (yb, ry) if y)
    val = newness_score(yb, ry, _REF)
    kind = "ανακαίνιση" if ry and ry >= (yb or 0) else "κατασκευή"
    band = f"{_REF.build_year_floor}-{_REF.build_year_ceiling}"
    if val >= _NEWNESS_GOOD:
        return _row(
            f"Σύγχρονο ακίνητο ({kind} {year})",
            "positive",
            f"Νεότερο από τη μέση της κλίμακας παλαιότητας {band}.",
        )
    return _row(
        f"Παλαιότερο ακίνητο ({kind} {year})",
        "negative",
        f"Κάτω από τη μέση της κλίμακας παλαιότητας {band}.",
    )


def _energy_row(d: dict) -> Row:
    """Mirrors ``_energy_signal``/``energy_class_score`` + the ``energy_known`` gate: an
    unknown/exempt class is dropped, not scored 0. Poor classes read as an EPBD liability."""
    ec = (d.get("energy_class") or "").strip()
    if not ec or ec.upper() not in _ENERGY_SCORE:
        return _row(
            "Δεν δηλώνεται ενεργειακή κλάση",
            "unknown",
            f"Καμία (ή εξαιρούμενη) ενεργειακή κλάση — {_NOT_SCORED}",
        )
    label = f"Ενεργειακή κλάση {ec.upper()}"
    if energy_class_score(ec) >= _ENERGY_GOOD:
        return _row(
            label,
            "positive",
            "Αποδοτική κλάση — ακριβότερο ενοίκιο και ασφαλής απέναντι στους κανόνες της ΕΕ.",
        )
    return _row(
        label,
        "negative",
        "Ενεργοβόρα κλάση — η υποχρεωτική ανακαίνιση EPBD / το κόστος αναβάθμισης ρίχνει το σκορ.",
    )


def _metro_row(d: dict) -> Row:
    """Mirrors ``_metro_proximity_signal`` + the ``metro_known`` gate: distance only scores
    when it's a real per-listing figure (``location_precision == 'exact'``). A centroid-only
    location gives one distance for a whole municipality, so it's reported unknown."""
    metro = d.get("metro_distance_m")
    if metro is None:
        return _row(
            "Άγνωστη απόσταση από μετρό",
            "unknown",
            "Η αγγελία δεν εντοπίστηκε — ούτε πόντοι ούτε ποινή για την εγγύτητα.",
        )
    if d.get("location_precision") != "exact":
        return _row(
            "Κατά προσέγγιση τοποθεσία",
            "unknown",
            "Μόνο το κέντρο της περιοχής, όχι το ακριβές σημείο — η εγγύτητα δεν βαθμολογείται.",
        )
    ceiling = _REF.metro_distance_ceiling_m
    if metro < ceiling:
        return _row(
            f"{int(metro)} m ως το μετρό",
            "positive",
            f"Εντός {ceiling} m με τα πόδια από μετρό (πιο κοντά = περισσότεροι πόντοι).",
        )
    return _row(
        f"{int(metro)} m ως το μετρό",
        "negative",
        f"Στο ή πέρα από το όριο των {ceiling} m — χωρίς μπόνους εγγύτητας στο μετρό.",
    )


def explain_score(d: dict) -> list[Row]:
    """Explain a listing's score as an ordered list of ``{label, effect, detail}`` rows.

    ``effect`` is one of ``"positive" | "negative" | "unknown"``. Row order follows the
    scoring engine's signal order (undervaluation, yield, newness, energy, metro). An
    unknown/imputed signal is honestly reported as ``"unknown"`` and flagged as not
    scored — never as a positive. An empty/falsy dict returns ``[]``.

    ``d`` uses the ``Listing`` field names: ``value_gap_pct``, ``net_yield``,
    ``gross_yield``, ``rent_estimated``, ``year_built``, ``renovated_year``,
    ``energy_class``, ``metro_distance_m``, ``location_precision`` (``score`` is used only
    by :func:`summarize_score`).
    """
    if not d:
        return []
    return [
        _undervaluation_row(d),
        _yield_row(d),
        _newness_row(d),
        _energy_row(d),
        _metro_row(d),
    ]


def summarize_score(d: dict) -> str:
    """A one-line summary: the score plus its strengths and concerns (unknowns omitted)."""
    if not d:
        return "Δεν υπάρχουν διαθέσιμα σήματα"
    rows = explain_score(d)
    strengths = [r["label"] for r in rows if r["effect"] == "positive"]
    concerns = [r["label"] for r in rows if r["effect"] == "negative"]

    score = d.get("score")
    head = f"Σκορ {round(float(score))}" if score is not None else "Χωρίς σκορ"
    parts = [head]
    if strengths:
        parts.append("δυνατά σημεία: " + ", ".join(strengths))
    if concerns:
        parts.append("αδυναμίες: " + ", ".join(concerns))
    if len(parts) == 1:
        return f"{head} — κανένα αξιοσημείωτο σήμα"
    return " — ".join(parts)
