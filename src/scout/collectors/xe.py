"""XE.gr collector — browser-free.

XE serves its search results as **server-rendered HTML**, so we fetch them with a
plain cookie-persisting ``requests`` session (realistic browser headers) and parse
the cards with selectolax — no headless browser. Each card is a
``div.common-ad-body``; fields are read via **class-based** selectors (the classes
exist in both the server-rendered and JS-hydrated markup, unlike ``data-testid``
which only appears after hydration). Area is embedded in the title ("Μεζονέτα 257
τ.μ.") and the neighborhood sits in the address before the " | " separator. Keep the
selectors as class constants so a redesign is a one-file fix; refresh
``tests/fixtures/xe_card.html`` alongside any change.

XE rate-limits per IP: an over-frequent request returns a page with zero cards. The
fetcher treats that as a transient block and retries with backoff, and caches a good
page so re-runs within the TTL don't re-hit XE.

Geo filtering: XE filters results server-side by ``geo_place_id`` (a Google Places
id). We resolve the strategy's ``municipality`` to that id via XE's autocomplete API
and pass it on the search URL, so results come back already scoped to the target
area instead of spanning all of Athens. XE only filters at municipality/locality
granularity — sub-neighborhood ids return nothing — so we resolve the municipality.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import urlencode

import requests
from selectolax.parser import HTMLParser

from ..config import Strategy, get_settings
from .base import RAW_HTML_DIR, USER_AGENT, Collector
from .parse_helpers import (
    parse_float,
    parse_floor,
    parse_int,
    parse_private_seller,
    parse_rent,
)

logger = logging.getLogger(__name__)

# Realistic browser headers — XE serves the search results as server-rendered HTML
# to a normal-looking client, so a plain session with these headers gets the cards
# without a headless browser. A persistent Session keeps XE's cookies across hits.
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "el-GR,el;q=0.9,en;q=0.8",
    "Referer": "https://www.xe.gr/property/",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

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

# Detail pages embed a schema.org JSON-LD block; this is far more reliable than
# scraping hydrated HTML. Pull the RealEstateListing script out of the page.
_LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S
)


def _feature_value(name: str) -> tuple[str, str] | None:
    """Split a JSON-LD feature string 'Έτος κατασκευής: 1984' into (key, value)."""
    if ":" not in name:
        return None
    key, value = name.split(":", 1)
    return key.strip(), value.strip()


# The detail page embeds the listing's location as a small privacy bounding box under
# ``property_location.coordinates`` (HTML-escaped JSON). The box CENTRE is the listing's
# real position — precise enough for an accurate walking distance to the nearest metro.
_COORDS_RE = re.compile(r"property_location\.coordinates\"\s*:\s*(\{.*?\}\s*\})")
_LAT_RE = re.compile(r"\"lat\"\s*:\s*(-?\d+\.\d+)")
_LON_RE = re.compile(r"\"lon\"\s*:\s*(-?\d+\.\d+)")


def parse_detail_coordinates(html: str) -> tuple[float | None, float | None]:
    """Return the listing's (lat, lng) from the detail page's geo bounding box, or
    (None, None). Averages the box corners to the centre. Fails soft."""
    match = _COORDS_RE.search(unescape(html))
    if not match:
        return None, None
    lats = [float(x) for x in _LAT_RE.findall(match.group(1))]
    lons = [float(x) for x in _LON_RE.findall(match.group(1))]
    if not lats or not lons:
        return None, None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def parse_detail_jsonld(html: str) -> dict:
    """Extract the rich investment fields from a listing detail page's JSON-LD.

    Returns any of ``year_built, bedrooms, area_m2, energy_class, heating,
    description`` that are present. Fails soft (returns ``{}`` on missing/garbled
    data) so a bad detail page never breaks the run — the card fields still stand.
    """
    out: dict = {}
    for block in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        for node in data if isinstance(data, list) else [data]:
            if not isinstance(node, dict) or node.get("@type") != "RealEstateListing":
                continue
            entity = node.get("mainEntity") or {}
            year = entity.get("yearBuilt")
            if year is not None:
                out["year_built"] = parse_int(str(year))
            rooms = entity.get("numberOfRooms")
            if isinstance(rooms, dict):
                rooms = rooms.get("value")
            if rooms is not None:
                out["bedrooms"] = parse_int(str(rooms))
            size = entity.get("floorSize")
            if isinstance(size, dict) and size.get("value") is not None:
                area = parse_float(str(size["value"]))
                if area:
                    out["area_m2"] = area
            for feat in entity.get("amenityFeature") or []:
                kv = _feature_value(feat.get("name", "") if isinstance(feat, dict) else "")
                if not kv:
                    continue
                key, value = kv
                if "Ενεργειακή" in key and value:
                    out["energy_class"] = value
                elif key.startswith("Θέρμανση") and value:
                    out["heating"] = value
                elif "Έτος κατασκευής" in key and "year_built" not in out:
                    out["year_built"] = parse_int(value)
            desc = node.get("description")
            if desc:
                out["description"] = desc
    return out


class XeCollector(Collector):
    source = "xe"
    BASE = "https://www.xe.gr"
    CARD_SELECTOR = "div.common-ad-body"

    # Class-based selectors: these classes are present in BOTH the server-rendered
    # HTML (what `requests` receives) and the JS-hydrated DOM, so the parser works
    # without a browser. (The `data-testid` attributes only appear after hydration.)
    SEL_LINK = "a[href*='/property/']"
    SEL_TITLE = ".common-property-ad-title"
    SEL_PRICE = ".property-ad-price"
    SEL_PPSQM = ".property-ad-price-per-sqm"
    SEL_FLOOR = ".property-ad-level-container"
    SEL_ADDRESS = ".common-property-ad-address"
    SEL_DETAIL = ".property-ad-detail-container"

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

    def search_urls(self, strategy: Strategy, transaction: str = "buy") -> list[str]:
        s = strategy.search
        base_params: dict = {
            "transaction_name": transaction,
            "item_type": "re_residence",
            "minimum_size": int(s.area_min_m2),
        }
        # The sale price band (€120k–320k) is meaningless for rentals — omit it so the
        # rent-comps search isn't filtered to nonsensical "€120k/month" rentals.
        if transaction == "buy":
            base_params["minimum_price"] = s.price_min
            base_params["maximum_price"] = s.price_max

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

    def _new_session(self) -> requests.Session:
        """A cookie-persisting session warmed up against XE's homepage."""
        session = requests.Session()
        session.headers.update(BROWSER_HEADERS)
        session.verify = not get_settings().scrape_ignore_https_errors
        try:  # warm-up: pick up XE's cookies before hitting the results endpoint
            session.get(f"{self.BASE}/property/", timeout=20)
        except requests.RequestException as exc:
            logger.warning("xe: warm-up request failed: %s", exc)
        return session

    def _cache_path(self, url: str):
        digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]  # noqa: S324 (cache key only)
        return RAW_HTML_DIR / self.source / f"page-{digest}.html"

    def _read_cache(self, url: str, ttl_minutes: int) -> str | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        age = datetime.utcnow() - datetime.utcfromtimestamp(path.stat().st_mtime)
        if age > timedelta(minutes=ttl_minutes):
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _write_cache(self, url: str, html: str) -> None:
        if not self.save_raw:
            return
        path = self._cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(html, encoding="utf-8")
        except OSError as exc:
            logger.warning("xe: could not cache page: %s", exc)

    def _has_cards(self, html: str) -> bool:
        return bool(HTMLParser(html).css_first(self.CARD_SELECTOR))

    def _fetch_html(self, session: requests.Session, url: str) -> str | None:
        """Fetch a results page, retrying transient empty/blocked responses.

        XE rate-limits per IP: an over-frequent request returns a page with zero
        cards. We treat that as a transient block and retry with growing backoff;
        a successful page is cached so re-runs within the TTL don't re-hit XE.
        """
        settings = get_settings()
        cached = self._read_cache(url, settings.scrape_cache_ttl_minutes)
        if cached is not None and self._has_cards(cached):
            logger.info("xe: served %s from cache", url)
            return cached

        for attempt in range(1, settings.scrape_max_retries + 1):
            html = ""
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                html = resp.text
            except requests.RequestException as exc:
                logger.warning(
                    "xe: fetch failed (attempt %d/%d): %s",
                    attempt,
                    settings.scrape_max_retries,
                    exc,
                )
            if html and self._has_cards(html):
                self._write_cache(url, html)
                return html
            logger.warning(
                "xe: empty/blocked page (attempt %d/%d) — backing off",
                attempt,
                settings.scrape_max_retries,
            )
            if attempt < settings.scrape_max_retries:
                time.sleep(settings.scrape_retry_backoff_s * attempt + random.uniform(0, 3))
        logger.warning("xe: gave up on %s after %d attempts", url, settings.scrape_max_retries)
        return None

    @staticmethod
    def _has_jsonld(html: str) -> bool:
        return "RealEstateListing" in html

    def _fetch_detail(self, session: requests.Session, url: str) -> str | None:
        """Fetch a listing detail page (cached; one retry). Returns HTML or None."""
        settings = get_settings()
        cached = self._read_cache(url, settings.scrape_cache_ttl_minutes)
        if cached is not None and self._has_jsonld(cached):
            return cached
        for attempt in range(1, 3):
            html = ""
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                html = resp.text
            except requests.RequestException as exc:
                logger.warning("xe: detail fetch failed (%d/2) for %s: %s", attempt, url, exc)
            if html and self._has_jsonld(html):
                self._write_cache(url, html)
                return html
            if attempt < 2:
                time.sleep(settings.scrape_retry_backoff_s)
        return None

    def _enrich_from_detail(self, session: requests.Session, raw: dict) -> None:
        """Merge a listing's detail-page JSON-LD (year, energy, bedrooms, description
        → rent/rented/private) into ``raw``. Fail-soft: a bad fetch leaves card fields."""
        html = self._fetch_detail(session, raw["url"])
        if not html:
            return
        lat, lng = parse_detail_coordinates(html)
        if lat is not None and lng is not None:
            raw["lat"], raw["lng"] = lat, lng
        try:
            detail = parse_detail_jsonld(html)
        except Exception as exc:
            logger.warning("xe: detail parse error for %s: %s", raw.get("url"), exc)
            return
        for key in ("year_built", "bedrooms", "energy_class", "heating"):
            if detail.get(key) is not None:
                raw[key] = detail[key]
        if detail.get("area_m2") and not raw.get("area_m2"):
            raw["area_m2"] = detail["area_m2"]
        desc = detail.get("description")
        if desc:
            rented, listed_rent = parse_rent(desc)
            if rented:
                raw["is_currently_rented"] = True
            if listed_rent:
                raw["listed_rent"] = listed_rent
            if parse_private_seller(desc):
                raw["is_private_seller"] = True

    def collect_rent_rows(self) -> Iterator[dict]:
        """Scrape RENTAL cards (no detail fetch) for rent comps: yields
        ``{rent, area_m2, neighborhood}``. Card price is the monthly rent here."""
        settings = get_settings()
        session = self._new_session()
        for url in self.search_urls(self.strategy, transaction="rent"):
            html = self._fetch_html(session, url)
            if not html:
                continue
            cards = HTMLParser(html).css(self.CARD_SELECTOR)
            logger.info("xe: %d rental cards on %s", len(cards), url)
            for card in cards:
                try:
                    raw = self.parse_card(card.html, base_url=url)
                except Exception:
                    continue
                if raw and raw.get("price") and raw.get("area_m2"):
                    yield {
                        "rent": raw["price"],
                        "area_m2": raw["area_m2"],
                        "neighborhood": raw.get("neighborhood"),
                    }
            time.sleep(random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s))

    def collect(self) -> Iterator[dict]:
        settings = get_settings()
        session = self._new_session()
        cap = settings.scrape_detail_max_per_area
        for url in self.search_urls(self.strategy):
            html = self._fetch_html(session, url)
            if not html:
                continue
            cards = HTMLParser(html).css(self.CARD_SELECTOR)
            logger.info("xe: %d cards on %s", len(cards), url)
            enriched = 0
            for card in cards:
                try:
                    raw = self.parse_card(card.html, base_url=url)
                except Exception as exc:  # fail soft per card
                    logger.warning("xe: card parse error: %s", exc)
                    continue
                if not raw:
                    continue
                if settings.scrape_detail_pages and raw.get("url") and (cap == 0 or enriched < cap):
                    self._enrich_from_detail(session, raw)
                    enriched += 1
                    time.sleep(
                        random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s)
                    )
                yield raw
            time.sleep(random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s))

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

        # Bedrooms/year sit in icon+value detail boxes (no stable per-field class),
        # so find the box by its icon class and read its value span.
        def detail_by_icon(icon_class: str) -> str | None:
            for box in tree.css(self.SEL_DETAIL):
                if box.css_first(f"i.{icon_class}"):
                    span = box.css_first("span")
                    return span.text(strip=True) if span else None
            return None

        bedrooms = parse_int(detail_by_icon("xe-bedroom"))  # "×4" -> 4
        year = parse_int(detail_by_icon("xe-house-construction"))

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
