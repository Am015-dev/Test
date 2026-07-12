"""Negotiation intelligence — the sellable core.

Free portals show a listing's *current* price. They hide the thing an investor or agent
will actually pay for: how motivated the seller is. That is not predicted, it is
**recorded** — from the price/status history this tool accumulates daily:

- **Days on market** — a flat that has sat is a flat whose owner will deal.
- **Price cuts** — how many, how deep, how recent.
- **Relisted** — pulled and re-posted (a reset/distress tell).
- **Stale AND above the area price** — an over-asked flat that isn't moving = maximum
  negotiating room.

Pure functions, no DB. The signal strengthens as the daily tracker runs — that compounding
time-series is the moat (it can't be reconstructed from a single portal snapshot).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Reference points (tunable). A flat sitting this long, or cut this much, saturates the
# corresponding signal.
_STALE_DAYS_FULL = 120.0
_CUT_PCT_FULL = 0.15
_OVERPRICED_FULL = 0.15
# Weights (contribution to the 0..100 negotiation score).
_W_STALE = 28.0
_W_CUT = 30.0
_W_OVERPRICED_STALE = 20.0
_W_RELISTED = 14.0
_W_PRIVATE = 8.0
# A listing at/above this score is surfaced as a "motivated seller" lead.
MOTIVATED_THRESHOLD = 45.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class NegotiationResult:
    score: float = 0.0  # 0..100 — higher = more negotiable / motivated seller
    days_on_market: int | None = None
    num_cuts: int = 0
    total_cut_pct: float = 0.0  # 0..1, cumulative drop from the first observed price
    relisted: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def is_motivated(self) -> bool:
        return self.score >= MOTIVATED_THRESHOLD


def _count_cuts(prices: list[int]) -> int:
    """Number of times the price stepped DOWN across the observed history."""
    return sum(1 for a, b in zip(prices, prices[1:], strict=False) if b < a)


def analyze(
    *,
    price_history: list[tuple[datetime, int]],
    first_seen: datetime | None,
    now: datetime,
    current_price: int,
    ppm2: float | None,
    area_median_ppm2: float | None,
    is_private_seller: bool = False,
    relisted: bool = False,
) -> NegotiationResult:
    """Score how motivated/negotiable the seller is from the recorded history.

    ``price_history`` is ``[(observed_at, price), ...]`` ascending (as stored). All
    signals degrade gracefully when history is short — a freshly-seen listing simply
    scores low until the daily tracker accumulates its story.
    """
    res = NegotiationResult()

    # Days on market (since first tracked; becomes the true dwell time as the tool runs).
    if first_seen is not None:
        res.days_on_market = max((now - first_seen).days, 0)
    stale = _clamp01((res.days_on_market or 0) / _STALE_DAYS_FULL)

    # Price cuts from the history.
    prices = [p for _, p in price_history] or [current_price]
    first_price = prices[0]
    res.num_cuts = _count_cuts(prices)
    if first_price > 0 and current_price < first_price:
        res.total_cut_pct = (first_price - current_price) / first_price
    # A cut signal that rewards both depth and repetition (each extra cut adds urgency).
    cut = _clamp01(res.total_cut_pct / _CUT_PCT_FULL)
    if res.num_cuts >= 2:
        cut = _clamp01(cut + 0.15)

    # Over-asked AND not moving = the most negotiable of all.
    overpriced_stale = 0.0
    if ppm2 and area_median_ppm2:
        over = (ppm2 / area_median_ppm2) - 1.0
        overpriced_stale = _clamp01(over / _OVERPRICED_FULL) * stale

    res.relisted = relisted
    relisted_sig = 1.0 if relisted else 0.0
    private_sig = 1.0 if is_private_seller else 0.0

    raw = (
        stale * _W_STALE
        + cut * _W_CUT
        + overpriced_stale * _W_OVERPRICED_STALE
        + relisted_sig * _W_RELISTED
        + private_sig * _W_PRIVATE
    )
    total = _W_STALE + _W_CUT + _W_OVERPRICED_STALE + _W_RELISTED + _W_PRIVATE
    res.score = round(raw / total * 100.0, 1)

    # Human-readable reasons (what an agent/investor would act on).
    if res.days_on_market and res.days_on_market >= 45:
        res.reasons.append(f"On market {res.days_on_market} days")
    if res.total_cut_pct > 0:
        cuts = f" over {res.num_cuts} cuts" if res.num_cuts > 1 else ""
        res.reasons.append(f"Price cut {res.total_cut_pct * 100:.0f}%{cuts}")
    if overpriced_stale > 0.25:
        res.reasons.append("Over-asked and not moving")
    if relisted:
        res.reasons.append("Relisted")
    if is_private_seller:
        res.reasons.append("Private seller (direct negotiation)")
    return res
