"""The regulatory layer makes claims that change an investment decision, so its logic
is checked: frozen zones block new short-lets, the freeze is Athens-only, GV needs both
price and size, and only EPC-C-or-lower is a subsidy candidate."""

from __future__ import annotations

from scout.regulatory import golden_visa_status, renovation_subsidy, str_legality


def test_frozen_zone_blocks_new_short_let():
    for hood in ("Koukaki", "koukaki", "Néos Kósmos", "Neos Kosmos", "Pagkrati"):
        r = str_legality(hood)
        assert r.status == "FROZEN", hood
        assert r.can_new_short_let is False, hood


def test_expanding_risk_is_allowed_today_not_frozen():
    r = str_legality("Kypseli")
    assert r.status == "EXPANDING_RISK"
    assert r.can_new_short_let is True  # legally allowed today


def test_suburbs_outside_athens_are_allowed():
    for hood in ("Marousi", "Glyfada", "Cholargos", "Chalandri", "Piraeus"):
        assert str_legality(hood).status == "ALLOWED", hood


def test_unknown_neighborhood_is_unknown_not_guessed():
    assert str_legality(None).status == "UNKNOWN"
    assert str_legality("").status == "UNKNOWN"


def test_golden_visa_needs_price_and_area():
    assert golden_visa_status(850_000, 130).qualifies is True
    assert golden_visa_status(850_000, 90).qualifies is False  # too small
    assert golden_visa_status(500_000, 130).qualifies is False  # below threshold
    assert golden_visa_status(None, 130).qualifies is None  # unknown price


def test_renovation_candidate_only_c_or_lower():
    assert renovation_subsidy("E", 1975).candidate is True
    assert renovation_subsidy("A+", 2015).candidate is False
    assert renovation_subsidy("B", 2010).candidate is False
    assert renovation_subsidy(None, 1975).candidate is False


def test_renovation_accepts_greek_epc_letters():
    # Data stores Greek letters: Γ=C, Δ=D, Ε=E, Ζ=F, Η=G → all eligible; Α/Β not.
    for greek in ("Γ", "Δ", "Ε", "Ζ", "Η"):
        assert renovation_subsidy(greek, 1975).candidate is True, greek
    for greek in ("Α+", "Α", "Β", "Β+"):
        assert renovation_subsidy(greek, 2015).candidate is False, greek
    # "Εξαιρείται" (exempt) starts with Ε but must NOT be read as class E.
    assert renovation_subsidy("Εξαιρείται", 1970).candidate is False
    # pre-1980 bonus text appears only for old builds
    assert "πριν το 1980" in renovation_subsidy("F", 1970).detail
    assert "πριν το 1980" not in renovation_subsidy("F", 2000).detail


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("ok")


def test_flags_frozen_zone_by_greek_subarea_and_latin_search_area():
    from scout.regulatory import flags

    for d in (
        {"neighborhood": "Αθήνα (Κουκάκι)"},
        {"neighborhood": "Αθήνα", "search_area": "Koukaki"},
        {"neighborhood": "Αθήνα (Νέος Κόσμος)", "search_area": "Neos Kosmos"},
    ):
        out = flags(d)
        assert len(out) == 1 and "δεν εκδίδεται νέο ΑΜΑ" in out[0], d
        assert "31/12/2026" in out[0] and "ν. 5170/2025" in out[0]


def test_flags_watch_zone_is_not_a_ban():
    from scout.regulatory import flags

    out = flags({"neighborhood": "Αθήνα (Αμπελόκηποι)", "search_area": "Ampelokipoi"})
    assert len(out) == 1 and "επιτρέπεται σήμερα" in out[0] and "δεν εκδίδεται" not in out[0]


def test_flags_nothing_for_suburbs_or_unknown():
    from scout.regulatory import flags

    assert flags({"neighborhood": "Χολαργός (Κέντρο)", "search_area": "Cholargos"}) == []
    assert flags({}) == []


def test_flags_golden_visa_and_subsidy_only_when_data_supports():
    from scout.regulatory import flags

    big = flags({"price": 900_000, "area_m2": 140, "energy_class": "Δ", "neighborhood": "Μαρούσι"})
    assert any(f.startswith("Golden Visa: επιλέξιμο") for f in big)
    assert any("Εξοικονομώ" in f and "κλάση Δ" in f for f in big)
    small = flags({"price": 300_000, "area_m2": 140, "energy_class": "Β"})
    assert small == []
    assert not any(ord(c) > 0x2600 and c in "❌✓⚠🛂🔧" for f in big for c in f)  # no emoji
