"""Metro Line 4 table: 15 stations, matched to listings only by sub-area name."""

from __future__ import annotations

from scout import metro_line4 as m


def test_fifteen_stations_in_line_order_with_one_horizon():
    names = [s.name for s in m.STATIONS]
    assert len(names) == 15 and names[0] == "Άλσος Βεΐκου" and names[-1] == "Γουδή"
    assert {s.opening for s in m.STATIONS} == {2032}
    assert m.SOURCE_URL.startswith("https://en.wikipedia.org/wiki/Line_4")


def test_listing_matches_only_by_station_named_subarea():
    assert m.line4_station({"neighborhood": "Γαλάτσι (Άλσος Βεΐκου)"}) == "Άλσος Βεΐκου"
    assert m.line4_station({"neighborhood": "Αθήνα (Κυψέλη)"}) == "Κυψέλη"
    assert m.line4_station({"neighborhood": "Αθήνα (Άνω Κυψέλη)"}) == "Ελικώνος"
    assert m.line4_station({"neighborhood": "Ζωγράφου (Ιλίσια)"}) == "Ιλίσια"
    assert m.line4_station({"neighborhood": "Ζωγράφου (Κέντρο)"}) == "Ζωγράφου"
    # «Κέντρο» is a station sub-area only in Ζωγράφου
    assert m.line4_station({"neighborhood": "Χολαργός (Κέντρο)"}) is None
    # other Γαλάτσι sub-areas: no claim for a single flat
    assert m.line4_station({"neighborhood": "Γαλάτσι (Λαμπρινή)"}) is None
    assert m.line4_station({"neighborhood": None}) is None
    assert m.line4_station({"neighborhood": "Γαλάτσι"}) is None


def test_area_level_stations_and_text():
    assert m.line4_stations("Γαλάτσι") == ["Άλσος Βεΐκου", "Γαλάτσι", "Ελικώνος"]
    assert m.line4_stations("Ζωγράφου") == ["Ιλίσια", "Ζωγράφου", "Γουδή"]
    assert m.line4_stations("Χολαργός") == []
    assert m.line4_text(["Γαλάτσι"]) == "Μετρό Γραμμή 4 υπό κατασκευή: Γαλάτσι (ορίζοντας 2032)"
    assert m.line4_text([]) == ""
