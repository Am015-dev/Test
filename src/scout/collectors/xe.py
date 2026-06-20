"""XE.gr collector.

Selectors below were hardened against XE's live search-results markup (June 2026):
each result card is a ``div.common-ad-body`` whose fields are exposed via
``data-testid`` attributes. Area is embedded in the title ("Μεζονέτα 257 τ.μ.")
and the neighborhood sits in the address before the " | " separator. Keep these as
class constants so a redesign is a one-file fix; refresh ``tests/fixtures/xe_card.html``
alongside any change.

Geo filtering: XE filters results server-side by ``geo_place_id`` (a Google Places
id). We resolve the strategy's ``municipality`` to that id via XE's autocomplete API
and pass it on the search URL, so results come back already scoped to the target
area instead of spanning all of Athens. XE only filters at municipality/locality
granularity — sub-neighborhood ids return nothing — so we resolve the municipality.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from urllib.parse import urlencode

import requests
from selectolax.parser import HTMLParser

from ..config import Strategy, get_settings
from .base import USER_AGENT, Collector
from .parse_helpers import (
    parse_float,
    parse_floor,
    parse_int,
    parse_private_seller,
    parse_rent,
)

logger = logging.getLogger(__name__)

# XE has two listing-URL forms; the stable unique id sits in a different segment:
#   /property/u/782567?...                              -> "782567"
#   /property/d/<category-slug>/<uuid>/<area-slug>?...   -> the <uuid>
# The `d` form must skip the category slug (e.g. "poliseis-katoikion") and take the
# UUID, otherwise every `d` listing collapses onto the same slug id and dedup wipes
# them down to one record. Try the `d` UUID first, then the `u` numeric id.
_ID_RE_D = re.compile(r"/property/d/[^/?#]+/([^/?#]+)")
_ID_RE_U = re.compile(r"/property/u/([^/?#]+)")

# Area embedded in the title, anchored to the Greek "τ.μ." (or "m²"/"m2") unit so a
# leading room/bedroom count is never mistaken for the area.
_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:τ\.?\s*μ\.?|m²|m2)", re.IGNORECASE)


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

    AUTOCOMPLETE_URL = "https://www.xe.gr/services/places/autocomplete"

    def _resolve_place_id(self, query: str) -> str | None:
        """Resolve a place name to XE's ``geo_place_id`` via its autocomplete API.

        Returns the top candidate's id, or ``None`` on any failure so the caller can
        fall back to an unfiltered search rather than crash. ``verify`` follows the
        ``SCRAPE_IGNORE_HTTPS_ERRORS`` setting (for TLS-intercepting proxies).
        """
        try:
            resp = requests.get(
                self.AUTOCOMPLETE_URL,
                params={"query": query, "country_code": "GR"},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
                verify=not get_settings().scrape_ignore_https_errors,
            )
            resp.raise_for_status()
            candidates = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("xe: place autocomplete failed for %r: %s", query, exc)
            return None
        if not candidates:
            logger.warning("xe: no place match for %r", query)
            return None
        place_id = candidates[0].get("place_id")
        logger.info("xe: resolved %r -> geo_place_id %s", query, place_id)
        return place_id

    def search_urls(self, strategy: Strategy) -> list[str]:
        s = strategy.search
        base_params = {
            "transaction_name": "buy",
            "item_type": "re_residence",
            "minimum_price": s.price_min,
            "maximum_price": s.price_max,
            "minimum_size": int(s.area_min_m2),
        }

        # Preferred path: a single search scoped server-side to the municipality.
        place_id = self._resolve_place_id(s.municipality) if s.municipality else None
        if place_id:
            params = {**base_params, "geo_place_id": place_id}
            return [f"{self.BASE}/property/results?{urlencode(params)}"]

        # Fallback (autocomplete unreachable): legacy free-text per-neighborhood
        # search. ``geo_place_name`` does NOT filter server-side, so results span all
        # of Athens and the metro-distance hard filter does the narrowing; kept only
        # so the collector degrades gracefully instead of returning nothing.
        logger.warning("xe: geo_place_id unavailable; falling back to geo_place_name search")
        urls = []
        for neighborhood in s.neighborhoods or [""]:
            params = {
                **base_params,
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
        if href:
            # Drop XE's tracking query string. It carries unencoded spaces
            # (e.g. "widget_name=search results sponsored placement") that produce a
            # malformed, unclickable URL, and points the link at the search results
            # rather than the canonical listing page. Keep only the path.
            href = href.split("?")[0]
            if href.startswith("/"):
                href = self.BASE + href

        m = _ID_RE_D.search(href or "") or _ID_RE_U.search(href or "")
        # Fallback to None (not the last path segment, which is a non-unique area
        # slug like "cholargos" that would collapse many listings onto one id).
        source_id = m.group(1) if m else None

        title = text(self.SEL_TITLE)
        # Area is embedded in the title, e.g. "Μεζονέτα 257 τ.μ." — anchor to the
        # τ.μ./m² unit so we don't grab a leading room count ("2 δωμ. 85 τ.μ." -> 85).
        area = None
        if title:
            m_area = _AREA_RE.search(title)
            area = parse_float(m_area.group(1)) if m_area else parse_float(title)
        # Neighborhood lives in the address before the " | " separator. The address
        # also carries a transaction suffix ("... | Πώληση κατοικίας") that is noise
        # for geocoding, so keep only the location part before the separator.
        raw_address = text(self.SEL_ADDRESS)
        neighborhood = raw_address.split("|")[0].strip() if raw_address else None
        address = neighborhood
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
