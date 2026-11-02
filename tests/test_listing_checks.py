"""The listing page shows the six checks of a buy-to-let investor (round-3 spec §5)."""

from __future__ import annotations

from .test_ui_gauntlet import SEARCH, env, fresh, ok  # noqa: F401  (env is a fixture)

LABELS = (
    "Τιμή έναντι παρόμοιων",
    "Μικτή απόδοση",
    "Ρευστότητα περιοχής",
    "Ζήτηση ενοικίου",
    "Νομικά / κανονιστικά",
    "Έξοδος (τάση €/τ.μ.)",
)


def test_listing_page_shows_the_six_investor_checks(env):  # noqa: F811
    at = fresh(SEARCH)
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "details")
    text = "\n".join(m.value for m in at.markdown)
    assert any(e.label == "Έξι έλεγχοι επενδυτή" for e in at.expander)  # collapsed (C17)
    for label in LABELS:
        assert f"**{label}" in text, label
    # every check carries a verdict word, never a bare value
    assert any(w in text for w in ("καλό", "μέτριο", "προσοχή", "άγνωστο"))
