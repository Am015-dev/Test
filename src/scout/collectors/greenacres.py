"""Green-Acres collector — browser-free, a genuine SECOND source alongside XE.

Green-Acres is an international portal that (unlike Spitogatos/Indomio, which sit
behind PerimeterX/Cloudflare and block server clients) serves its per-city listing
pages as **static server-rendered HTML** to a plain ``requests`` session. Each city
has a stable SEO URL — ``/property-for-sale/<city-slug>`` — that returns every one of
that city's listings in a single GET (each target suburb has < 24, the AJAX page size,
so no pagination is needed).

Cards are ``div.announce-card[data-advertid]`` (skeleton placeholders lack the
attribute, so the selector skips them). The detail URL is base64-encoded in ``data-o``;
its 3rd path segment is the property type, which we use to keep only residential
apartments/houses. Green-Acres pages append a "similar listings" tail from *other*
areas, so we keep only cards whose location matches the searched suburb.

Detail pages carry no JSON-LD but expose the listing's coordinates in a
``window.advert = { coordinates: { latitude, longitude } }`` script — enough for an
accurate walking distance to the nearest metro. Energy class / build year are not
published here, so those stay unknown (scoring imputes them, fail-soft).
"""

from __future__ import annotations

import base64
import binascii
import logging
import random
import re
import time
from collections.abc import Iterator
from html import unescape

import requests
from selectolax.parser import HTMLParser

from ..config import Strategy, get_settings
from .base import USER_AGENT, Collector
from .parse_helpers import parse_float, parse_int

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,el;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

# Detail page embeds the precise location in a JS object; the box centre is the listing.
_COORDS_RE = re.compile(
    r"coordinates\s*:\s*\{\s*latitude\s*:\s*(-?\d+\.\d+)\s*,\s*longitude\s*:\s*(-?\d+\.\d+)"
)
# Residential types worth keeping (the URL's 3rd path segment). Drop business-premises,
# land, parking, etc. — this tool is about homes to let.
_RESIDENTIAL_TYPES = {"apartment", "house", "luxury-property", "property"}
# A property photo URL sitting in the card (carousel slides / img src).
_IMG_RE = re.compile(
    r"https://[a-z0-9.\-/_]*green-acres\.com/[^\"'&\s]+\.(?:jpg|jpeg|webp|png)", re.I
)


