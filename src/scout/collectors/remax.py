"""RE/MAX Greece collector — browser-free, a fourth source alongside XE, Green-Acres and
Golden Home.

remax.gr serves its sale search as **server-rendered HTML** to a plain ``requests`` session
(runner probes 2026-10-31, runs 41221767513 / 41221939367 — see ``docs/SOURCES.md``). The
sale-homes page of an area is ``/pwliseis-agora-katoikies/<id>-<slug>`` (ids from the
``xml_sitemaps/el/pwliseis-agora/katoikies.xml`` sitemap), 15 cards a page, cheapest first,
paged with ``?Property_page=N``. robots.txt disallows only ``/backend.php``, ``/ftp`` and
``/property/createPDF``.

Each card (``div.property-miniature``) has the category («Διαμέρισμα»), sub-area and
municipality, rooms, floor, m², price («€298,000») and photo count — but **no build year**,
which comparables and cross-portal twins need. So each card that passes the price/m² band
gets ONE detail-page visit (same pacing) to read «Έτος Κατασκευής» from the
characteristics table (``tr.constructionyear``). Fail-soft: no page or no row → the year
stays unknown, never guessed. A year after this one marks the flat under construction.
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

# Strategy area -> RE/MAX "<id>-<slug>", from the sale-homes sitemap (2026-10-31). The
# municipality ids sit in the 10xx block next to Χολαργός (1031); 10007 is the Athens
# quarter Αμπελόκηποι (1162 is the Thessaloniki municipality of the same name). Psychiko
# and Filothei were not found in the sitemap: they are skipped, never guessed.
AREA_IDS: dict[str, str] = {
    "Cholargos": "1031-xolargos",
    "Papagou": "1024-papagoy",
    "Agia Paraskevi": "1009-agia-paraskeyh",
    "Chalandri": "1030-xalandri",
    "Vrilissia": "1011-brilhssia",
    "Marousi": "1019-maroysi",
    "Zografou": "1043-zwgrafoy",
    "Irakleio": "1015-hrakleio",
    "Nea Filadelfeia": "1061-nea-filadelfeia",
    "Pefki": "1026-peykh",
    "Galatsi": "1055-galatsi",
    "Ampelokipoi": "10007-ampelokhpoi",
    "Metamorfosi": "1059-metamorfwsh",
}

_ID_RE = re.compile(r"/property/(\d+)-")
# Categories that are homes; land, shops, offices etc. never reach the sale-homes page,
# but a stray one is dropped rather than scored as a flat.
_HOME_WORDS = re.compile(
    r"διαμ[εέ]ρισμα|μεζον[εέ]τα|μονοκατοικ|studio|γκαρσονι[εέ]ρα|loft|ρετιρ[εέ]|βίλα|βιλα",
    re.I,
)


class RemaxCollector(Collector):
    source = "remax"
    BASE = "https://www.remax.gr"
    CARD_SELECTOR = "div.property-miniature"

    SEL_LINK = ".main-info > a"
    SEL_CATEGORY = ".category"
    SEL_SUBAREA = ".location h4.title"
    SEL_PATH = ".location .path"
    SEL_ROOMS = ".feature.rooms .label"
    SEL_FLOOR = ".feature.floor .label"
    SEL_M2 = ".feature.sqrMeters .label"
    SEL_PRICE = ".price"
    SEL_PHOTOS = ".photo-count .label"
    SEL_IMAGE = ".swiper-container img"
    SEL_NEXT_FMT = 'a[href*="Property_page={n}"]'
    SEL_DETAIL_YEAR = "tr.constructionyear td:last-child"

    def search_urls(self, strategy: Strategy) -> list[str]:
        """The sale-homes page of the run's ONE municipality; unknown area → none, logged."""
        area_id = AREA_IDS.get(strategy.search.municipality)
        if not area_id:
            logger.info("remax: no area page for %s — skipped", strategy.search.municipality)
            return []
        return [f"{self.BASE}/pwliseis-agora-katoikies/{area_id}"]

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(BROWSER_HEADERS)
        session.verify = not get_settings().scrape_ignore_https_errors
        return session

    def _fetch(self, session: requests.Session, url: str) -> str | None:
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            logger.warning("remax: fetch failed for %s: %s", url, exc)
            return None
        if not resp.ok:
            logger.warning("remax: %s returned HTTP %s", url, resp.status_code)
            return None
        return resp.text

    def _pause(self) -> None:
        s = get_settings()
        time.sleep(random.uniform(s.scrape_request_min_s, s.scrape_request_max_s))

    def collect(self) -> Iterator[dict]:
        settings = get_settings()
        search = self.strategy.search
        session = self._new_session()
        for base_url in self.search_urls(self.strategy):
            url: str | None = base_url
            page, seen, kept = 0, 0, 0
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
                        logger.warning("remax: card parse error: %s", exc)
                        continue
                    if self._keep(raw, search):
                        self._pause()
                        raw.update(self._detail_fields(self._fetch(session, raw["url"])))
                        kept += 1
                        yield raw
                nxt = tree.css_first(self.SEL_NEXT_FMT.format(n=page + 1))
                url = f"{base_url}?Property_page={page + 1}" if nxt else None
                self._pause()
            logger.info("remax: %d kept of %d cards over %d page(s)", kept, seen, page)

    @staticmethod
    def _keep(raw: dict, search) -> bool:
        """A home with a price and m² inside the strategy band."""
        if not raw.get("url") or not raw.get("price") or not raw.get("area_m2"):
            return False
        if not _HOME_WORDS.search(raw.get("title") or ""):
            return False
        if not (search.price_min <= raw["price"] <= search.price_max):
            return False
        return raw["area_m2"] >= search.area_min_m2

    @classmethod
    def _detail_fields(cls, html: str | None) -> dict:
        """Build year from the listing page; {} when the page or the row is missing."""
        if not html:
            return {}
        node = HTMLParser(html).css_first(cls.SEL_DETAIL_YEAR)
        year = parse_int(node.text(strip=True)) if node else None
        if not year or not 1800 < year < 2100:
            return {}
        return {"year_built": year, "is_unfinished": year > date.today().year}

    @staticmethod
    def _neighborhood(subarea: str | None, path: str | None) -> str | None:
        """('Φανερωμένη', 'Χολαργός, Αθήνα - Βόρεια Προάστια') → 'Χολαργός (Φανερωμένη)';
        ('Χολαργός', 'Αθήνα - Βόρεια Προάστια') → 'Χολαργός' (XE's form)."""
        if not subarea:
            return None
        if path and "," in path:
            municipality = path.split(",", 1)[0].strip()
            if municipality and municipality != subarea:
                return f"{municipality} ({subarea})"
        return subarea

    def parse_card(self, html: str, base_url: str) -> dict:
        tree = HTMLParser(html)

        def text(sel: str) -> str | None:
            node = tree.css_first(sel)
            return re.sub(r"\s+", " ", node.text(strip=True)) if node else None

        link = tree.css_first(self.SEL_LINK)
        href = link.attributes.get("href") if link else None
        url = urljoin(self.BASE, href) if href else None
        m_id = _ID_RE.search(href or "")

        category = text(self.SEL_CATEGORY)
        area_m2 = parse_float(text(self.SEL_M2))  # "92m2" (the ² is a <sup>)
        title = f"{category} {area_m2:g} τ.μ." if category and area_m2 else category
        hood = self._neighborhood(text(self.SEL_SUBAREA), text(self.SEL_PATH))

        return {
            "source": self.source,
            "source_id": m_id.group(1) if m_id else None,
            "url": url,
            "title": title,
            "price": parse_int(text(self.SEL_PRICE)),  # "€298,000"
            "area_m2": area_m2,
            "bedrooms": parse_int(text(self.SEL_ROOMS)),
            "floor": parse_floor(text(self.SEL_FLOOR)),
            "neighborhood": hood,
            "address": hood,
            "photo_count": parse_int(text(self.SEL_PHOTOS)),
            "image_url": card_image_url(tree.css(self.SEL_IMAGE), self.BASE, "remax.gr"),
        }
