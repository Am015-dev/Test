"""One Greek name per place: Latin place names → the Greek «Δήμος (γειτονιά)» form.

XE stores neighbourhoods as «Χολαργός (Άνω Χολαργός)» and central Athens as «Αθήνα (Κουκάκι)».
Some portals and some XE cards name the place in Latin instead (Green-Acres: «Nea Smyrni»;
XE: «Athina (Νέος Κόσμος)», «Byron (Βύρωνας)»). Left alone they reach the UI in Latin and land
in a separate area bucket from the Greek rows of the same place. ``greek_place`` maps them:

1. ``EXACT`` — whole values the two rules below cannot get right;
2. a bare central-Athens quarter («Koukaki») → «Αθήνα (Κουκάκι)» (``ATHENS_QUARTERS``);
3. a Latin municipality, bare or before a bracket («Athina (Κυψέλη)») → its Greek form
   (``MUNICIPALITIES``); a bracket that only repeats the municipality is dropped.

Anything else is returned unchanged (never guessed). ``search_area`` stays Latin: it is the
internal key of strategy.yaml, ``regions`` and the centroid table, not a displayed name;
``SEARCH_AREA_GREEK`` gives its Greek name. ``BRAND_WORDS`` are Latin words that are a
portal's own name for a spot («Νέα Φιλαδέλφεια Αττικής (Όπισθεν Renault)») and stay.
"""

from __future__ import annotations

# Latin municipality (every search area and every portal spelling seen) → XE's Greek form.
MUNICIPALITIES: dict[str, str] = {
    # search areas (regions.REGIONS), outside central Athens
    "Zografou": "Ζωγράφου",
    "Vyronas": "Βύρωνας",
    "Kaisariani": "Καισαριανή",
    "Galatsi": "Γαλάτσι",
    "Cholargos": "Χολαργός",
    "Papagou": "Παπάγου",
    "Agia Paraskevi": "Αγία Παρασκευή",
    "Chalandri": "Χαλάνδρι",
    "Vrilissia": "Βριλήσσια",
    "Marousi": "Μαρούσι",
    "Nea Ionia": "Νέα Ιωνία",
    "Nea Filadelfeia": "Νέα Φιλαδέλφεια Αττικής",
    "Irakleio": "Ηράκλειο",
    "Metamorfosi": "Μεταμόρφωση",
    "Pefki": "Πεύκη",
    "Melissia": "Μελίσσια",
    "Psychiko": "Ψυχικό",
    "Filothei": "Φιλοθέη",
    "Nea Smyrni": "Νέα Σμύρνη",
    "Agios Dimitrios": "Άγιος Δημήτριος Αττικής",
    "Dafni": "Δάφνη Αττικής",
    "Ilioupoli": "Ηλιούπολη",
    "Alimos": "Άλιμος",
    "Argyroupoli": "Αργυρούπολη",
    "Elliniko": "Ελληνικό",
    "Kallithea": "Καλλιθέα",
    "Moschato": "Μοσχάτο",
    "Glyfada": "Γλυφάδα",
    "Palaio Faliro": "Παλαιό Φάληρο",
    "Voula": "Βούλα",
    "Vouliagmeni": "Βουλιαγμένη",
    "Aigaleo": "Αιγάλεω",
    "Peristeri": "Περιστέρι",
    "Haidari": "Χαϊδάρι",
    "Ilion": "Ίλιον",
    "Petroupoli": "Πετρούπολη",
    "Agioi Anargyroi": "Άγιοι Ανάργυροι",
    "Kamatero": "Καματερό",
    "Piraeus": "Πειραιάς",
    "Nikaia": "Νίκαια",
    "Korydallos": "Κορυδαλλός",
    "Agios Ioannis Rentis": "Άγιος Ιωάννης Ρέντης",
    "Tavros": "Ταύρος Αττικής",
    "Keratsini": "Κερατσίνι",
    "Perama": "Πέραμα",
    "Drapetsona": "Δραπετσώνα",
    # other spellings the portals use
    "Athina": "Αθήνα",
    "Athens": "Αθήνα",
    "Byron": "Βύρωνας",
    "Papagos": "Παπάγου",
    "Psichiko": "Ψυχικό",
    "Egaleo": "Αιγάλεω",
    "Nea Filadelfia": "Νέα Φιλαδέλφεια Αττικής",
    "Iraklio": "Ηράκλειο",
    "Heraklion": "Ηράκλειο",
    # outside the search areas, seen as neighbours in their results (comparables only)
    "Vari": "Βάρη",
    "Ano Liosia": "Άνω Λιόσια",
    "Kato Archanes": "Κάτω Αρχάνες",  # Heraklion, Crete (the "Irakleio" search)
    "Prassas": "Πρασάς",  # Heraklion, Crete
}

