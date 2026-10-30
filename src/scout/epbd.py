"""EU-EPBD renovation-liability flag — a real Greek buyer concern portals ignore.

Under the recast Energy Performance of Buildings Directive, the worst-performing stock
(energy class E/F/G, Greek Ε/Ζ/Η) faces staged minimum-energy-performance requirements this
decade: to keep letting or selling, an owner will likely have to fund a deep-energy
renovation. That is a real, quantifiable capital liability sitting on top of the purchase
price — and no portal surfaces it. This turns the energy class into an actionable number.

Pure functions, no DB/network. The capex estimate is a transparent heuristic (a €/m² retrofit
cost scaled by how far below compliance the class sits), clearly labelled as an estimate —
not a survey. Unknown/exempt energy → no flag (never invent a liability from missing data).
"""

from __future__ import annotations

from dataclasses import dataclass

from .scoring import _ENERGY_SCORE, energy_class_score
from .ui.format import euro

# Indicative deep-energy-retrofit cost (€/m²) to lift a dwelling to a compliant class.
# A worst-class (G/Η) flat needs the full retrofit; a class-E flat needs less. Deliberately
# round and conservative — a starting figure a buyer refines with a real engineer's quote.
_FULL_RETROFIT_EUR_PER_M2 = 350.0
# Classes at/below this 0..1 energy score carry a renovation-mandate risk (E/F/G ≈ ≤0.26).
_LIABILITY_THRESHOLD = 0.26


@dataclass
class EpbdFlag:
    at_risk: bool
    energy_class: str | None
    est_capex: int | None  # indicative retrofit cost to reach compliance, EUR
    note: str


def epbd_flag(energy_class: str | None, area_m2: float | None) -> EpbdFlag:
    """Flag EPBD renovation risk + an indicative retrofit capex for a listing.

    Only fires for a KNOWN poor class (E/F/G · Ε/Ζ/Η). Unknown/exempt/good classes return
    ``at_risk=False`` with no capex — missing data must never fabricate a liability."""
    ec = (energy_class or "").strip().upper()
    if ec not in _ENERGY_SCORE:
        return EpbdFlag(False, energy_class, None, "")
    score = energy_class_score(energy_class)
    if score > _LIABILITY_THRESHOLD:
        return EpbdFlag(False, energy_class, None, "")
    # Worse class → closer to a full retrofit. Scale the €/m² cost by the compliance gap.
    gap = (_LIABILITY_THRESHOLD - score) / _LIABILITY_THRESHOLD  # 0..1 (G/Η ≈ 1.0)
    capex = None
    if area_m2 and area_m2 > 0:
        capex = int(round(_FULL_RETROFIT_EUR_PER_M2 * area_m2 * (0.5 + 0.5 * gap) / 500) * 500)
    note = (
        f"Ενεργειακή κλάση {energy_class}: οι ελάχιστες απαιτήσεις της οδηγίας EPBD της ΕΕ "
        "πιθανότατα θα απαιτήσουν ριζική ενεργειακή ανακαίνιση μέσα στη δεκαετία"
        + (f" — ενδεικτικό κόστος ≈ {euro(capex)}." if capex else ".")
    )
    return EpbdFlag(True, energy_class, capex, note)
