# ruff: noqa: F811  (the imported `env` fixture is re-declared as a test argument)
"""C17 — verdict first, two actions.

Within one phone screen the buyer sees the answer, the link to the ad and one next tap:
the card's five lines, the link under every card, exactly two buttons («Λεπτομέρειες»,
«Αγαπημένο») in the guide, the recommendation as one spoken sentence, and the listing page
in the order link → card → «Τι να κάνεις» → collapsed sections.
"""

from __future__ import annotations

import re

from scout.ui import buyer, guide

from .test_guide import _text, walk
from .test_ui_gauntlet import DETAIL, SEARCH, SHORTLIST, env, fresh, ok  # noqa: F401

CMP = {"ppm": 3600.0, "p25": 3300.0, "p75": 3900.0, "n": 46, "pct": -0.15, "label": "L"}
FLAT = dict(
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
    page_checked=True,
    energy_class="B",
)


# ---- the card's lines ----------------------------------------------------------------------


def test_line_five_speaks_of_the_neighbours_never_of_comparables():
    assert buyer.comps_text({"cmp": CMP}) == "15 % κάτω από τα διπλανά (46)"
    assert buyer.comps_text({"cmp": {**CMP, "pct": 0.07}}) == "7 % πάνω από τα διπλανά (46)"
    assert buyer.comps_text({"cmp": {**CMP, "pct": 0.0}}) == "Όσο τα διπλανά (46)"
    assert buyer.comps_text({}) == "Λίγα διπλανά για σύγκριση"
    assert "Παρόμοια (" not in buyer.comps_text({"cmp": CMP})


def test_station_on_line_two_only_for_a_short_measured_walk():
    near = {
        **FLAT,
        "location_precision": "exact",
        "metro_distance_m": 450,
        "nearest_metro": "Holargos",
    }
    far = {**near, "metro_distance_m": 900}
    named = {
        **FLAT,
        "location_precision": "approx",
        "metro_distance_m": 300,
        "nearest_metro": "Holargos",
    }
    assert buyer.station_on_card(near).endswith("450 μ.")
    assert buyer.station_on_card(far) == "" and buyer.station_on_card(named) == ""
    assert buyer.station_basis(named).startswith(
        "Σταθμός "
    ) and "όνομα της γειτονιάς" in buyer.station_basis(named)
    html = buyer.card_html(named, {"cmp": CMP}, compact=True)
    l2 = html.split('<div class="hg-l2">')[1].split("</div>")[0]
    assert "Σταθμός" not in l2 and "όνομα της γειτονιάς" in html.split("<details>")[1]


def test_line_three_is_one_status_chip():
    html = buyer.card_html({**FLAT, "few_photos": True}, {"cmp": CMP}, compact=True)
    l3 = html.split('<div class="hg-l3">')[1].split("</div>")[0]
    assert l3.count('class="hg-st') == 1 and "Ελέγχθηκε η περιγραφή" in l3
    # the photo clause and «≤ 2 photos» are facts behind the card, not chips
    inside = html.split("<details>")[1]
    assert "Φωτογραφίες:" in inside and "Έως 2 φωτογραφίες" in inside


def test_line_one_ends_with_the_score():
    html = buyer.card_html(FLAT, {"cmp": CMP, "score": 71}, compact=True)
    l1 = re.sub(r"<[^>]+>", "", html.split('<div class="hg-l1">')[1].split("</div>")[0])
    assert l1 == "245.000 € · 78 τ.μ. · 3.141 €/τ.μ. · Βαθμολογία 71"


def test_no_photo_means_no_box():
    assert buyer.photo_html(FLAT) == ""
    assert "hg-thumb" not in buyer.card_html(FLAT, {}, compact=True)


# ---- the verdict and the recommendation ----------------------------------------------------


def test_verdict_lines_are_three_short_spoken_sentences():
    lines = buyer.verdict_lines(FLAT, {"cmp": CMP})
    assert lines == [
        "Καλή τιμή: 15 % κάτω από τα διπλανά (46 σπίτια).",
        "Ενοίκιο ~900 € τον μήνα, 4,4 % μικτά: μέτρια απόδοση.",
        "Πριν τηλεφωνήσεις, ρώτα κοινόχρηστα, βάρη και πότε ελευθερώνεται.",
    ]
    assert all(len(x.split()) <= 20 for x in lines)
    dear = buyer.verdict_lines(FLAT, {"cmp": {**CMP, "pct": 0.08}})[0]
    assert dear.startswith("Ακριβό: 8 % πάνω") and dear.endswith("ζήτα έκπτωση.")
    bait = buyer.verdict_lines(FLAT, {"cmp": {**CMP, "pct": -0.45}})[0]
    assert bait.startswith("Πολύ φθηνό") and bait.endswith("ρώτα γιατί.")
    assert buyer.verdict_lines(FLAT, {})[0] == "Λίγα διπλανά: δεν ξέρουμε αν η τιμή είναι καλή."
    assert buyer.verdict_lines({**FLAT, "page_checked": False}, {})[2].endswith("δεν το ελέγξαμε.")
    assert buyer.verdict_lines({**FLAT, "is_unfinished": True}, {})[2].startswith("Χτίζεται ακόμα")
    assert "ενεργειακό" in buyer.verdict_lines({**FLAT, "energy_class": None}, {})[2]
    assert buyer.verdict_lines({**FLAT, "area_m2": None, "est_monthly_rent": None}, {})[1] == (
        "Χωρίς τ.μ. στην αγγελία δεν βγάζουμε ενοίκιο."
    )


