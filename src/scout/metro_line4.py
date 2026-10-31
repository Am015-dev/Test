"""Athens Metro Line 4 (Άλσος Βεΐκου–Γουδή), Section A — stations under construction.

Static table, no network. Source for the stations, their municipality and the planned
opening: Wikipedia, «Line 4 (Athens Metro)»,
https://en.wikipedia.org/wiki/Line_4_(Athens_Metro) — read 2026-10-31. The article lists
15 stations of Section A (Ελληνικό Μετρό: https://www.emetro.gr/?page_id=8334) and gives
"2032" as the planned opening of every station, citing Kathimerini, 9 Apr 2026, «Athens
metro line 4 faces yet another delay»
(https://www.ekathimerini.com/economy/1300526/athens-metro-line-4-faces-yet-another-delay/):
originally 2029, "more realistically at least 2032". That horizon is a press estimate, not a
contract date, and the UI prints it as «ορίζοντας 2032». Sections C–E (beyond Goudi) are
not under construction and are not listed.

The listings carry no exact coordinates, so the link between a station and a listing is by
NEIGHBOURHOOD NAME only (the XE sub-area in brackets, e.g. «Γαλάτσι (Άλσος Βεΐκου)»):

* ``line4_station(d)`` — a station only when the listing's own sub-area carries the station's
  name (Άλσος Βεΐκου, Κυψέλη, Εξάρχεια, Ιλίσια, Γουδή, Κολωνάκι, Ζωγράφου-Κέντρο, Άνω Κυψέλη
  for Ελικώνος). A municipality-wide link would claim a station for streets kilometres away.
* ``line4_stations(area)`` — the stations that sit in an AREA (an ``area_insights.area_name``
  value), for the area card; stations in central Athens quarters we cannot match by a
  sub-area name (Δικαστήρια, Αλεξάνδρας, Ακαδημία, Ευαγγελισμός, Πανεπιστημιούπολη, and
  Γαλάτσι/Καισαριανή for single flats) are listed against their municipality only.

Pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass

OPENING = 2032
SOURCE_URL = "https://en.wikipedia.org/wiki/Line_4_(Athens_Metro)"
SOURCE_NOTE = (
    "Πηγή: Wikipedia «Line 4 (Athens Metro)», με παραπομπή στην Καθημερινή (9/4/2026): "
    "αρχικά 2029, ρεαλιστικά τουλάχιστον 2032."
)


@dataclass(frozen=True)
class Station:
    name: str  # Greek, as on emetro.gr
    areas: tuple[str, ...]  # ``area_insights.area_name`` values the station belongs to
    hoods: tuple[str, ...] = ()  # XE sub-areas (text in brackets) named after the station
    opening: int = OPENING


# Order = along the line, Άλσος Βεΐκου → Γουδή.
STATIONS: tuple[Station, ...] = (
    Station("Άλσος Βεΐκου", ("Γαλάτσι",), ("Άλσος Βεΐκου",)),
    Station("Γαλάτσι", ("Γαλάτσι",)),
    Station("Ελικώνος", ("Γαλάτσι", "Κυψέλη"), ("Άνω Κυψέλη",)),
    Station("Κυψέλη", ("Κυψέλη",), ("Κυψέλη",)),
    Station("Δικαστήρια", ()),
    Station("Αλεξάνδρας", ()),
    Station("Εξάρχεια", ("Εξάρχεια",), ("Εξάρχεια",)),
    Station("Ακαδημία", ()),
    Station("Κολωνάκι", ("Κολωνάκι",), ("Κολωνάκι",)),
    Station("Ευαγγελισμός", ()),
    Station("Καισαριανή", ("Καισαριανή",)),
    Station("Πανεπιστημιούπολη", ("Καισαριανή",)),
    Station("Ιλίσια", ("Ζωγράφου", "Ιλίσια"), ("Ιλίσια",)),
    Station("Ζωγράφου", ("Ζωγράφου",), ("Κέντρο",)),
    Station("Γουδή", ("Ζωγράφου", "Γουδή"), ("Γουδή",)),
)


def _hood(neighborhood: str | None) -> tuple[str, str]:
    """'Ζωγράφου (Ιλίσια)' → ('Ζωγράφου', 'Ιλίσια'); no brackets → (text, '')."""
    text = (neighborhood or "").strip()
    if "(" not in text:
        return text, ""
    head, tail = text.split("(", 1)
    return head.strip(), tail.rstrip(") ").strip()


def line4_station(d: dict) -> str | None:
    """Line 4 station named by the listing's own sub-area, else None (see module docstring).

    The «Κέντρο» sub-area counts only for Ζωγράφου (the station of the same name)."""
    muni, hood = _hood(d.get("neighborhood"))
    if not hood:
        return None
    for s in STATIONS:
        if hood not in s.hoods:
            continue
        if hood == "Κέντρο" and muni != s.name:
            continue
        return s.name
    return None


def line4_stations(area: str) -> list[str]:
    """Names of the Line 4 stations in ``area`` (an ``area_insights.area_name`` value), in
    line order; empty when the area has none."""
    return [s.name for s in STATIONS if area in s.areas]


def line4_text(stations: list[str]) -> str:
    """«Μετρό Γραμμή 4 υπό κατασκευή: Γαλάτσι, Ελικώνος (ορίζοντας 2032)» or ''."""
    if not stations:
        return ""
    return f"Μετρό Γραμμή 4 υπό κατασκευή: {', '.join(stations)} (ορίζοντας {OPENING})"
