"""Listing pages that say a "νεόδμητο" flat is still being built (real XE wording, Oct 2026)."""

from __future__ import annotations

from datetime import date

import pytest

from scout.collectors.xe import unfinished_on_detail

TODAY = date(2026, 10, 31)


def page(facts: str = "") -> str:
    return (
        '<div data-testid="characteristics"><span>Βασικά χαρακτηριστικά</span>'
        f"{facts}</div><nav>Φίλτρα: Νεόδμητο · Υπό κατασκευή · Ανακαινισμένο</nav>"
    )


@pytest.mark.parametrize(
    "facts,detail",
    [
        ("<span>Υπό κατασκευή</span>", {}),
        ("<span>Διαθέσιμο από: 1/3/2027</span>", {}),
        ("", {"condition": "under_construction"}),
        ("", {"description": "Α1 95τμ ΠΑΡΑΔΟΣΗ ΤΕΛΗ 27-ΑΡΧΕΣ 28"}),
        ("", {"description": "Αποθήκη. Ενεργειακή κλάση Α+ Ολοκλήρωση τέλη του 2027"}),
        ("", {"description": "2υ/δ διαμέρισμα 64 τ.μ. στους Αμπελόκηπους (παράδοση έργου 2028)"}),
        ("", {"description": "H κατασκευή ξεκίνησε το 2025 με ενεργειακή κλάση Α"}),
        ("", {"description": "Κοντα στον ΗΣΑΠ. Αποπερατωση σε 1,5 χρονο"}),
        ("", {"description": "Η ολοκλήρωση της κατασκευής αναμένεται τον Απρίλιο του 2027."}),
        ("", {"description": "Οι φωτογραφίες είναι ενδεικτικές απεικονίσεις του έργου."}),
        ("", {"description": "Δείτε τα φωτορεαλιστικά σχέδια της πολυκατοικίας."}),
    ],
)
def test_still_being_built(facts, detail):
    assert unfinished_on_detail(page(facts), detail, TODAY)


@pytest.mark.parametrize(
    "facts,detail",
    [
        ("<span>Έτος κατασκευής: 2025</span>", {"condition": "newbuild"}),
        ("<span>Διαθέσιμο από: 1/9/2026</span>", {}),
        ("", {"description": "Νεόδμητο, 200 μέτρα από σταθμό Μετρό. Παράδοση αρχές 2026."}),
        ("", {"description": "Έχει κατασκευαστεί το 2025. Η κατάστασή του είναι: Νεόδμητο"}),
    ],
)
def test_finished(facts, detail):
    # the filter bar's "Υπό κατασκευή" option on every page must not count
    assert not unfinished_on_detail(page(facts), detail, TODAY)


def test_pages_read_before_the_check_existed_do_not_count_as_checked():
    from datetime import datetime

    from scout.collectors.xe import checked_for_unfinished

    assert not checked_for_unfinished(None)
    assert not checked_for_unfinished(datetime(2026, 7, 16))  # opened, but not checked
    assert checked_for_unfinished(datetime(2026, 10, 31, 13))