class GreenAcresCollector(Collector):
    source = "greenacres"
    BASE = "https://www.green-acres.gr"
    CARD_SELECTOR = "div.announce-card[data-advertid]"

    SEL_PRICE = "strong.info-price"
    SEL_LOCATION = ".announce-localisation"
    SEL_AREA = 'div[title="Living area"]'
    SEL_BEDROOMS = 'div[title="Bedrooms"]'

    @staticmethod
    def _slug(area: str) -> str:
        """Green-Acres city slug for an area name (e.g. 'Agia Paraskevi' -> 'agia-paraskevi')."""
        return re.sub(r"\s+", "-", area.strip().lower())

    def search_urls(self, strategy: Strategy) -> list[str]:
        """One static per-city page for the run's scoped municipality. A missing city
        404s and is skipped in ``collect`` — never fatal.

        Scoped to ``municipality`` (the ONE area this run scrapes), not ``all_areas()``:
        ``run_for_area`` runs the pipeline once per area, so pulling every area here made
        a single per-area run re-scrape all 55 areas (with a 4-7s detail fetch per card),
        blowing past the daily job's 45-min collect timeout — the process was killed
        before ``run()`` reached its store phase, so no ``last_seen`` ever advanced. XE is
        scoped the same way."""
        return [f"{self.BASE}/property-for-sale/{self._slug(strategy.search.municipality)}"]

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(BROWSER_HEADERS)
        session.verify = not get_settings().scrape_ignore_https_errors
        return session

    def _fetch(self, session: requests.Session, url: str) -> str | None:
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            logger.warning("greenacres: fetch failed for %s: %s", url, exc)
            return None
        if resp.status_code == 404:
            logger.info("greenacres: no page for %s (404) — skipping", url)
            return None
        if not resp.ok:
            logger.warning("greenacres: %s returned HTTP %s", url, resp.status_code)
            return None
        return resp.text

    def collect(self) -> Iterator[dict]:
        settings = get_settings()
        s = self.strategy.search
        session = self._new_session()
        for area, url in zip([s.municipality], self.search_urls(self.strategy), strict=True):
            html = self._fetch(session, url)
            if not html:
                continue
            if self.save_raw:
                self.save_raw_html(f"search-{self._slug(area)}", html)
            cards = HTMLParser(html).css(self.CARD_SELECTOR)
            kept = 0
            for card in cards:
                try:
                    raw = self.parse_card(card.html, base_url=url)
                except Exception as exc:  # fail soft per card
                    logger.warning("greenacres: card parse error: %s", exc)
                    continue
                if not self._keep(raw, area, s):
                    continue
                self._enrich_from_detail(session, raw)
                kept += 1
                yield raw
                time.sleep(
                    random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s)
                )
            logger.info("greenacres: %d kept of %d cards on %s", kept, len(cards), url)
            time.sleep(random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s))

    def _keep(self, raw: dict, area: str, search) -> bool:
        """Keep only residential listings in the searched suburb and within the price/area
        band. Drops the cross-area 'similar listings' tail and out-of-band noise."""
        if not raw.get("url") or not raw.get("price") or not raw.get("area_m2"):
            return False
        if raw.get("property_type") not in _RESIDENTIAL_TYPES:
            return False
        # Location must match the searched suburb (else it's the similar-listings tail).
        loc = (raw.get("neighborhood") or "").lower()
        if self._slug(area).replace("-", " ") not in loc:
            return False
        if not (search.price_min <= raw["price"] <= search.price_max):
            return False
        if raw["area_m2"] < search.area_min_m2:
            return False
        return True

    def parse_card(self, html: str, base_url: str) -> dict:
        tree = HTMLParser(html)
        card = tree.css_first(self.CARD_SELECTOR)

        def text(sel: str) -> str | None:
            node = tree.css_first(sel)
            return node.text(strip=True) if node else None

        advert_id = card.attributes.get("data-advertid") if card else None
        # Detail URL is base64 in data-o; its 3rd path segment is the property type.
        url = None
        property_type = None
        data_o = card.attributes.get("data-o") if card else None
        if data_o:
            try:
                url = base64.b64decode(data_o).decode("utf-8")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                url = None
        if url:
            parts = url.split("/en/properties/")
            if len(parts) > 1:
                property_type = parts[1].split("/", 1)[0]

        location = text(self.SEL_LOCATION)  # "Chalandri (Attica)"
        neighborhood = location.split("(")[0].strip() if location else None

        m_img = _IMG_RE.search(unescape(html))
        image_url = m_img.group(0) if m_img else None

        return {
            "source": self.source,
            "source_id": advert_id,
            "url": url,
            "title": card.attributes.get("title") if card else None,
            "price": parse_int(text(self.SEL_PRICE)),  # "700,000 €" -> 700000
            "area_m2": parse_float((text(self.SEL_AREA) or "").replace(",", "")),  # "199 m²" -> 199
            "bedrooms": parse_int(text(self.SEL_BEDROOMS)),  # "4  bedrooms" -> 4
            "neighborhood": neighborhood,
            "address": neighborhood,
            "property_type": property_type,
            "image_url": image_url,
        }

    def _enrich_from_detail(self, session: requests.Session, raw: dict) -> None:
        """Fetch the detail page for the listing's precise coordinates (accurate metro
        distance). Fail-soft: no coords just means the neighbourhood centroid is used."""
        settings = get_settings()
        try:
            resp = session.get(raw["url"], timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("greenacres: detail fetch failed for %s: %s", raw.get("url"), exc)
            return
        m = _COORDS_RE.search(resp.text)
        if m:
            raw["lat"], raw["lng"] = float(m.group(1)), float(m.group(2))
        time.sleep(random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s))
