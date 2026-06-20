"""Spitogatos collector.

Selectors are class constants so a portal redesign is a one-file fix. ``parse_card``
works on a single result-card's HTML and is exercised offline by fixtures, so it
must not assume any field is present.

NOTE: portal markup changes frequently and is bot-guarded. The selectors below are
a reasonable starting point; when the live structure differs, update the constants
here and refresh the fixtures — the rest of the pipeline is unaffected.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlencode

from selectolax.parser import HTMLParser

from ..config import Strategy, get_settings
from .base import Collector
from .parse_helpers import (
    parse_float,
    parse_floor,
    parse_int,
    parse_private_seller,
    parse_rent,
)


class SpitogatosCollector(Collector):
    source = "spitogatos"
    BASE = "https://www.spitogatos.gr"
    CARD_SELECTOR = "[data-testid='property-card']"

    # Within-card selectors (class constants).
    SEL_LINK = "a[href]"
    SEL_TITLE = "[data-testid='title'], h3"
    SEL_PRICE = "[data-testid='price']"
    SEL_AREA = "[data-testid='area']"
    SEL_FLOOR = "[data-testid='floor']"
    SEL_NEIGHBORHOOD = "[data-testid='location']"
    SEL_DESC = "[data-testid='description'], p"
    ATTR_ID = "data-id"

    def search_urls(self, strategy: Strategy) -> list[str]:
        """One pre-filtered search URL per neighborhood (server-side filtering).

        Floor is NOT filtered here — portals filter it unreliably, so floor
        filtering happens in scoring.
        """
        s = strategy.search
        urls = []
        for neighborhood in s.neighborhoods or [""]:
            params = {
                "transaction": "buy",
                "category": "residential",
                "priceFrom": s.price_min,
                "priceTo": s.price_max,
                "areaFrom": int(s.area_min_m2),
                "geo": neighborhood,
            }
            urls.append(f"{self.BASE}/en/search?{urlencode(params)}")
        return urls

    def collect(self) -> Iterator[dict]:
        endpoint = get_settings().flaresolverr_url
        if endpoint:
            yield from self._collect_via_flaresolverr(endpoint)
        else:
            yield from self._collect_with_playwright()

    def parse_card(self, html: str, base_url: str) -> dict:
        tree = HTMLParser(html)

        def text(sel: str) -> str | None:
            node = tree.css_first(sel)
            return node.text(strip=True) if node else None

        link_node = tree.css_first(self.SEL_LINK)
        href = link_node.attributes.get("href") if link_node else None
        if href and href.startswith("/"):
            href = self.BASE + href

        card = tree.css_first(self.CARD_SELECTOR)
        source_id = (card.attributes.get(self.ATTR_ID) if card else None) or _id_from_url(href)

        desc = text(self.SEL_DESC)
        rented, listed_rent = parse_rent(desc)
        private = parse_private_seller(" ".join(filter(None, [text(self.SEL_TITLE), desc])))

        return {
            "source": self.source,
            "source_id": source_id,
            "url": href,
            "title": text(self.SEL_TITLE),
            "price": parse_int(text(self.SEL_PRICE)),
            "area_m2": parse_float(text(self.SEL_AREA)),
            "floor": parse_floor(text(self.SEL_FLOOR)),
            "neighborhood": text(self.SEL_NEIGHBORHOOD),
            "is_currently_rented": rented,
            "listed_rent": listed_rent,
            "is_private_seller": private,
            "description": desc,
        }


def _id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").split("/")[-1] or None
