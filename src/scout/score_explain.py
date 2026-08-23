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


def _row(label: str, effect: str, detail: str) -> Row:
    return {"label": label, "effect": effect, "detail": detail}


def _undervaluation_row(d: dict) -> Row:
    """Mirrors ``_undervaluation_signal``: prefers the hedonic ``value_gap_pct`` (fraction,
    +ve = priced below the model's fair value). Absent → unknown, not scored."""
    gap = d.get("value_gap_pct")
    if gap is None:
        return _row(
            "Undervaluation not modeled",
            "unknown",
            "No hedonic value gap for this listing — dropped from the score, not scored as 0.",
        )
    pct = round(gap * 100)
    if gap > 0:
        return _row(
            f"Priced {pct}% below area model",
            "positive",
            f"Hedonic fair-value gap; {round(_REF.target_undervaluation * 100)}% below earns full credit.",
        )
    return _row(
        f"Priced {abs(pct)}% above area model" if gap < 0 else "At area-model price",
        "negative",
        "Asking price is at or above the model's fair value — no undervaluation.",
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
            "Yield from estimated rent",
            "unknown",
            "Rent is imputed, not a real comp — yield is not counted as a signal.",
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
                f"Net of Greek acquisition/holding costs and vacancy — better than "
                f"{round(local_pct * 100)}% of comparable listings in this area."
            )
        else:
            effect = "positive" if net >= _REF.net_yield_floor else "negative"
            detail = (
                "Net of Greek acquisition/holding costs and vacancy — the honest headline return."
            )
        return _row(f"{pct}% net yield", effect, detail)
    if gross:
        pct = round(gross * 100, 1)
        effect = "positive" if gross >= _REF.yield_floor else "negative"
        return _row(
            f"{pct}% gross yield",
            effect,
            "Gross (net yield unavailable) — overstates the return an investor keeps.",
        )
    return _row(
        "Yield not computed",
        "unknown",
        "No rent to derive a yield from — dropped from the score, not scored as 0.",
    )


def _newness_row(d: dict) -> Row:
    """Mirrors ``_newness_signal``/``newness_score``: newness from the later of build /
    renovation year. Neither reported → unknown, not scored."""
    yb = d.get("year_built")
    ry = d.get("renovated_year")
    if not (yb or ry):
        return _row(
            "Build year not reported",
            "unknown",
            "No build or renovation year — dropped from the score, not scored as 0.",
        )
    year = max(y for y in (yb, ry) if y)
    val = newness_score(yb, ry, _REF)
    kind = "renovated" if ry and ry >= (yb or 0) else "built"
    if val >= _NEWNESS_GOOD:
        return _row(
            f"Modern stock ({kind} {year})",
            "positive",
            f"Newer than the {_REF.build_year_floor}-{_REF.build_year_ceiling} newness band midpoint.",
        )
    return _row(
        f"Older stock ({kind} {year})",
        "negative",
        f"Below the {_REF.build_year_floor}-{_REF.build_year_ceiling} newness band midpoint.",
    )


def _energy_row(d: dict) -> Row:
    """Mirrors ``_energy_signal``/``energy_class_score`` + the ``energy_known`` gate: an
    unknown/exempt class is dropped, not scored 0. Poor classes read as an EPBD liability."""
    ec = (d.get("energy_class") or "").strip()
    if not ec or ec.upper() not in _ENERGY_SCORE:
        return _row(
            "Energy class not reported",
            "unknown",
            "No (or exempt) energy class — dropped from the score, not scored as 0.",
        )
    label = f"Energy class {ec.upper()}"
    if energy_class_score(ec) >= _ENERGY_GOOD:
        return _row(
            label, "positive", "Efficient class — rents higher and future-proof under EU rules."
        )
    return _row(
        label,
        "negative",
        "Inefficient class — EU EPBD renovation mandate / capex liability demotes the score.",
    )


def _metro_row(d: dict) -> Row:
    """Mirrors ``_metro_proximity_signal`` + the ``metro_known`` gate: distance only scores
    when it's a real per-listing figure (``location_precision == 'exact'``). A centroid-only
    location gives one distance for a whole municipality, so it's reported unknown."""
    metro = d.get("metro_distance_m")
    if metro is None:
        return _row(
            "Metro distance unknown",
            "unknown",
            "Listing couldn't be located — no proximity points, and not penalized either.",
        )
    if d.get("location_precision") != "exact":
        return _row(
            "Location approximate",
            "unknown",
            "Only an area centroid, not a per-listing point — proximity not scored.",
        )
    ceiling = _REF.metro_distance_ceiling_m
    if metro < ceiling:
        return _row(
            f"{int(metro)} m to metro",
            "positive",
            f"Within the {ceiling} m walk-to-metro band (closer = more points).",
        )
    return _row(
        f"{int(metro)} m to metro",
        "negative",
        f"At or beyond the {ceiling} m proximity ceiling — no walk-to-metro bonus.",
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
        return "No signals available"
    rows = explain_score(d)
    strengths = [r["label"] for r in rows if r["effect"] == "positive"]
    concerns = [r["label"] for r in rows if r["effect"] == "negative"]

    score = d.get("score")
    head = f"Score {round(float(score))}" if score is not None else "Unscored"
    parts = [head]
    if strengths:
        parts.append("strengths: " + ", ".join(strengths))
    if concerns:
        parts.append("concerns: " + ", ".join(concerns))
    if len(parts) == 1:
        return f"{head} — no notable signals"
    return " — ".join(parts)
