"""Athens regional grouping — the familiar map buyers actually think in.

Investors and agents don't shop by ``search_area`` municipality codes; they think in
the classic Attica regions — *Κέντρο, Βόρεια/Νότια/Δυτικά Προάστια, Πειραιάς*. This maps
each scraped municipality/locality to its region so the UI can filter and group by region
without any schema change (``search_area`` already stores the municipality; the region is
derived here). Keys are the exact strings passed to the collector (English transliterations
XE's autocomplete resolves), so a lookup is a plain dict hit.

Order of regions is the display order (centre first, then the ring of suburbs, then the
port). Adding a new scrape area only requires adding it to the right list below.
"""

from __future__ import annotations

# region (Greek display name) -> the municipalities/localities it contains
REGIONS: dict[str, list[str]] = {
    "Κέντρο Αθήνας": [
        "Koukaki",
        "Pagkrati",
        "Ampelokipoi",
        "Exarcheia",
        "Kolonaki",
        "Neos Kosmos",
        "Metaxourgeio",
        "Gkyzi",
        "Kypseli",
        "Zografou",
        "Vyronas",
        "Kaisariani",
        "Galatsi",
    ],
    "Βόρεια Προάστια": [
        "Cholargos",
        "Papagou",
        "Agia Paraskevi",
        "Chalandri",
        "Vrilissia",
        "Marousi",
        "Nea Ionia",
        "Nea Filadelfeia",
        "Irakleio",
        "Metamorfosi",
        "Pefki",
        "Melissia",
        "Psychiko",
        "Filothei",
    ],
    "Νότια Προάστια": [
        "Nea Smyrni",
        "Agios Dimitrios",
        "Dafni",
        "Ilioupoli",
        "Alimos",
        "Argyroupoli",
        "Elliniko",
        "Kallithea",
        "Moschato",
        "Glyfada",
        "Palaio Faliro",
        "Voula",
        "Vouliagmeni",
    ],
    "Δυτικά Προάστια": [
        "Aigaleo",
        "Peristeri",
        "Haidari",
        "Ilion",
        "Petroupoli",
        "Agioi Anargyroi",
        "Kamatero",
    ],
    "Πειραιάς": [
        "Piraeus",
        "Nikaia",
        "Korydallos",
        "Agios Ioannis Rentis",
        "Tavros",
        "Keratsini",
        "Perama",
        "Drapetsona",
    ],
}

# Reverse index: municipality -> region (built once).
REGION_OF: dict[str, str] = {area: region for region, areas in REGIONS.items() for area in areas}


def region_of(search_area: str | None) -> str | None:
    """The region a municipality belongs to, or None if it isn't in the map."""
    if not search_area:
        return None
    return REGION_OF.get(search_area)


def all_areas() -> list[str]:
    """Every municipality across all regions, in display order (centre → port)."""
    return [area for areas in REGIONS.values() for area in areas]
