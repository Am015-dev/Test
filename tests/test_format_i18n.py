"""Greek display formatting + display labels that sit apart from the internal codes."""

from scout.recommendation import verdict_label
from scout.strategy_fit import strategy_label, strategy_tags
from scout.ui import format as fmt


def test_euro_is_greek_style():
    assert fmt.euro(170_000) == "170.000 €"
    assert fmt.euro(950) == "950 €"
    assert fmt.euro(None) == "—"


def test_euro_per_m2_is_greek_style():
    assert fmt.euro_per_m2(2429.4) == "2.429 €/τ.μ."
    assert fmt.euro_per_m2(None) == "—"


def test_verdict_codes_stay_english_labels_are_greek():
    assert verdict_label("BUY") == "Αγορά"
    assert verdict_label("WATCH") == "Παρακολούθηση"
    assert verdict_label("PASS") == "Προσπέραση"
    assert verdict_label("??") == "??"


def test_strategy_tag_ids_stay_codes_labels_are_greek():
    tags = strategy_tags({"value_percentile": 0.95, "days_on_market": 400})
    assert tags == ["Underpriced", "Motivated seller"]  # ids unchanged
    assert [strategy_label(t) for t in tags] == ["Υποτιμημένο", "Πρόθυμος πωλητής"]
    assert strategy_label("💸 −5% σήμερα") == "💸 −5% σήμερα"  # free text passes through


def test_status_badges_are_greek():
    out = fmt.badges({"relist_count": 2, "is_private_seller": True, "is_currently_rented": True})
    assert out == [fmt.BADGE_RELISTED, fmt.BADGE_PRIVATE, fmt.BADGE_RENTED]
    assert not any(c.isascii() and c.isalpha() for b in out for c in b)
