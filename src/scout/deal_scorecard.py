"""A transparent, Athens-calibrated point scorecard for a listing.

Inspired by the US "deal-analyzer 14-point scorecard" format investors like — a flat list
of yes/no/partial checks that sum to a headline number — but with **Greek** thresholds, not
US rules of thumb. It COMPLEMENTS ``investment.deal_grade`` (the A–D letter) rather than
replacing it: the grade is a fused judgement, this is the itemised, show-your-work tally a
buyer can read line by line.

Two honesty rules, enforced everywhere:

1. **Unknown never scores as good.** A check whose input is missing scores 0 and is labelled
   "unknown" in its ``note`` — we never assume a blank field is favourable.
2. **Imputed rent doesn't earn a yield point.** When ``rent_estimated`` is true the rent is a
   deterministic function of €/m², so the net-yield check scores 0 with an explicit note —
   the same gate ``score_explain`` applies.

All metric values are reused from ``metrics.investor_metrics`` (same Greek cost model), never
recomputed here. Pure function, no DB / network / Streamlit. Never raises on missing keys.
"""

from __future__ import annotations

from .metrics import investor_metrics

# Net-yield thresholds (fraction). Athens gross yields run ~4–6%, so a ~4.5% NET yield is a
# genuinely strong income return here — nothing like a US "1% rule".
_NET_YIELD_GOOD = 0.045
_NET_YIELD_OK = 0.035

# A modelled value gap this large is "significant" (matches deal_grade's 10% threshold).
_VALUE_GAP_SIGNIFICANT = 0.10

# Motivation tells (either is enough for the single point).
_MOTIVATED_NEGOTIATION = 45.0
_MOTIVATED_DOM = 180

# Energy classes an investor treats as efficient (no near-term EPBD retrofit liability).
_EFFICIENT_ENERGY = {"A", "B", "C"}

# Verdict cut-offs on the percentage score.
_STRONG_PCT = 70.0
_FAIR_PCT = 45.0


# Greek display labels for the checks and for investor_metrics' verdict codes. Labels and
# notes are display-only; the verdict codes ("good"/"ok"/"weak", "Strong"/"Fair"/"Pass")
# stay English because callers compare against them.
_L_NET_YIELD = "Καθαρή απόδοση"
_L_VALUE_GAP = "Απόκλιση από εκτιμώμενη αξία"
_L_MOTIVATED = "Πρόθυμος πωλητής"
_L_ENERGY = "Ενεργειακή απόδοση"
_METRIC_VERDICT_GR = {"good": "καλό", "ok": "μέτριο", "weak": "αδύναμο"}


def _check(label: str, points: int, max_points: int, note: str) -> dict:
    return {"label": label, "points": points, "max_points": max_points, "note": note}


def _pts_from_verdict(verdict: str | None) -> int:
    """Map an investor_metrics verdict ("good"/"ok"/"weak"/None) onto 2 / 1 / 0 points."""
    return {"good": 2, "ok": 1}.get(verdict or "", 0)


def _num(value) -> float | None:
    """Coerce to a finite float, or None — so a stray string/None never raises downstream."""
    try:
        if value is None:
            return None
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def _annual_rent(d: dict) -> float | None:
    """Monthly rent × 12, preferring the estimate the pipeline already put on the listing."""
    monthly = _num(d.get("est_monthly_rent")) or _num(d.get("listed_rent"))
    if monthly is None or monthly <= 0:
        return None
    return monthly * 12.0


def _net_yield_check(d: dict) -> dict:
    """Net yield — but only when it comes from a REAL rent. An imputed rent makes the yield a
    deterministic inverse of €/m², so it earns 0 with an honest note, never a positive."""
    # Match the Listing default: rent is treated as estimated unless proven otherwise.
    if d.get("rent_estimated", True):
        return _check(_L_NET_YIELD, 0, 2, "ενοίκιο κατ' εκτίμηση — η απόδοση δεν μετράει (0)")
    ny = _num(d.get("net_yield"))
    if ny is None:
        return _check(_L_NET_YIELD, 0, 2, "άγνωστο — δεν υπάρχει καθαρή απόδοση")
    pct = ny * 100
    if ny >= _NET_YIELD_GOOD:
        return _check(_L_NET_YIELD, 2, 2, f"{pct:.1f}% καθαρή — υψηλή για Αθήνα (≥4,5%)")
    if ny >= _NET_YIELD_OK:
        return _check(_L_NET_YIELD, 1, 2, f"{pct:.1f}% καθαρή — αποδεκτή (≥3,5%)")
    return _check(_L_NET_YIELD, 0, 2, f"{pct:.1f}% καθαρή — χαμηλή (<3,5%)")


def _metric_check(label: str, value: float | None, verdict: str | None, fmt: str) -> dict:
    """A generic 0/1/2 check off an investor_metrics value + its Athens-calibrated verdict."""
    if value is None or verdict is None:
        return _check(label, 0, 2, "άγνωστο — χρειάζεται πραγματικό ενοίκιο")
    pts = _pts_from_verdict(verdict)
    shown = _METRIC_VERDICT_GR.get(verdict, verdict)
    return _check(label, pts, 2, fmt.format(value=value, verdict=shown))


