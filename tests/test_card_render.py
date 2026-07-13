"""Regression: the card grid must never emit a blank line inside its raw-HTML block.

Streamlit renders the grid via a CommonMark parser, which ends a raw-HTML block at the first
blank line — which made the rest of every card render as literal text (the badges + CTA
showed as raw <div> code). The collapse in listing_grid must prevent that.
"""

from __future__ import annotations

import re

from scout.ui.components import _card_html


def _row(**kw):
    base = dict(
        score=70,
        price=200_000,
        price_per_m2=2500,
        neighborhood="X",
        search_area="X",
        region="Κέντρο Αθήνας",
        archetype="Standard",
        deal_grade="B",
        data_confidence=80,
    )
    base.update(kw)
    return base


def test_card_html_collapses_to_no_blank_lines():
    # A card with NO thesis and NO completeness note (the case that used to break rendering).
    html = _card_html(_row(deal_thesis=None, data_missing=[]))
    collapsed = re.sub(r">\s+<", "><", html)
    assert "\n\n" not in collapsed
    # The footer (badges + CTA) must be present and contiguous with the rest.
    assert "ph-card-foot" in collapsed and "View listing" in collapsed
    # No stray blank line between the signals and the footer.
    assert ">\n\n<" not in collapsed


def test_card_html_with_thesis_and_missing_data():
    html = _card_html(_row(deal_thesis="Offer €190,000", data_missing=["energy", "year"]))
    collapsed = re.sub(r">\s+<", "><", html)
    assert "\n\n" not in collapsed
    assert "Offer" in collapsed and "Limited data" in collapsed
