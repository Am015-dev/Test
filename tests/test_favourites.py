# ruff: noqa: F811  (the imported `env` fixture is re-declared as a test argument)
"""Favourites: one short card per flat, best score first, no second list of the same flats."""

from __future__ import annotations

from .test_ui_gauntlet import SEARCH, env, fresh, goto, ok  # noqa: F401


def test_favourites_are_cards_once_each(env):
    at = fresh(SEARCH)
    for _ in range(2):
        next(b for b in at.button if b.label == "Αγαπημένο").click().run()
    goto(at, "Αγαπημένα")
    ok(at, "favourites")
    assert any(m.value == "## Αγαπημένα (2)" for m in at.markdown)
    cards = [m.value for m in at.markdown if 'class="hg-card"' in m.value]
    assert len(cards) == 2 and all('data-compact="1"' in c for c in cards)
    assert not any(m.value.startswith("1. [") for m in at.markdown)  # no duplicate text list
    assert at.button(key="watch_compare").label == "Σύγκρινε δύο από αυτά"
