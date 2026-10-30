"""All money / yield / badge formatting in one place (spec §9)."""

from __future__ import annotations

from datetime import datetime


def _gr_int(value: float | int) -> str:
    """Greek-style thousands grouping: 170000 -> "170.000"."""
    return f"{value:,.0f}".replace(",", ".")


def euro(value: float | int | None) -> str:
    """Greek money format: "170.000 €"."""
    if value is None:
        return "—"
    return f"{_gr_int(value)} €"


def euro_per_m2(value: float | None) -> str:
    """Greek €/m² format: "2.429 €/τ.μ."."""
    if value is None:
        return "—"
    return f"{_gr_int(value)} €/τ.μ."


def pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def days_on_market(first_seen: datetime | None, last_seen: datetime | None = None) -> int | None:
    if first_seen is None:
        return None
    end = last_seen or datetime.utcnow()
    return max((end - first_seen).days, 0)


# Asset-class badge per archetype — leads the badge row so quality reads at a glance.
# Keys are the archetype codes (data); values are the Greek display labels.
_ARCHETYPE_BADGE = {
    "New build": "✨ ΝΕΟΔΜΗΤΟ",
    "Renovated": "🔧 ΑΝΑΚΑΙΝΙΣΜΕΝΟ",
    "Modern": "🏢 ΣΥΓΧΡΟΝΟ",
    "Energy liability": "⚠️ ΕΝΕΡΓΟΒΟΡΟ",
    "Dated": "🕰️ ΠΑΛΑΙΟ",
}
BADGE_SUSPECT = "⚠️ ΕΛΕΓΞΕ ΣΤΟΙΧΕΙΑ"
BADGE_NEGOTIABLE = "🤝 ΔΙΑΠΡΑΓΜΑΤΕΥΣΙΜΟ"
BADGE_NEW = "🆕 ΝΕΑ"
BADGE_PRICE_DROP = "📉 ΤΙΜΗ ↓"
BADGE_RELISTED = "🔁 ΕΠΑΝΑΔΗΜΟΣΙΕΥΣΗ"
BADGE_OPPORTUNITY = "💎 ΕΥΚΑΙΡΙΑ"
BADGE_PRIVATE = "🤝 ΙΔΙΩΤΗΣ"
BADGE_RENTED = "🏠 ΕΝΟΙΚΙΑΣΜΕΝΟ"
# Badges the listing card hides: the archetype has its own pill, and OPPORTUNITY /
# NEGOTIABLE duplicate the Underpriced / Motivated-seller strategy tags.
CARD_HIDDEN_BADGES = frozenset({*_ARCHETYPE_BADGE.values(), BADGE_OPPORTUNITY, BADGE_NEGOTIABLE})


def badges(row: dict) -> list[str]:
    """Compute the badge labels for a listing row (asset class first, then signals)."""
    out: list[str] = []
    arch = _ARCHETYPE_BADGE.get(row.get("archetype", ""))
    if arch:
        out.append(arch)
    # Data-quality suspect (whole building priced as a flat, future year, off-by-10x €/m²).
    # Lead with it so the table makes plain why the ranking demoted this row.
    if row.get("is_suspect"):
        out.append(BADGE_SUSPECT)
    if (row.get("negotiation_score") or 0) >= 45:
        out.append(BADGE_NEGOTIABLE)
    if row.get("is_new"):
        out.append(BADGE_NEW)
    if row.get("price_dropped"):
        out.append(BADGE_PRICE_DROP)
    if (row.get("relist_count") or 0) > 1:
        out.append(BADGE_RELISTED)
    if row.get("is_opportunity"):
        out.append(BADGE_OPPORTUNITY)
    if row.get("is_private_seller"):
        out.append(BADGE_PRIVATE)
    if row.get("is_currently_rented"):
        out.append(BADGE_RENTED)
    return out