def _value_gap_check(d: dict) -> dict:
    """A modelled discount to fair value: ≥10% is a significant edge (2); any positive gap
    still earns partial credit (1); absent gap is unknown (0), never assumed favourable."""
    gap = _num(d.get("value_gap_pct"))
    if gap is None:
        return _check(_L_VALUE_GAP, 0, 2, "άγνωστο — δεν υπάρχει εκτίμηση αξίας από το μοντέλο")
    pct = gap * 100
    if gap >= _VALUE_GAP_SIGNIFICANT:
        return _check(_L_VALUE_GAP, 2, 2, f"{pct:.0f}% κάτω από το μοντέλο — σημαντικό (≥10%)")
    if gap > 0:
        return _check(_L_VALUE_GAP, 1, 2, f"{pct:.0f}% κάτω από το μοντέλο — μικρό")
    return _check(_L_VALUE_GAP, 0, 2, f"{pct:.0f}% — στο ή πάνω από το μοντέλο, χωρίς έκπτωση")


def _motivated_seller_check(d: dict) -> dict:
    """One point for a motivated seller: a high negotiation signal OR a long time on market."""
    neg = _num(d.get("negotiation_score"))
    dom = _num(d.get("days_on_market"))
    if neg is not None and neg >= _MOTIVATED_NEGOTIATION:
        return _check(_L_MOTIVATED, 1, 1, f"σκορ διαπραγμάτευσης {neg:.0f} (≥45)")
    if dom is not None and dom >= _MOTIVATED_DOM:
        return _check(_L_MOTIVATED, 1, 1, f"{dom:.0f} μέρες στην αγορά (≥180)")
    if neg is None and dom is None:
        return _check(_L_MOTIVATED, 0, 1, "άγνωστο — καμία ένδειξη κινήτρου")
    return _check(_L_MOTIVATED, 0, 1, "καμία ισχυρή ένδειξη κινήτρου")


def _energy_check(d: dict) -> dict:
    """One point for an energy-efficient class (A/B/C): no near-term EPBD retrofit liability."""
    ec = d.get("energy_class")
    if not ec or not isinstance(ec, str):
        return _check(_L_ENERGY, 0, 1, "άγνωστο — δεν δηλώνεται ενεργειακή κλάση")
    cls = ec.strip().upper()[:1]
    if cls in _EFFICIENT_ENERGY:
        return _check(_L_ENERGY, 1, 1, f"κλάση {cls} — αποδοτική (Α/Β/Γ)")
    return _check(_L_ENERGY, 0, 1, f"κλάση {cls} — θα χρειαστεί ενεργειακή αναβάθμιση")


def scorecard(d: dict) -> dict:
    """Score a listing on a transparent, Athens-calibrated point scorecard.

    ``d`` uses the ``Listing`` field names: ``price``, ``area_m2``, ``net_yield``,
    ``gross_yield``, ``listed_rent``, ``est_monthly_rent``, ``rent_estimated``,
    ``value_gap_pct``, ``days_on_market``, ``negotiation_score``, ``energy_class``,
    ``is_private_seller``. Every key is optional — missing inputs score 0 and read "unknown".

    Returns a dict::

        {
          "checks": [{"label", "points", "max_points", "note"}, ...],
          "points": int, "max_points": int, "pct": float, "verdict": str
        }

    ``verdict`` is "Strong" (pct ≥ 70), "Fair" (≥ 45) or "Pass". Never raises.
    """
    price = _num(d.get("price"))
    price = int(price) if price and price > 0 else None
    area_m2 = _num(d.get("area_m2"))
    annual_rent = _annual_rent(d)
    is_private = bool(d.get("is_private_seller", False))

    m = investor_metrics(price or 0, annual_rent, area_m2, is_private_seller=is_private)
    v = m["verdicts"]

    checks = [
        _net_yield_check(d),
        _metric_check(
            "Cap rate", m["cap_rate"], v["cap_rate"], "{value:.1%} καθαρό έσοδο/τιμή ({verdict})"
        ),
        _metric_check(
            "DSCR", m["dscr"], v["dscr"], "{value:.2f}× κάλυψη δόσης από ενοίκιο ({verdict})"
        ),
        _metric_check(
            "Πληρότητα νεκρού σημείου",
            m["break_even_occupancy"],
            v["break_even_occupancy"],
            "{value:.0%} πληρότητα για να μη χάνεις ({verdict})",
        ),
        _metric_check(
            "GRM", m["grm"], v["grm"], "{value:.1f}× τιμή / ετήσιο μικτό ενοίκιο ({verdict})"
        ),
        _value_gap_check(d),
        _motivated_seller_check(d),
        _energy_check(d),
    ]

    points = sum(c["points"] for c in checks)
    max_points = sum(c["max_points"] for c in checks)
    pct = round(100.0 * points / max_points, 1) if max_points else 0.0
    if pct >= _STRONG_PCT:
        verdict = "Strong"
    elif pct >= _FAIR_PCT:
        verdict = "Fair"
    else:
        verdict = "Pass"

    return {
        "checks": checks,
        "points": points,
        "max_points": max_points,
        "pct": pct,
        "verdict": verdict,
    }
