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
    assert "ph-card-foot" in collapsed and "Δες την αγγελία" in collapsed
    # No stray blank line between the signals and the footer.
    assert ">\n\n<" not in collapsed


def test_card_html_with_thesis_and_missing_data():
    html = _card_html(_row(deal_thesis="Offer €190,000", data_missing=["energy", "year"]))
    collapsed = re.sub(r">\s+<", "><", html)
    assert "\n\n" not in collapsed
    assert "Offer" in collapsed and "Ελλιπή στοιχεία" in collapsed


# ---- the buyer card (search, favourites, saved searches) -----------------------------------

BUYER = dict(
    id=7,
    price=245_000,
    area_m2=78.0,
    price_per_m2=3141.0,
    floor=3.0,
    year_built=2018,
    neighborhood="Περισσός",
    est_monthly_rent=900.0,
    rent_estimated=True,
    source="xe",
    url="https://www.xe.gr/property/d/x/1",
)
CMP = {"ppm": 3600.0, "p25": 3300.0, "p75": 3900.0, "n": 12, "pct": 3141 / 3600 - 1, "label": "L"}


def _lines(html: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", x) for x in re.findall(r'<div class="hg-l\d">(.*?)</div>', html)]


def test_buyer_card_has_the_five_fixed_lines_in_greek():
    from scout.ui.buyer import card_html

    html = card_html({**BUYER, "page_checked": True}, {"cmp": CMP})
    l1, l2, l3, l4, l5 = _lines(html)
    assert l1 == "245.000 € · 78 τ.μ. · 3.141 €/τ.μ."
    assert l2 == "3ος όροφος · κτίριο 2018 · Περισσός · Σταθμός ΗΣΑΠ Περισσός (Γραμμή 1)"
    assert l3 == "Ελέγχθηκε η περιγραφή — δεν αναφέρει κατασκευή σε εξέλιξη"
    assert l4 == "Ενοίκιο (εκτίμηση) ~900 €/μήνα · Μικτή απόδοση 4,4 %"
    assert l5 == "Παρόμοια (12): 13 % κάτω"


def test_buyer_card_status_unknowns_and_photos():
    from scout.ui.buyer import card_html

    unchecked = card_html({**BUYER, "floor": None, "year_built": None}, {})
    assert 'hg-st-unk">Δεν έχει ελεγχθεί ακόμα η σελίδα της αγγελίας<' in unchecked
    assert "όροφος: δεν δηλώνεται" in unchecked and "έτος: δεν δηλώνεται" in unchecked
    assert "Λίγα παρόμοια" in unchecked
    shell = card_html(
        {**BUYER, "is_unfinished": True, "page_checked": True, "few_photos": True}, {}
    )
    assert 'hg-st-bad">Υπό κατασκευή<' in shell and "≤2 φωτογραφίες" in shell
    assert "Ελέγχθηκε" not in shell.split("<details>")[0]  # under construction wins
    norent = card_html({**BUYER, "area_m2": None, "est_monthly_rent": None}, {})
    assert "Ενοίκιο: χωρίς εκτίμηση" in norent


def test_buyer_card_every_number_has_its_basis_one_tap_away_and_no_score():
    from scout.ui.buyer import card_html

    html = card_html(BUYER, {"cmp": CMP, "score": 81})
    basis = html.split("<details>", 1)[1]
    assert "12 × 900 € ÷ 245.000 € = 4,4 %" in basis  # the yield
    assert "× 78 τ.μ." in basis and "αγγελίες ενοικίασης στο XE" in basis  # the rent
    assert "12 αγγελίες (L), διάμεσος 3.600 €/τ.μ." in basis  # the comparables
    assert "81" not in html and "Σκορ" not in html
    # no emoji decoration, no English, no raw keys
    assert not re.search(r"[\U0001F300-\U0001FAFF]", html)
    assert not any(w in html for w in ("N/A", "None", "rent", "yield", "score"))


def test_too_cheap_is_a_question_not_a_bonus():
    from scout.ui.buyer import comps_text

    assert comps_text({"cmp": {**CMP, "pct": -0.45}}).endswith(
        "45 % κάτω — έλεγξε γιατί (τ.μ., κατάσταση, νομικά)"
    )
