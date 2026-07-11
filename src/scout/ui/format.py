"""All money / yield / badge formatting in one place (spec §9)."""

from __future__ import annotations

from datetime import datetime


def euro(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"€{value:,.0f}"


def euro_per_m2(value: float | None) -> str:
    if value is None:
        return "—"
    return f"€{value:,.0f}/m²"


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
_ARCHETYPE_BADGE = {
    "New build": "✨ NEW BUILD",
    "Renovated": "🔧 RENOVATED",
    "Modern": "🏢 MODERN",
    "Energy liability": "⚠️ ENERGY LIABILITY",
    "Dated": "🕰️ DATED",
}


def badges(row: dict) -> list[str]:
    """Compute the badge labels for a listing row (asset class first, then signals)."""
    out: list[str] = []
    arch = _ARCHETYPE_BADGE.get(row.get("archetype", ""))
    if arch:
        out.append(arch)
    if row.get("is_new"):
        out.append("🆕 NEW")
    if row.get("price_dropped"):
        out.append("📉 PRICE ↓")
    if row.get("is_opportunity"):
        out.append("💎 OPPORTUNITY")
    if row.get("is_private_seller"):
        out.append("🤝 PRIVATE")
    if row.get("is_currently_rented"):
        out.append("🏠 RENTED")
    return out
