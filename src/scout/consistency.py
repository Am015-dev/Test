"""Internal-consistency checks — catch listings whose own numbers contradict each other.

A tool that surfaces a "€424/m²" flat or an "A+ energy, built 1960, never renovated" listing
without comment looks like it isn't reading its own data. These pure checks return short,
honest "verify this" notes (never silently hide or down-rank a listing — a genuinely cheap
flat is exactly what a buyer wants) so the UI can warn a buyer to double-check before trusting
the headline numbers. High-precision by design: only flag clear contradictions, not merely
unusual-but-plausible values.
"""

from __future__ import annotations

# Athens apartment €/m² realistically spans ~€900 (far/old) to ~€9,000 (prime new). Outside a
# generous band, the listing is probably a whole building, a plot, or a data error.
_PPM2_LOW = 700.0
_PPM2_HIGH = 12_000.0
_MIN_AREA_M2 = 18.0
_MIN_PRICE = 25_000
_GOOD_ENERGY = {"A+", "Α+", "A", "Α", "B+", "Β+"}
_OLD_BUILD_YEAR = 1995


def consistency_flags(d: dict) -> list[str]:
    """Return human-readable 'verify' notes for a listing dict, or [] when nothing is off."""
    flags: list[str] = []

    ppm2 = d.get("price_per_m2")
    if ppm2 is not None:
        if ppm2 < _PPM2_LOW:
            flags.append("unusually low €/m² — may be a whole building, plot, or data error")
        elif ppm2 > _PPM2_HIGH:
            flags.append("unusually high €/m² — verify the area is correct")

    area = d.get("area_m2")
    if area is not None and area < _MIN_AREA_M2:
        flags.append("very small floor area — verify it's a full residence")

    price = d.get("price")
    if price is not None and price < _MIN_PRICE:
        flags.append("unusually low price — verify it's the full sale price")

    # A top energy certificate on an old build with no stated renovation is contradictory:
    # pre-1995 blocks don't earn A/B ratings unless they were substantially upgraded.
    energy = (d.get("energy_class") or "").strip()
    year = d.get("year_built")
    reno = d.get("renovated_year")
    if energy in _GOOD_ENERGY and year and year < _OLD_BUILD_YEAR and not reno:
        flags.append(f"top energy rating on a {year} build with no stated renovation — verify")

    return flags
