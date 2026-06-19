"""XE.gr collector.

Selectors below were hardened against XE's live search-results markup (June 2026):
each result card is a ``div.common-ad-body`` whose fields are exposed via
``data-testid`` attributes. Area is embedded in the title ("Μεζονέτα 257 τ.μ.")
and the neighborhood sits in the address before the " | " separator. Keep these as
class constants so a redesign is a one-file fix; refresh ``tests/fixtures/xe_card.html``
alongside any change.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urlencode

from selectolax.parser import HTMLParser

from ..config import Strategy
from .base import Collector
from .parse_helpers import (
    parse_float,
    parse_floor,
    parse_int,
    parse_private_seller,
    parse_rent,
)

# Both XE URL forms: /property/u/782567?... and /property/d/athina-...-104?...
# Capture the path segment after /property/<letter>/, stopping before any query.
_ID_RE = re.compile(r"/property/[a-z]/([^/?#]+)")


class XeCollector(Collector):
    source = "xe"
    BASE = "https://www.xe.gr"
    CARD_SELECTOR = "div.common-ad-body"

    SEL_LINK = "a[data-testid='property-ad-url']"
    SEL_TITLE = "[data-testid='property-ad-title']"
    SEL_PRICE = "[data-testid='property-ad-price']"
    SEL_PPSQM = "[data-testid='property-ad-price-per-sqm']"
    SEL_FLOOR = "[data-testid='property-ad-level-container']"
    SEL_ADDRESS = "[data-testid='property-ad-address']"
    SEL_BEDROOMS = "[data-testid='property-ad-xe xe-bedroom']"
    SEL_YEAR = "[data-testid='property-ad-xe xe-house-construction']"

    def search_urls(self, strategy: Strategy) -> list[str]:
        # NOTE: ``geo_place_name`` is a free-text param and does NOT filter
        # server-side — XE resolves areas via a numeric ``geo_place_id`` from its
        # autocomplete API. Until that lookup is added, results span all of Athens
        # and the metro-distance hard filter does the geographic narrowing instead.
        s = strategy.search
        urls = []
        for neighborhood in s.neighborhoods or [""]:
            params = {
                "transaction_name": "buy",
                "item_type": "re_residence",
                "minimum_price": s.price_min,
                "maximum_price": s.price_max,
                "minimum_size": int(s.area_min_m2),
                "geo_place_name": neighborhood,
            }
            urls.append(f"{self.BASE}/property/results?{urlencode(params)}")
        return urls

    def collect(self) -> Iterator[dict]:
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

        m = _ID_RE.search(href or "")
        if m:
            source_id = m.group(1)
        elif href:
            # Fallback: last path segment, without any query string.
            source_id = href.split("?")[0].rstrip("/").split("/")[-1] or None
        else:
            source_id = None

        title = text(self.SEL_TITLE)
        # Area is embedded in the title, e.g. "Μεζονέτα 257 τ.μ.".
        area = parse_float(title)
        # Neighborhood lives in the address before the " | " separator.
        address = text(self.SEL_ADDRESS)
        neighborhood = address.split("|")[0].strip() if address else None
        bedrooms = parse_int(text(self.SEL_BEDROOMS))  # "×4" -> 4
        year = parse_int(text(self.SEL_YEAR))

        # Search cards carry no description; rent/private-seller surface on detail pages.
        rented, listed_rent = parse_rent(title)
        private = parse_private_seller(title)

        return {
            "source": self.source,
            "source_id": source_id,
            "url": href,
            "title": title,
            "price": parse_int(text(self.SEL_PRICE)),
            "area_m2": area,
            "floor": parse_floor(text(self.SEL_FLOOR)),
            "bedrooms": bedrooms,
            "year_built": year,
            "neighborhood": neighborhood,
            "address": address,
            "is_currently_rented": rented,
            "listed_rent": listed_rent,
            "is_private_seller": private,
        }
