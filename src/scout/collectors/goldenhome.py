"""Golden Home collector — browser-free, a third source alongside XE and Green-Acres.

Golden Home (goldenhome.gr, a Greek agency network) serves its search pages as
**server-rendered HTML** to a plain ``requests`` session (surveyed from a GitHub runner,
2026-10-31 — see ``docs/SOURCES.md``). Each area has a stable SEO URL,
``/property/pwlisi/katoikies/perioxi-<slug>`` (sale · homes · area), 30 cards a page, with
a ``li.next`` pagination link. robots.txt disallows only ``/api``, ``/backend``,
``/console``, ``?sort=`` and ``OFFSET`` URLs — none of which we use.

Cards are ``article.property-card[data-key]`` and carry everything the twins/comps logic
needs without a detail visit: id, title ("Διαμέρισμα 72τ.μ. προς πώληση"), area
("Χολαργός - Κάτω Χολαργός"), bedrooms, floor ("1   (1ος)"), m², build year, price and
the photo count. The area is rewritten to XE's "Χολαργός (Κάτω Χολαργός)" form so
cross-portal twins share a municipality key.

A build year in the future means the flat is sold off-plan: it is flagged
``is_unfinished`` (the year itself is nulled by ``normalize``), never passed off as new.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Iterator
from datetime import date
from urllib.parse import urljoin

import requests
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..config import Strategy, get_settings
from .base import USER_AGENT, Collector
from .parse_helpers import card_image_url, parse_float, parse_floor, parse_int

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

# Strategy area (XE autocomplete name) -> Golden Home area slug, read from the area
# dropdowns of the six Athens/Piraeus region pages (diag/goldenhome_areas.py, 2026-10-31).
# Golden Home has no single page for some central quarters (Exarcheia is "Εξάρχεια -
# Νεάπολη", Kolonaki "Κολωνάκι - Λυκαβηττός"); those map to that combined page.
# An area missing here is skipped with a log line, never guessed.
AREA_SLUGS: dict[str, str] = {
    "Cholargos": "holargos",
    "Papagou": "papagou",
    "Agia Paraskevi": "athens-northern-suburbs-agia-paraskevi",
    "Chalandri": "halandri",
    "Vrilissia": "vrilissia",
    "Marousi": "maroussi",
    "Nea Ionia": "athens-western-suburbs-nea-ionia",
    "Nea Filadelfeia": "athens-western-suburbs-nea-filadelfia",
    "Irakleio": "athens-northern-suburbs-iraklio",
    "Metamorfosi": "athens-western-suburbs-metamorfosi",
    "Pefki": "athens-northern-suburbs-pefki",
    "Melissia": "athens-northern-suburbs-melissia",
    "Psychiko": "paleo-psihiko",
    "Filothei": "athens-northern-suburbs-filothei",
    "Galatsi": "galatsi",
    "Zografou": "zografoy",
    "Vyronas": "vyronas",
    "Kaisariani": "kaisariani",
    "Koukaki": "koukaki-makrigianni",
    "Pagkrati": "athens-center-pagrati",
    "Ampelokipoi": "athens-center-abelokipi",
    "Exarcheia": "exarchia-neapoli",
    "Kolonaki": "kolonaki-lycabettus",
    "Neos Kosmos": "athens-center-neos-kosmos",
    "Metaxourgeio": "gazi-metaxourgio-votanikos",
    "Gkyzi": "gizi-pedion-areos",
    "Kypseli": "athens-center-kipseli",
    "Nea Smyrni": "nea-smyrni",
    "Agios Dimitrios": "athina-southern-suburbs-agios-dimitrios",
    "Dafni": "athina-southern-suburbs-dafni",
    "Ilioupoli": "ilioypoli",
    "Alimos": "alimos",
    "Argyroupoli": "athina-southern-suburbs-argiroupoli",
    "Elliniko": "athina-southern-suburbs-elliniko",
    "Kallithea": "athina-southern-suburbs-kallithea",
    "Moschato": "piraeus-suburbs-moschato",
    "Glyfada": "glyfada",
    "Palaio Faliro": "palaio-faliro",
    "Voula": "voyla",
    "Vouliagmeni": "voyliagmeni",
    "Aigaleo": "egaleo",
    "Peristeri": "athens-western-suburbs-peristeri",
    "Haidari": "haidari",
    "Ilion": "ilion",
    "Petroupoli": "petroupoli",
    "Agioi Anargyroi": "athens-western-suburbs-agii-anargiri",
    "Kamatero": "athens-western-suburbs-kamatero",
    "Piraeus": "piraeus-center",
    "Nikaia": "piraeus-suburbs-nikea",
    "Korydallos": "piraeus-suburbs-koridallos",
    "Agios Ioannis Rentis": "agios-ioannis-rentis",
    "Keratsini": "keratsini",
    "Drapetsona": "drapetsona",
}

# Titles that are not a home to live in or let: air rights, plots, shops.
_NOT_A_HOME = re.compile(r"υψο[υύ]ν|α[εέ]ρας|οικ[οό]πεδ|κατ[αά]στημα|γραφε[ιί]", re.I)
_TITLE_AREA_RE = re.compile(r"^(.*?)(\d+(?:[.,]\d+)?)\s*τ\.?μ\.?.*$")
_LEADING_INT = re.compile(r"^\s*(-?\d+)")


class GoldenHomeCollector(Collector):
    source = "goldenhome"
    BASE = "https://goldenhome.gr"
    CARD_SELECTOR = "article.property-card[data-key]"

    SEL_TITLE = ".property-title a"
    SEL_AREA_NAME = ".property-area"
    SEL_BEDROOMS = ".property-icon-number.rooms"
    SEL_FLOOR = ".property-icon-number.floor"
    SEL_M2 = ".property-icon-number.sm-area"
    SEL_YEAR = ".property-icon-number.built-year"
    SEL_PRICE = ".property-price"
    SEL_PHOTOS = ".images-icon"
    SEL_IMAGE = ".carousel-item img"
    SEL_NEXT = "ul.pagination li.next a"

    def search_urls(self, strategy: Strategy) -> list[str]:
        """The sale-homes page of the run's ONE municipality (like XE/Green-Acres, a
        per-area run scrapes only its area). Unknown area → no URL, logged."""
        slug = AREA_SLUGS.get(strategy.search.municipality)
        if not slug:
            logger.info("goldenhome: no area page for %s — skipped", strategy.search.municipality)
            return []
        return [f"{self.BASE}/property/pwlisi/katoikies/perioxi-{slug}"]

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(BROWSER_HEADERS)
        session.verify = not get_settings().scrape_ignore_https_errors
        return session

    def _fetch(self, session: requests.Session, url: str) -> str | None:
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            logger.warning("goldenhome: fetch failed for %s: %s", url, exc)
            return None
        if not resp.ok:
            logger.warning("goldenhome: %s returned HTTP %s", url, resp.status_code)
            return None
        return resp.text

    def _pause(self) -> None:
        s = get_settings()
        time.sleep(random.uniform(s.scrape_request_min_s, s.scrape_request_max_s))

    def collect(self) -> Iterator[dict]:
        settings = get_settings()
        search = self.strategy.search
        session = self._new_session()
        for url in self.search_urls(self.strategy):
            page, seen = 0, 0
            kept = 0
            while url and page < settings.scrape_max_pages:
                page += 1
                html = self._fetch(session, url)
                if not html:
                    break
                tree = HTMLParser(html)
                cards = tree.css(self.CARD_SELECTOR)
                seen += len(cards)
                for card in cards:
                    try:
                        raw = self.parse_card(card.html, base_url=url)
                    except Exception as exc:  # fail soft per card
                        logger.warning("goldenhome: card parse error: %s", exc)
                        continue
                    if self._keep(raw, search):
                        kept += 1
                        yield raw
                nxt = tree.css_first(self.SEL_NEXT)
                url = urljoin(self.BASE, nxt.attributes.get("href") or "") if nxt else None
                self._pause()
            logger.info("goldenhome: %d kept of %d cards over %d page(s)", kept, seen, page)

    @staticmethod
    def _keep(raw: dict, search) -> bool:
        """A home with a price and m² inside the strategy band (XE filters server-side)."""
        if not raw.get("url") or not raw.get("price") or not raw.get("area_m2"):
            return False
        if _NOT_A_HOME.search(raw.get("title") or ""):
            return False
        if not (search.price_min <= raw["price"] <= search.price_max):
            return False
        return raw["area_m2"] >= search.area_min_m2

    @staticmethod
    def _floor(label: str | None) -> float | None:
        """'4   (4ος)' → 4; '0  (Υπερυψ. Ισόγειο)' → 0; '0  (Ημιυπόγειο)' → -1.
        The word in brackets goes through the shared XE mapping so both portals agree."""
        if not label:
            return None
        if "(" in label:
            word = parse_floor(label.split("(", 1)[1].rstrip(") "))
            if word is not None:
                return word
        m = _LEADING_INT.match(label)
        return float(m.group(1)) if m else None

    @staticmethod
    def _neighborhood(text: str | None) -> str | None:
        """'Χολαργός\\n - Κάτω Χολαργός' → 'Χολαργός (Κάτω Χολαργός)' (XE's form)."""
        if not text:
            return None
        parts = [p.strip() for p in re.sub(r"\s+", " ", text).split(" - ", 1)]
        if len(parts) == 2 and parts[1]:
            return f"{parts[0]} ({parts[1]})"
        return parts[0] or None

    def parse_card(self, html: str, base_url: str) -> dict:
        tree = HTMLParser(html)
        card = tree.css_first(self.CARD_SELECTOR)

        def text(sel: str) -> str | None:
            node = tree.css_first(sel)
            return node.text(strip=True) if node else None

        listing_id = card.attributes.get("data-key") if card else None
        link = tree.css_first(self.SEL_TITLE)
        href = link.attributes.get("href") if link else None
        url = urljoin(self.BASE, href) if href else None

        # "Διαμέρισμα 72τ.μ. προς πώληση" → "Διαμέρισμα 72 τ.μ." (XE's title form).
        raw_title = text(self.SEL_TITLE)
        title = raw_title
        m = _TITLE_AREA_RE.match(raw_title or "")
        if m:
            title = f"{m.group(1).strip()} {m.group(2)} τ.μ."

        area_m2 = parse_float(text(self.SEL_M2))
        if area_m2 is None and m:
            area_m2 = parse_float(m.group(2))

        year = parse_int(text(self.SEL_YEAR))
        hood = self._neighborhood(text(self.SEL_AREA_NAME))

        return {
            "source": self.source,
            "source_id": listing_id,
            "url": url,
            "title": title,
            "price": parse_int(text(self.SEL_PRICE)),
            "area_m2": area_m2,
            "bedrooms": parse_int(text(self.SEL_BEDROOMS)),
            "floor": self._floor(text(self.SEL_FLOOR)),
            "year_built": year,
            # A build year after this year = sold off-plan, i.e. under construction.
            "is_unfinished": bool(year and year > date.today().year),
            "neighborhood": hood,
            "address": hood,
            "photo_count": parse_int(text(self.SEL_PHOTOS)),
            "image_url": card_image_url(tree.css(self.SEL_IMAGE), self.BASE, "goldenhome.gr"),
        }
