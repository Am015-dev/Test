"""The recommendation — the one thing a paying investor actually wants: *should I buy
this, and what exactly would I do?* Not another number, a decision.

Everything upstream produces signals (fair-value gap, net yield, cap rate, DSCR, days on
market, strategy tags, renovation ROI). This fuses them into a single honest verdict —
**BUY / WATCH / PASS** — plus the concrete play (buy-to-let, value-add, negotiate) and the
realistic action, stated in one or two plain sentences. Crucially it will say **PASS**:
telling a subscriber what NOT to buy (rent won't cover the mortgage; not actually cheap) is
as valuable as flagging a deal, and it's what makes the tool trustworthy rather than a hype
machine.

Pure functions over the listing dict (the shape from ui.queries._row_to_dict). No DB /
network / Streamlit. Fails soft to a WATCH with a generic note on missing inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import metrics as _metrics
from .relative_value import relative_yield
from .ui.format import euro as _euro


@dataclass
class Recommendation:
    verdict: str  # "BUY" | "WATCH" | "PASS" — a CODE (compared in logic); see verdict_label
    headline: str  # one-line action (Greek), e.g. "Αγορά — προσφορά 185.000 € …"
    play: str  # the strategy (Greek), e.g. "Αγορά για εισόδημα από ενοίκιο"
    rationale: list[str] = field(default_factory=list)  # the persuasive "why", ordered
    risks: list[str] = field(default_factory=list)  # the honest caveats


_VERDICT_EMOJI = {"BUY": "🟢", "WATCH": "🟡", "PASS": "🔴"}
# Greek display label per verdict code. The code itself ("BUY"/"WATCH"/"PASS") stays the
# value logic compares against; only what the buyer reads is translated.
VERDICT_LABELS = {"BUY": "Αγορά", "WATCH": "Παρακολούθηση", "PASS": "Προσπέραση"}
# Word the thin-data "verify first" headline puts before the missing-field list; the card
# checks for it so it doesn't repeat the same list in its own completeness note.
MISSING_MARKER = "λείπουν:"


def verdict_emoji(v: str) -> str:
    return _VERDICT_EMOJI.get(v, "")


def verdict_label(v: str | None) -> str:
    """Greek display label for a verdict code (unknown codes pass through)."""
    return VERDICT_LABELS.get(v or "", v or "")


def _fmt_pct(x: float | None) -> str:
    return f"{x * 100:.1f}%" if x is not None else "—"


# Greek names for the play (strategy) — the headline reuses them in lower case.
_PLAY_BTL = "Αγορά για ενοικίαση"
_PLAY_CASHFLOW = "Αγορά για εισόδημα από ενοίκιο"
_PLAY_VALUE_ADD = "Ανακαίνιση & ενοικίαση (αναβάθμιση αξίας)"


def recommend(d: dict) -> Recommendation:
    """Fuse the signals into a BUY/WATCH/PASS recommendation with a concrete play."""
    price = d.get("price")
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    annual = monthly * 12 if monthly else None
    ny = d.get("net_yield")
    gap = d.get("value_gap_pct")  # significance-gated: only present when beyond model noise
    dom = d.get("days_on_market") or 0
    energy = (d.get("energy_class") or "").strip().upper()
    rent_est = bool(d.get("rent_estimated"))
    private = bool(d.get("is_private_seller"))
    tags = set(d.get("strategy_tags") or [])

    im = _metrics.investor_metrics(price, annual, d.get("area_m2")) if (price and annual) else {}
    dscr = im.get("dscr")
    beo = im.get("break_even_occupancy")
    cap = im.get("cap_rate")

    rationale: list[str] = []
    risks: list[str] = []

    # ---- disqualifiers → PASS (say what NOT to buy) --------------------------------
    if d.get("excluded"):
        return Recommendation(
            "PASS",
            f"Εκτός φίλτρων ({d.get('exclusion_reason') or 'αυστηρό φίλτρο'})",
            "—",
            risks=[d.get("exclusion_reason") or "αποκλείστηκε από αυστηρό κανόνα"],
        )
    hard_pass = []
    if dscr is not None and dscr < 0.85:
        hard_pass.append(
            f"με δάνειο, το ενοίκιο καλύπτει μόνο το {dscr:.0%} της δόσης (DSCR {dscr:.2f})"
        )
    if beo is not None and beo > 1.0:
        hard_pass.append("με δάνειο δεν βγαίνει ούτε με 100% πληρότητα")
    if (ny is not None and ny < 0.02) and not (gap and gap >= 0.10):
        hard_pass.append(
            f"χαμηλή καθαρή απόδοση {_fmt_pct(ny)} χωρίς πραγματική έκπτωση από την αξία"
        )

    # ---- the play & positives -----------------------------------------------------
    play = _PLAY_BTL
    if gap and gap >= 0.10:
        rationale.append(
            f"τιμή {gap * 100:.0f}% κάτω από την εκτιμώμενη αξία του μοντέλου "
            "(πέρα από το περιθώριο σφάλματος)"
        )
    if ny is not None and ny >= 0.045 and not rent_est:
        rationale.append(
            f"υψηλή καθαρή απόδοση {_fmt_pct(ny)} με το ενοίκιο που δηλώνει η ίδια η αγγελία"
        )
        play = _PLAY_CASHFLOW
    elif ny is not None and ny >= 0.035:
        rationale.append(f"καθαρή απόδοση {_fmt_pct(ny)}")
    if cap is not None and cap >= 0.045:
        rationale.append(f"cap rate {_fmt_pct(cap)}")
    if dom >= 180:
        rationale.append(f"{dom} μέρες στην αγορά — ο πωλητής μάλλον διαπραγματεύεται")
    elif dom >= 90:
        rationale.append(f"{dom} μέρες στην αγορά — υπάρχει περιθώριο διαπραγμάτευσης")
    if private:
        rationale.append("ιδιώτης πωλητής — χωρίς μεσιτικά, απευθείας διαπραγμάτευση")

    # Value-add angle: poor energy / old + a renovation ROI worth stating.
    reno = d.get("renovation") or {}
    if "Value-add" in tags or energy in {"D", "E", "F", "G", "Δ", "Ε", "Ζ", "Η", "H"}:
        play = _PLAY_VALUE_ADD
        rationale.append(
            "ενεργοβόρο ακίνητο — η αναβάθμιση ανεβάζει ενοίκιο και αξία μεταπώλησης (EPBD)"
        )
        if reno.get("roi_pct"):
            rationale.append(
                f"αναβάθμιση ~{_euro(reno.get('capex', 0))} → "
                f"+{_euro(reno.get('annual_rent_uplift', 0))}/έτος "
                f"({reno['roi_pct'] * 100:.0f}% ROI)"
            )

    # ---- honest risks -------------------------------------------------------------
    if rent_est:
        risks.append(
            "το ενοίκιο είναι εκτίμηση περιοχής, όχι πραγματικό συγκρίσιμο — "
            "επιβεβαίωσε τι ενοίκιο πιάνει"
        )
    if d.get("data_missing"):
        risks.append(f"ανεπιβεβαίωτα: {', '.join(d['data_missing'])}")
    if d.get("consistency_flags"):
        risks.append(d["consistency_flags"][0])
    if energy in {"E", "F", "G", "Ε", "Ζ", "Η", "H"}:
        risks.append("χαμηλή ενεργειακή κλάση — η ανακαίνιση (EPBD) ίσως γίνει υποχρεωτική")
    if d.get("location_precision") != "exact":
        risks.append(
            "κατά προσέγγιση τοποθεσία — επιβεβαίωσε το ακριβές σημείο και την απόσταση από μετρό"
        )

    # ---- decide the verdict -------------------------------------------------------
    offer = d.get("suggested_offer")
    disc = d.get("offer_discount_pct")
    if hard_pass:
        return Recommendation(
            "PASS",
            hard_pass[0][:1].upper() + hard_pass[0][1:],
            play,
            rationale=rationale,
            risks=hard_pass + risks,
        )

    # DSCR/cap here are computed off the SAME (often imputed) rent as the yield, so on an
    # estimated-rent listing they're not an independent signal — only count them when the
    # rent is a real comp. Otherwise a card-only flat stacks two correlated "strong" marks
    # off one guessed number and lands a false BUY.
    strong = sum(
        [
            bool(gap and gap >= 0.10),
            bool(ny is not None and ny >= 0.045 and not rent_est),
            bool(dom >= 180),
            bool(dscr is not None and dscr >= 1.2 and not rent_est),
        ]
    )

    # A BUY is a claim we can stand behind. Two gates cap an otherwise-strong listing at
    # WATCH ("shortlist and verify") rather than BUY — telling the buyer to look before they
    # leap is the honest call, and it stops the verdict from being BUY on everything:
    #   • self-inconsistent numbers (a €545/m² "apartment" that's really land/commercial), or
    #   • too little verified data to underwrite (card-only listing missing the essentials).
    inconsistent = bool(d.get("consistency_flags"))
    thin_data = len(d.get("data_missing") or []) >= 2
    # A data-quality-suspect listing (whole building priced as a flat, future year, off-by-10x
    # €/m²/yield) must never clear the BUY bar — its headline numbers are artifacts. It still
    # shows (as WATCH/PASS, badged and demoted), so the buyer sees WHY, never a silent drop.
    suspect = bool(d.get("is_suspect"))
    buy_ok = not inconsistent and not thin_data and not suspect

    # BUY is a *high-conviction shortlist*, not a "notable" tag. Both of our soft, largely
    # independent estimates must AGREE and each clear a WIDER bar than the WATCH-level marks:
    #   • significantly under the model's fair value (asking-vs-model gap, past its ±band), AND
    #   • a genuinely solid net yield — not just the 4.5% "decent" line.
    # Either signal ALONE is too soft to buy on: the gap is asking-based, the yield rests on
    # an area-imputed rent, and both share the asking price, so one cheap number can inflate
    # both at once. Only when they corroborate — past raised bars, on non-suspect, non-thin
    # data — does a listing earn the green light. This is deliberately a few-hundred set, not
    # a tenth of inventory; if the data only supports WATCH, WATCH is the honest verdict.
    BUY_GAP, BUY_YIELD = 0.15, 0.055
    # The flat national BUY_YIELD floor alone misses the failure case relative_value.py's
    # tests demonstrate: 5.5% net yield clears it everywhere, even in a peripheral
    # high-yield area where 5.5% is actually the WORST yield among comparable local
    # listings (peers there run 7-11%) — a false-positive BUY on a locally-mediocre deal.
    # When there are enough local peers to judge (BUY_YIELD_LOCAL_PCT gate), also require
    # the yield to rank at/above the local median — never BELOW where the flat floor alone
    # would have said yes. Too few local peers (relative_yield returns None) → unchanged,
    # flat-floor-only behavior, so a listing is never blocked from BUY for lack of data.
    BUY_YIELD_LOCAL_PCT = 0.5
    ry = relative_yield(d)
    yield_ok = (
        ny is not None and ny >= BUY_YIELD and (ry is None or ry.percentile >= BUY_YIELD_LOCAL_PCT)
    )
    would_buy = (gap is not None and gap >= BUY_GAP) and yield_ok

    if would_buy and buy_ok:
        verdict = "BUY"
    elif strong >= 2 or rationale:
        verdict = "WATCH"
    else:
        verdict = "PASS"
        rationale = rationale or ["κανένα ξεχωριστό σήμα — δίκαιη τιμή, συνηθισμένη απόδοση"]

    # Cleared the BUY bar but held at WATCH only for want of trust (suspect / thin data)?
    # Say so plainly in the headline so the discipline is visible, not silent.
    capped = verdict == "WATCH" and would_buy

    # ---- headline: the concrete action -------------------------------------------
    # The UI always shows the verdict label (Αγορά / Παρακολούθηση / Προσπέραση) right before
    # the headline, so the headline itself does not repeat it.
    if verdict == "PASS":
        headline = "Τίποτα καλύτερο από ένα σπίτι σε δίκαιη τιμή"
    elif capped and inconsistent:
        headline = f"Έλεγξε πρώτα — δυνατό στα χαρτιά, αλλά {d['consistency_flags'][0]}"
    elif capped and thin_data:
        headline = (
            f"Έλεγξε πρώτα — δυνατό στα χαρτιά, αλλά {MISSING_MARKER} "
            f"{', '.join(d['data_missing'])}"
        )
    else:
        if offer and disc and disc >= 0.01:
            headline = (
                f"Προσφορά {_euro(offer)} ({disc * 100:.0f}% κάτω από τη ζητούμενη), "
                f"~{_fmt_pct(ny)} καθαρή απόδοση"
            )
        else:
            headline = f"{play}, ~{_fmt_pct(ny)} καθαρή απόδοση"

    return Recommendation(verdict, headline, play, rationale=rationale, risks=risks)
