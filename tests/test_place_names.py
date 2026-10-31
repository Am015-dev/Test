"""C12: one Greek name per place — the table, normalize, and the offline repair script."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scout.db as db
from scout.area_insights import _GREEK, area_name
from scout.models import Base, ListingRow
from scout.normalize import normalize
from scout.place_names import BRAND_WORDS, SEARCH_AREA_GREEK, greek_place
from scout.regions import all_areas

from .conftest import make_listing

# Every Latin-bearing ``neighborhood`` value on the published DB (2026-10-31, all statuses).
PUBLISHED_LATIN = (
    "Νέα Φιλαδέλφεια Αττικής (Όπισθεν Renault)", "Kallithea", "Nea Smyrni", "Dafni", "Galatsi",
    "Chalandri", "Nea Ionia", "Vyronas", "Zografou", "Agia Paraskevi", "Athina (Νέος Κόσμος)",
    "Marousi", "Argyroupoli", "Ilioupoli", "Peristeri", "Athina (Γκύζη)", "Athina (Κουκάκι)",
    "Cholargos", "Melissia", "Nikaia", "Petroupoli", "Psychiko", "Vouliagmeni", "Vrilissia",
    "Agios Dimitrios", "Kato Archanes", "Koukaki", "Metamorfosi", "Nea Filadelfeia",
    "Nea Filadelfia (Αμπέλια)", "Neos Kosmos", "Pefki", "Select (Γκύζη)", "Vari (Ασύρματος)",
    "ΝΕΑ ΦΙΛΑΔΕΛΦΕΙΑ (RENAULT)", "Agia Paraskevi (Κοντόπευκο)", "Alimos", "Ano Liosia",
    "Athens (Κέντρο)", "Athina (Εξάρχεια)", "Athina (Κάτω Χαλάνδρι)", "Athina (Κυψέλη)",
    "Athina (Μακρυγιάννη (Ακρόπολη))", "Athina (Μεταξουργείο)", "Athina (Παγκράτι)",
    "Athina (Πλατεία Κάνιγγος)", "Athina (Ρηγίλλης)", "Byron (Βύρωνας)", "Drapetsona",
    "Egaleo (Λιούμη)", "Filothei", "Heraklion", "Irakleio", "Iraklio", "Kolonaki",
    "Korydallos", "Kypseli", "Papagos (Παπάγου)", "Prassas", "Psichiko (Πλατεία Ελευθερίας)",
    "Vrilissia (Κέντρο)", "ΠEYKH (Κάτω Πεύκη)", "Ampelokipi (Αμπελόκηποι)",
    "Athina (Άνω Κυψέλη)", "Zografou (Κέντρο)", "Αθήνα (Όπισθεν Renault)",
)  # fmt: skip

# Repaired names whose area is not one of the covered search areas, and why.
OUTSIDE_COVERAGE = {
    "Βάρη": "Vari, a neighbour in the Vouliagmeni results",
    "Άνω Λιόσια": "a neighbour in the Kamatero results",
    "Κάτω Αρχάνες": "Crete, from the Irakleio search (dropped by CRETE_SEARCHES)",
    "Πρασάς": "Crete, from the Irakleio search (dropped by CRETE_SEARCHES)",
    "Κέντρο": "central-Athens quarter that is not a search area",
    "Μακρυγιάννη (Ακρόπολη": "central-Athens quarter that is not a search area",
    "Πλατεία Κάνιγγος": "central-Athens quarter that is not a search area",
    "Ρηγίλλης": "central-Athens quarter that is not a search area",
    "Άνω Κυψέλη": "central-Athens quarter that is not a search area",
}

_LATIN = re.compile(r"[A-Za-z]")


def _latin_left(value: str) -> bool:
    for word in BRAND_WORDS:
        value = value.replace(word, "")
    return bool(_LATIN.search(value))


def _covered() -> set[str]:
    """The Greek area name of every covered search area, as area_name gives it."""
    out = set()
    for a in all_areas():
        greek = greek_place(a)
        assert greek != a, f"search area {a} has no Greek form"
        out.add(area_name(greek))
    return out


def test_every_search_area_has_a_greek_name():
    assert set(all_areas()) <= set(SEARCH_AREA_GREEK)
    assert all(_GREEK.search(area_name(greek_place(a))) for a in all_areas())


@pytest.mark.parametrize("value", PUBLISHED_LATIN)
def test_every_published_latin_value_maps_to_greek(value):
    greek = greek_place(value)
    assert not _latin_left(greek), greek
    assert greek_place(greek) == greek  # idempotent


def test_examples_and_brand_words():
    assert greek_place("Nea Smyrni") == "Νέα Σμύρνη"
    assert greek_place("Dafni") == "Δάφνη Αττικής"
    assert greek_place("Koukaki") == "Αθήνα (Κουκάκι)"
    assert greek_place("Athina (Νέος Κόσμος)") == "Αθήνα (Νέος Κόσμος)"
    assert greek_place("Byron (Βύρωνας)") == "Βύρωνας"
    assert greek_place("Ampelokipi (Αμπελόκηποι)") == "Αθήνα (Αμπελόκηποι)"
    assert greek_place("Nea Filadelfia (Αμπέλια)") == "Νέα Φιλαδέλφεια Αττικής (Αμπέλια)"
    renault = "Νέα Φιλαδέλφεια Αττικής (Όπισθεν Renault)"
    assert greek_place(renault) == renault  # XE's own name for the spot stays
    # unknown values are never guessed
    for keep in ("Ano Cholargos", "Χολαργός (Άνω Χολαργός)", "", None):
        assert greek_place(keep) == keep


def test_area_name_resolves_every_repaired_name_to_a_covered_area():
    covered = _covered()
    for value in PUBLISHED_LATIN:
        area = area_name(greek_place(value))
        assert _GREEK.search(area), value
        assert area in covered or area in OUTSIDE_COVERAGE, (value, area)
    # the bulk of the Latin rows land in the same bucket as their Greek siblings
    assert area_name(greek_place("Kallithea")) == area_name("Καλλιθέα (Κέντρο)") == "Καλλιθέα"
    assert area_name(greek_place("Koukaki")) == area_name("Αθήνα (Κουκάκι)") == "Κουκάκι"


def test_normalize_stores_the_greek_name():
    raw = make_listing(
        source="greenacres", neighborhood="Nea Smyrni", address="Nea Smyrni"
    ).model_dump()
    lst = normalize(raw)
    assert lst.neighborhood == "Νέα Σμύρνη" and lst.address == "Νέα Σμύρνη"
    raw.update(neighborhood="Ano Cholargos", address="Ano Cholargos, Athens")
    lst = normalize(raw)
    assert lst.neighborhood == "Ano Cholargos" and lst.address == "Ano Cholargos, Athens"


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'names.db'}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", sessionmaker(bind=engine, future=True))
    rows = {
        "a": ("Kallithea", "Kallithea"),
        "b": ("Athina (Κυψέλη)", "Athina (Κυψέλη)"),
        "c": ("Χολαργός (Άνω Χολαργός)", "Χολαργός"),
        "d": ("Νέα Φιλαδέλφεια Αττικής (Όπισθεν Renault)", None),
        "e": ("Somewhere Unknown", "Somewhere Unknown"),
    }
    with db.session_scope() as s:
        for sid in rows:
            db.upsert_listing_with_history(s, make_listing(source_id=sid, url=f"https://x/{sid}"))
        for r in s.query(ListingRow):  # store the raw (pre-C12) values, bypassing normalize
            r.neighborhood, r.address = rows[r.source_id]
    yield


def _stored() -> dict[str, tuple]:
    with db.session_scope() as s:
        return {r.source_id: (r.neighborhood, r.address) for r in s.query(ListingRow)}


def test_repair_script_dry_run_then_real_then_idempotent(seeded):
    from scripts.repair_place_names import repair

    before = _stored()
    dry = repair(dry_run=True)
    assert _stored() == before
    assert (dry["neighborhood"], dry["address"], dry["rows"]) == (2, 2, 2)
    assert dry["skipped"] == {"Somewhere Unknown": 1}  # Renault is a brand word, not a leftover

    out = repair()
    assert (out["neighborhood"], out["address"], out["rows"]) == (2, 2, 2)
    after = _stored()
    assert after["a"] == ("Καλλιθέα", "Καλλιθέα")
    assert after["b"] == ("Αθήνα (Κυψέλη)", "Αθήνα (Κυψέλη)")
    assert after["c"] == before["c"] and after["d"] == before["d"]
    assert after["e"] == before["e"]  # never touches what it cannot map

    again = repair()
    assert (again["neighborhood"], again["address"], again["rows"]) == (0, 0, 0)
    assert _stored() == after
