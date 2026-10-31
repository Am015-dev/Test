"""RE/MAX collector: offline parse tests on a real captured page, pagination, the SOURCES
toggle, and what a card without a build year means downstream."""

from __future__ import annotations

from pathlib import Path

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from scout import market_intel as mi
from scout.collectors import SOURCE_LABELS, default_collectors, enabled_sources
from scout.collectors.remax import AREA_IDS, RemaxCollector
from scout.config import Strategy
from scout.normalize import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "remax_search.html"


def _collector(municipality: str = "Cholargos") -> RemaxCollector:
    strategy = Strategy()
    strategy.search.municipality = municipality
    return RemaxCollector(strategy, save_raw=False)


def _cards() -> dict[str, dict]:
    c = _collector()
    tree = HTMLParser(FIXTURE.read_text(encoding="utf-8"))
    raws = [c.parse_card(n.html, base_url="x") for n in tree.css(c.CARD_SELECTOR)]
    return {r["source_id"]: r for r in raws}


def test_parse_card_reads_every_field_from_the_real_card():
    r = _cards()["386739"]
    assert r["source"] == "remax"
    assert r["url"] == "https://www.remax.gr/property/386739-polisi-diamerisma-anw-xolargos"
    assert r["title"] == "Διαμέρισμα 75 τ.μ."
    assert r["price"] == 255_000  # "€255,000"
    assert r["area_m2"] == 75.0
    assert r["bedrooms"] == 1
    assert r["floor"] == 0.0  # "Ισόγειο"
    assert r["neighborhood"] == "Χολαργός (Άνω Χολαργός)"  # XE's form
    assert r["photo_count"] == 8
    assert r["image_url"].startswith("https://www.remax.gr/assets/media/properties/")
    assert "year_built" not in r  # the card has none; never guessed


def test_municipality_level_card_and_half_floor():
    cards = _cards()
    assert cards["404791"]["neighborhood"] == "Χολαργός"  # path has no sub-area
    assert cards["409530"]["floor"] == 0.5  # "Ημιόροφος", shared XE mapping
    assert cards["357565"]["title"] == "Μεζονέτα 126 τ.μ."


def test_keep_band_and_homes_only():
    r = _cards()["386739"]
    search = Strategy().search
    search.price_min, search.price_max, search.area_min_m2 = 100_000, 300_000, 45
    assert RemaxCollector._keep(r, search)
    assert not RemaxCollector._keep({**r, "price": 450_000}, search)
    assert not RemaxCollector._keep({**r, "area_m2": 30}, search)
    assert not RemaxCollector._keep({**r, "title": "Κατάστημα 75 τ.μ."}, search)


def test_parse_card_fails_soft_on_garbage():
    raw = _collector().parse_card("<div class='property-miniature'></div>", "x")
    assert raw["source_id"] is None and raw["price"] is None and raw["url"] is None
    assert normalize(raw) is None


def test_search_url_is_the_run_municipality_only():
    c = _collector()
    assert c.search_urls(c.strategy) == [
        "https://www.remax.gr/pwliseis-agora-katoikies/1031-xolargos"
    ]
    unknown = _collector("Psychiko")  # not in the sitemap: skipped, not guessed
    assert unknown.search_urls(unknown.strategy) == []


def test_weekly_areas_mapped_except_the_two_not_in_the_sitemap():
    weekly = (
        "Cholargos,Papagou,Agia Paraskevi,Chalandri,Vrilissia,Marousi,Zografou,Psychiko,"
        "Filothei,Irakleio,Nea Filadelfeia,Pefki,Galatsi,Ampelokipoi,Metamorfosi"
    ).split(",")
    assert [a for a in weekly if a not in AREA_IDS] == ["Psychiko", "Filothei"]


def test_collect_follows_property_page_and_stops(monkeypatch):
    page1 = FIXTURE.read_text(encoding="utf-8")
    page2 = page1.replace("Property_page=2", "Property_page=1")  # no link to page 3
    fetched: list[str] = []

    def fake_fetch(self, session, url):
        fetched.append(url)
        return page1 if len(fetched) == 1 else page2.replace("409530", "1")

    monkeypatch.setattr(RemaxCollector, "_fetch", fake_fetch)
    monkeypatch.setattr(RemaxCollector, "_pause", lambda self: None)
    c = _collector()
    c.strategy.search.price_min, c.strategy.search.price_max = 50_000, 1_000_000
    raws = list(c.collect())
    assert fetched == [
        "https://www.remax.gr/pwliseis-agora-katoikies/1031-xolargos",
        "https://www.remax.gr/pwliseis-agora-katoikies/1031-xolargos?Property_page=2",
    ]
    assert len(raws) == 8 and {r["source"] for r in raws} == {"remax"}


def test_sources_toggle_and_label(monkeypatch):
    monkeypatch.setenv("SOURCES", "xe,remax")
    assert enabled_sources() == ["xe", "remax"]
    assert [c.source for c in default_collectors(Strategy())] == ["xe", "remax"]
    assert SOURCE_LABELS["remax"] == "RE/MAX"


def test_no_build_year_means_no_twin_and_no_age_comps():
    """Honest limit: without a year a RE/MAX card is not matched to its XE twin."""
    g = normalize(_cards()["386739"]).model_dump()
    g.update(id=2, price_per_m2=g["price"] / g["area_m2"])
    x = {**g, "id": 1, "source": "xe", "year_built": 1980}
    intel = mi.build([x, g], year=2026)
    assert intel.twins(x) == [] and intel.twins(g) == []
