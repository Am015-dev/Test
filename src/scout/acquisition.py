"""Total cash-to-acquire model for a Greek residential purchase.

Pure functions only — no DB, no network, no Streamlit. The sticker price is never
the real cost of buying a home in Greece: on top of it sit the transfer tax, the
notary, the land-registry filing, the lawyer and (unless it's a private sale) the
estate agent. This module turns a headline price into the *all-in cash* a buyer
actually has to wire, so nobody underwrites a deal off the asking figure alone.

Everything FAILS SOFT: given a non-positive price the model returns a zeroed
breakdown rather than raising, so a listing with a missing/bad price shows blanks
instead of crashing the run. All euro figures are rounded to whole euros, matching
the rounding tone of ``finance.py`` / ``investment.py``.

Greek purchase-cost model (spec):
- Transfer tax ("φόρος μεταβίβασης") = 3.09% of price on RESALE homes. New builds
  sold *with* VAT would instead carry 24% VAT — but that regime has been suspended
  for most new builds for years, so we DEFAULT to the transfer-tax path and let the
  caller opt into VAT explicitly via ``new_build=True``.
- Notary ≈ 1.2% + VAT → ~1.5% effective.
- Land registry / mortgage registration ≈ 0.5%.
- Legal fee ≈ 1.0% (optional).
- Estate-agent fee ≈ 2% + VAT → ~2.48% (0 for private sales).
"""

from __future__ import annotations

# Transfer-tax path (resale): φόρος μεταβίβασης, 3.09% of the purchase price.
TRANSFER_TAX_PCT = 0.0309
# New-build path: VAT at 24% instead of transfer tax. Off by default — most new
# builds are VAT-suspended and fall back to the 3.09% transfer tax above.
NEW_BUILD_VAT_PCT = 0.24
# Notary fee ~1.2% + VAT ≈ 1.5% effective.
NOTARY_PCT = 0.015
# Land-registry / mortgage-registration filing ≈ 0.5%.
LAND_REGISTRY_PCT = 0.005
# Lawyer fee ≈ 1.0% (optional — many resale buyers still engage one).
LEGAL_PCT = 0.01
# Estate-agent fee ~2% + VAT ≈ 2.48% (0 for private, agent-free sales).
DEFAULT_AGENT_FEE_PCT = 0.0248


def acquisition_costs(
    price: int,
    *,
    new_build: bool = False,
    include_legal: bool = True,
    agent_fee_pct: float = DEFAULT_AGENT_FEE_PCT,
) -> dict:
    """All-in cash needed to buy a Greek home, broken out line by line.

    ``price`` is the agreed purchase price in euros. Fees are layered on top:

    - ``transfer_tax``: 3.09% on resale, OR 24% VAT when ``new_build=True`` (the
      VAT regime is opt-in because it's suspended for most new builds).
    - ``notary``, ``land_registry``: always applied.
    - ``legal``: 1.0%, only when ``include_legal`` is True.
    - ``agent``: ``agent_fee_pct`` of price (pass 0.0 for a private sale).

    Returns a dict of whole-euro line items plus ``total_fees`` (the costs on top
    of the price), ``total_cash`` (price + fees — what the buyer actually needs),
    and ``fees_pct_of_price`` (fees as a fraction of price, e.g. 0.0857 = 8.57%).

    Fails soft: for ``price <= 0`` every figure is zero and ``fees_pct_of_price``
    is 0.0, so a bad/missing price yields blanks rather than an exception.
    """
    if price is None or price <= 0:
        return {
            "price": 0,
            "transfer_tax": 0,
            "notary": 0,
            "land_registry": 0,
            "legal": 0,
            "agent": 0,
            "total_fees": 0,
            "total_cash": 0,
            "fees_pct_of_price": 0.0,
        }

    # New builds sold with VAT pay 24% VAT in lieu of the transfer tax; the far
    # more common suspended-VAT new build (and every resale) pays 3.09%.
    tax_pct = NEW_BUILD_VAT_PCT if new_build else TRANSFER_TAX_PCT
    transfer_tax = round(price * tax_pct)
    notary = round(price * NOTARY_PCT)
    land_registry = round(price * LAND_REGISTRY_PCT)
    legal = round(price * LEGAL_PCT) if include_legal else 0
    agent = round(price * max(agent_fee_pct, 0.0))

    total_fees = transfer_tax + notary + land_registry + legal + agent
    total_cash = price + total_fees

    return {
        "price": int(price),
        "transfer_tax": transfer_tax,
        "notary": notary,
        "land_registry": land_registry,
        "legal": legal,
        "agent": agent,
        "total_fees": total_fees,
        "total_cash": total_cash,
        "fees_pct_of_price": round(total_fees / price, 4),
    }
