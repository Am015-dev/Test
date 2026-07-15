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


@dataclass
class Recommendation:
    verdict: str  # "BUY" | "WATCH" | "PASS"
    headline: str  # one-line action, e.g. "Buy-to-let — offer €185k, ~5% net"
    play: str  # the strategy, e.g. "Cashflow buy-to-let"
    rationale: list[str] = field(default_factory=list)  # the persuasive "why", ordered
    risks: list[str] = field(default_factory=list)  # the honest caveats


_VERDICT_EMOJI = {"BUY": "🟢", "WATCH": "🟡", "PASS": "🔴"}


def verdict_emoji(v: str) -> str:
    return _VERDICT_EMOJI.get(v, "")


def _fmt_pct(x: float | None) -> str:
    return f"{x * 100:.1f}%" if x is not None else "—"


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
            f"Pass — filtered out ({d.get('exclusion_reason') or 'hard filter'})",
            "—",
            risks=[d.get("exclusion_reason") or "excluded by a hard rule"],
        )
    hard_pass = []
    if dscr is not None and dscr < 0.85:
        hard_pass.append(f"financed rent covers only {dscr:.0%} of the mortgage (DSCR {dscr:.2f})")
    if beo is not None and beo > 1.0:
        hard_pass.append("won't break even even at 100% occupancy when financed")
    if (ny is not None and ny < 0.02) and not (gap and gap >= 0.10):
        hard_pass.append(f"thin {_fmt_pct(ny)} net yield with no real discount to fair value")

    # ---- the play & positives -----------------------------------------------------
    play = "Buy-to-let"
    if gap and gap >= 0.10:
        rationale.append(f"priced {gap * 100:.0f}% below the model's fair value (beyond its ±band)")
    if ny is not None and ny >= 0.045 and not rent_est:
        rationale.append(f"strong {_fmt_pct(ny)} net yield on a real rent comp")
        play = "Cashflow buy-to-let"
    elif ny is not None and ny >= 0.035:
        rationale.append(f"{_fmt_pct(ny)} net yield")
    if cap is not None and cap >= 0.045:
        rationale.append(f"{_fmt_pct(cap)} cap rate")
    if dom >= 180:
        rationale.append(f"on the market {dom} days — the seller is likely negotiable")
    elif dom >= 90:
        rationale.append(f"{dom} days on market — some negotiating room")
    if private:
        rationale.append("private seller — no agent fee, direct negotiation")

    # Value-add angle: poor energy / old + a renovation ROI worth stating.
    reno = d.get("renovation") or {}
    if "Value-add" in tags or energy in {"D", "E", "F", "G", "Δ", "Ε", "Ζ", "Η", "H"}:
        play = "Value-add / renovate-to-rent"
        rationale.append("energy-inefficient stock — a retrofit lifts both rent and resale (EPBD)")
        if reno.get("roi_pct"):
            rationale.append(
                f"~€{reno.get('capex', 0):,.0f} retrofit → +€{reno.get('annual_rent_uplift', 0):,.0f}/yr "
                f"({reno['roi_pct'] * 100:.0f}% ROI)"
            )

    # ---- honest risks -------------------------------------------------------------
    if rent_est:
        risks.append("rent is an area estimate, not a real comp — verify the achievable rent")
    if d.get("data_missing"):
        risks.append(f"unverified: {', '.join(d['data_missing'])}")
    if d.get("consistency_flags"):
        risks.append(d["consistency_flags"][0])
    if energy in {"E", "F", "G", "Ε", "Ζ", "Η", "H"}:
        risks.append("low energy class — EPBD renovation may become mandatory")
    if d.get("location_precision") != "exact":
        risks.append("approximate location — confirm the exact spot and metro walk")

    # ---- decide the verdict -------------------------------------------------------
    offer = d.get("suggested_offer")
    disc = d.get("offer_discount_pct")
    if hard_pass:
        return Recommendation(
            "PASS",
            f"Pass — {hard_pass[0]}",
            play,
            rationale=rationale,
            risks=hard_pass + risks,
        )

    strong = sum(
        [
            bool(gap and gap >= 0.10),
            bool(ny is not None and ny >= 0.045 and not rent_est),
            bool(dom >= 180),
            bool(dscr is not None and dscr >= 1.2),
        ]
    )
    if strong >= 2 and not (rent_est and gap is None):
        verdict = "BUY"
    elif rationale:
        verdict = "WATCH"
    else:
        verdict = "PASS"
        rationale = rationale or ["no standout signal — fairly priced, ordinary return"]

    # ---- headline: the concrete action -------------------------------------------
    if verdict == "PASS":
        headline = "Pass — nothing here beats a fairly-priced flat"
    else:
        act = "Buy" if verdict == "BUY" else "Shortlist"
        if offer and disc and disc >= 0.01:
            headline = (
                f"{act} — offer €{offer:,.0f} ({disc * 100:.0f}% below asking), ~{_fmt_pct(ny)} net"
            )
        else:
            headline = f"{act} — {play.lower()}, ~{_fmt_pct(ny)} net yield"

    return Recommendation(verdict, headline, play, rationale=rationale, risks=risks)
