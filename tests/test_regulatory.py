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
    # pre-1980 bonus text appears only for old builds
    assert "Pre-1980" in renovation_subsidy("F", 1970).detail
    assert "Pre-1980" not in renovation_subsidy("F", 2000).detail


if __name__ == "__main__":
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("ok")