# Central-Athens quarters (search areas) → the quarter, stored as «Αθήνα (quarter)».
ATHENS_QUARTERS: dict[str, str] = {
    "Koukaki": "Κουκάκι",
    "Pagkrati": "Παγκράτι",
    "Ampelokipoi": "Αμπελόκηποι",
    "Ampelokipi": "Αμπελόκηποι",
    "Exarcheia": "Εξάρχεια",
    "Kolonaki": "Κολωνάκι",
    "Neos Kosmos": "Νέος Κόσμος",
    "Metaxourgeio": "Μεταξουργείο",
    "Gkyzi": "Γκύζη",
    "Kypseli": "Κυψέλη",
}

# Whole values the rules get wrong: a mislabelled municipality, Latin look-alike letters.
EXACT: dict[str, str] = {
    # XE card in the Chalandri search, at Chalandri's point: the quarter is Κάτω Χαλάνδρι
    "Athina (Κάτω Χαλάνδρι)": "Χαλάνδρι (Κάτω Χαλάνδρι)",
    # XE prefixes a few Γκύζη cards with «Select»; the place is the Athens quarter
    "Select (Γκύζη)": "Αθήνα (Γκύζη)",
    # Latin E and Y inside a Greek word
    "ΠEYKH (Κάτω Πεύκη)": "Πεύκη (Κάτω Πεύκη)",
    # XE card in the Nea Filadelfeia search, at its point; the Renault spot is there
    "Αθήνα (Όπισθεν Renault)": "Νέα Φιλαδέλφεια Αττικής (Όπισθεν Renault)",
    # Golden Home, upper case; the Renault spot keeps its brand name
    "ΝΕΑ ΦΙΛΑΔΕΛΦΕΙΑ (RENAULT)": "Νέα Φιλαδέλφεια Αττικής (Renault)",
}

# Latin words that are the portal's own name for a spot and stay inside a Greek name.
BRAND_WORDS: tuple[str, ...] = ("Renault",)

# Every search area's Greek name, as ``area_insights.area_name`` returns it.
SEARCH_AREA_GREEK: dict[str, str] = {**MUNICIPALITIES, **ATHENS_QUARTERS}


def greek_place(value: str | None) -> str | None:
    """«Nea Smyrni» → «Νέα Σμύρνη»; «Athina (Κυψέλη)» → «Αθήνα (Κυψέλη)»; unknown → unchanged."""
    if not value:
        return value
    value = value.strip()
    if value in EXACT:
        return EXACT[value]
    head, bracket, rest = value.partition(" (")
    if not bracket and head in ATHENS_QUARTERS:
        return f"Αθήνα ({ATHENS_QUARTERS[head]})"
    if head in ATHENS_QUARTERS and rest.rstrip(")").strip() == ATHENS_QUARTERS[head]:
        return f"Αθήνα ({ATHENS_QUARTERS[head]})"  # «Ampelokipi (Αμπελόκηποι)»
    greek = MUNICIPALITIES.get(head)
    if greek is None:
        return value
    if not bracket or rest.rstrip(")").strip() == greek:
        return greek  # «Byron (Βύρωνας)» → «Βύρωνας»
    return f"{greek} ({rest}"