def test_recommendation_needs_more_than_one_flat_in_the_area():
    """One high-yield flat alone in an area does not make the area the recommendation."""
    from scout import area_insights, market_intel, picks

    from .test_picks import RENTS, YEAR, flat

    rents = [*RENTS, {"neighborhood": "Χολαργός (Κέντρο)", "rent_per_m2": 11.0, "samples": 20}]
    # five different ordinary flats (same m² and price would collapse as twins) …
    rows = [flat(i, 190_000 + 4_000 * i, m2=60 + 5 * i) for i in range(5)]
    # … and one alone in another area, inside the band, with the highest yield of all
    rows.append(flat(9, 180_000, hood="Χολαργός (Κέντρο)", m2=100))
    found = picks.find(
        rows, market_intel.build(rows, YEAR), rents, 200_000, year=YEAR, top=50, near_rail=False
    )
    lone = next(p for p in found if p.listing["id"] == 9)
    assert lone.gross == max(p.gross for p in found) and len(found) >= 3
    sentence = guide.recommend(found, {}, "yield")
    want = guide.accusative(area_insights.area_name(rows[0]["neighborhood"]))
    assert sentence.startswith(f"Σου προτείνω {want}:")
    assert f"{len(found) - 1} από τα {len(found)} σπίτια" in sentence


def test_area_names_in_the_accusative():
    for nom, acc in (
        ("Χολαργός", "Χολαργό"),
        ("Αμπελόκηποι", "Αμπελόκηπους"),
        ("Άγιος Δημήτριος", "Άγιο Δημήτριο"),
        ("Νέα Σμύρνη", "Νέα Σμύρνη"),
        ("Γαλάτσι", "Γαλάτσι"),
        ("Παπάγου", "Παπάγου"),
        ("Αγία Παρασκευή", "Αγία Παρασκευή"),
        ("Βύρωνας", "Βύρωνα"),
        ("Περισσός", "Περισσό"),
        ("Ηλιούπολη", "Ηλιούπολη"),
    ):
        assert guide.accusative(nom) == acc, nom


# ---- the screens -----------------------------------------------------------------------------


def test_guide_result_has_two_buttons_per_card_and_the_link(env):
    at = walk(fresh("Βρες μου σπίτι"))
    text = _text(at)
    assert "## Η πρότασή μου" in text and "## Οδηγός" not in text  # one title on the result
    assert re.search(r"Σου προτείνω [^:]+: εκεί βγαίνει \d+,\d % και ", text)
    sentence = next(m.value for m in at.markdown if m.value.startswith("Σου προτείνω"))
    assert len(sentence.split()) <= 20 and sentence.endswith(".")
    det = [b for b in at.button if (b.key or "").startswith("pick-det-")]
    fav = [b for b in at.button if (b.key or "").startswith("pick-fav-")]
    assert det and len(det) == len(fav)
    assert not any(b.label in ("Εγκρίνω", "Δεν μου κάνει", "Αναίρεση") for b in at.button)
    # the recommendation and the counts line are the only prose above the first card
    first_card = next(i for i, m in enumerate(at.markdown) if 'class="hg-card"' in m.value)
    above = [m.value for m in at.markdown[:first_card] if not m.value.startswith(("<", "## "))]
    assert len(above) == 2, above
    # the map toggle and «Πώς υπολογίζω» are below the list
    assert at.toggle(key="guide_map") and any(e.label == "Πώς υπολογίζω" for e in at.expander)


def test_saved_searches_keep_their_verdict_buttons(env):
    at = fresh(SEARCH)
    at.button(key="ex0").click().run()
    ok(at, "example")
    next(b for b in at.button if b.label == "Αποθήκευση αναζήτησης").click().run()
    ok(at, "save")
    at = fresh(SHORTLIST)
    labels = {b.label for b in at.button}
    assert "Έγκριση" in labels and "Απόρριψη" in labels and "Λεπτομέρειες" in labels


def test_listing_page_order_link_card_verdict_then_collapsed_sections(env):
    at = fresh(SEARCH)
    next(b for b in at.button if b.label == "Λεπτομέρειες").click().run()
    ok(at, "details")
    assert at.session_state["page"] == DETAIL
    md = [m.value for m in at.markdown if not m.value.startswith("<style")]
    card = next(i for i, v in enumerate(md) if 'class="hg-card"' in v)
    verdict = next(i for i, v in enumerate(md) if v.startswith("**Τι να κάνεις**"))
    assert card < verdict
    assert md[verdict].count("\n- ") == 3
    # every section after the verdict is a collapsed expander
    labels = [e.label for e in at.expander]
    for want in ("Πώς βγαίνει η βαθμολογία", "Ενοίκιο και απόδοση", "Έξι έλεγχοι επενδυτή",
                 "Τι λέει η αγγελία", "Ιστορικό τιμής"):  # fmt: skip
        assert want in labels, want
    buttons = [b.label for b in at.main.button]
    assert "Πίσω" in buttons and "Αγαπημένο" in buttons
    assert not any(b.startswith("Άνοιγμα") for b in buttons)
