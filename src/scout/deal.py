"""Deal advice — turn the signals into a concrete decision an investor can act on.

Free portals show an asking price. What a buyer actually wants is: *what should I
offer, and why?* This module fuses the pieces the rest of the pipeline already
computes — the hedonic **fair value** (when the model is confident), the recorded
**negotiation signal** (days on market, price cuts), and the **net yield** — into a
single recommended offer price, the implied discount off asking, and a one-line
thesis. That decision is the thing worth paying for; the raw data underneath is free.

Pure functions, no DB / network / Streamlit. Fails soft: a listing with no usable
asking price returns ``None`` (the UI shows nothing rather than a bogus figure).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Motivation-driven room below asking. A maximally motivated seller (negotiation score
# ~100, sat long, already cutting) is modelled as good for ~8% off asking on evidence
# alone; explicit hard tells (a real cut, a long sit) nudge it a little further, capped
# so the tool never suggests an insultingly lowball, un-actionable offer.
_MAX_MOTIVATION_DISCOUNT = 0.08
_CUT_BONUS = 0.01
_STALE_BONUS = 0.01
_STALE_DAYS = 90
_MAX_TOTAL_DISCOUNT = 0.12
# Real offers are round numbers — snap to the nearest €500 so the figure reads like an
# amount a buyer would actually put on the table, not a spurious €197,314.
_OFFER_ROUNDING = 500


@dataclass
class DealAdvice:
    suggested_offer: int
    discount_pct: float  # 0..1 off the asking price
    thesis: str
    drivers: list[str] = field(default_factory=list)


def _round_offer(value: float) -> int:
    return int(round(value / _OFFER_ROUNDING) * _OFFER_ROUNDING)


def advise(
    *,
    asking: int | None,
    predicted_price: int | None = None,
    value_confident: bool = False,
    negotiation_score: float = 0.0,
    days_on_market: int | None = None,
    num_cuts: int = 0,
    net_yield: float | None = None,
) -> DealAdvice | None:
    """Recommend an offer price + thesis from the fused signals.

    - ``asking`` — the current listed price (required).
    - ``predicted_price`` / ``value_confident`` — the hedonic fair value and whether the
      per-area model was confident. A confident fair value BELOW the motivation-only offer
      caps the recommendation (never offer above what the model says it's worth); a
      low-confidence estimate is ignored for the number (shown only as context).
    - ``negotiation_score`` / ``days_on_market`` / ``num_cuts`` — the recorded motivation.
    - ``net_yield`` — folded into the thesis so the offer's return is stated.
    """
    if not asking or asking <= 0:
        return None

    # 1. Motivation-driven discount off asking, from the recorded signal + hard tells.
    motivation = min(max(negotiation_score, 0.0) / 100.0, 1.0) * _MAX_MOTIVATION_DISCOUNT
    if num_cuts >= 1:
        motivation += _CUT_BONUS
    if days_on_market and days_on_market >= _STALE_DAYS:
        motivation += _STALE_BONUS
    motivation = min(motivation, _MAX_TOTAL_DISCOUNT)
    offer_from_asking = asking * (1.0 - motivation)

    # 2. Fair-value cap: when the model confidently prices it below the motivation offer,
    #    anchor to fair value — there's no reason to offer above what it's worth.
    overpriced_vs_fair = bool(predicted_price and value_confident and predicted_price < asking)
    if predicted_price and value_confident and predicted_price < offer_from_asking:
        offer_raw = float(predicted_price)
    else:
        offer_raw = offer_from_asking

    offer = _round_offer(offer_raw)
    offer = max(offer, 0)
    discount_pct = (asking - offer) / asking if asking else 0.0

    # 3. Drivers — the evidence behind the number, most persuasive first.
    drivers: list[str] = []
    if days_on_market and days_on_market >= 45:
        drivers.append(f"on market {days_on_market} days")
    if num_cuts >= 1:
        times = f" ({num_cuts}×)" if num_cuts > 1 else ""
        drivers.append(f"seller already cut the price{times}")
    if overpriced_vs_fair:
        over = (asking - predicted_price) / asking
        drivers.append(f"asking ~{over * 100:.0f}% over modelled fair value")
    if net_yield is not None:
        drivers.append(f"~{net_yield * 100:.1f}% net yield")

    # 4. Thesis — one actionable line.
    head = f"Offer €{offer:,} (~{discount_pct * 100:.0f}% below asking)"
    if drivers:
        thesis = f"{head}: " + ", ".join(drivers) + "."
    else:
        thesis = f"{head}: priced in line with the market — limited room, offer near asking."
    return DealAdvice(
        suggested_offer=offer,
        discount_pct=round(discount_pct, 4),
        thesis=thesis,
        drivers=drivers,
    )
