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
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import urlencode

import requests
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from ..config import Strategy, get_settings
from .base import RAW_HTML_DIR, USER_AGENT, Collector
from .parse_helpers import (
    _strip_accents,
    card_image_url,
    clean_description,
    parse_float,
    parse_floor,
    parse_int,
    parse_private_seller,
    parse_rent,
    portal_photo_url,
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


# Renovation year stated in prose — "ανακαινισμένο/ανακαίνιση (το) 2019" and Latin variants.
_RENO_YEAR_RE = re.compile(r"(?:ανακαιν\w*|renovat\w*)[^0-9]{0,20}(19\d{2}|20\d{2})", re.IGNORECASE)

# --- Extra prose fields pulled from the JSON-LD description -----------------------
# These live in the free-text "description" (and sometimes the amenity list); XE has no
# structured field for most of them. All are best-effort — absent → the key is omitted.

# Heating stated inline as "<type> Θέρμανση" ("Ατομική - Φυσικό Αέριο Θέρμανση"). Used
# only as a fallback when the amenityFeature list carries no "Θέρμανση: …" entry. Bounded
# to a single clause ([^,.:]) so it can't swallow the rest of the sentence.
_HEATING_PROSE_RE = re.compile(r"([^,.:]+?)\s+Θέρμανση")

# Parking: an optional leading count then any of the accepted spellings. Matched against
# an accent-stripped, lower-cased copy of the text, so literals here are unaccented.
_PARKING_RE = re.compile(r"(?:(\d+)\s*)?(?:parking|θεσ\w*\s+σταθμευσης|γκαραζ)")
# Storage room ("αποθηκη"). Accent-stripped literal.
_STORAGE_RE = re.compile(r"αποθηκη")
# Off-plan delivery year: "…ΘΑ ΠΑΡΑΔΩΘΕΙ ΤΟ 2026…" (distinct from Έτος κατασκευής).
_DELIVERY_YEAR_RE = re.compile(r"παραδ[ωο]θ\w*\s+το\s+(20\d{2})")

# Property condition. Order matters: "χρηζει ανακαινισης" also contains "ανακαιν", so the
# needs-renovation test must precede the renovated test. Each pattern runs against
# accent-stripped, lower-cased text.
_CONDITION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("under_construction", re.compile(r"υπο κατασκευη")),
    ("newbuild", re.compile(r"νεοδμητ|νεοκτιστ")),
    ("needs_renovation", re.compile(r"χρηζει ανακαιν|χρηζουν ανακαιν")),
    ("renovated", re.compile(r"ανακαινισμ")),
)


def _condition_from_text(text: str | None) -> str | None:
    """Classify a listing's condition from free text, or None if nothing matches."""
    if not text:
        return None
    norm = _strip_accents(text).lower()
    for label, pattern in _CONDITION_PATTERNS:
        if pattern.search(norm):
            return label
    return None


# Unfinished / under-construction building. Run on accent-stripped, lower-cased text, so
# literals are unaccented. "νεοδμητο"/"ανακαινισμενο" deliberately don't match.
_UNFINISHED_RE = re.compile(
    r"ημι[\s-]?τελ"  # ημιτελής / ημι-τελές
    r"|υπο\s+κατασκευ"  # υπό κατασκευή
    r"|αποπερατω"  # (προς) αποπεράτωση
    r"|φαση\s+κατασκευ"  # σε φάση κατασκευής
    r"|\bσκελετ"  # σκελετός / σε σκελετό
    r"|under\s+construction|unfinished"
)
# A negation shortly before the match ("δεν είναι ημιτελές") cancels it.
_NEGATION_RE = re.compile(r"\b(?:δεν|μη|μην|ουτε|not|no)\b")


# Delivery still ahead, as agents phrase it: "παράδοση τέλη 27", "ολοκλήρωση τέλη του 2027",
# "παράδοση έργου 2028", "αποπεράτωση σε 1,5 χρόνο", "η κατασκευή ξεκίνησε το 2025",
# "κατασκευάζεται". Accent-stripped, lower-cased text.
_DELIVERY_RE = re.compile(
    r"(?:παραδοση|ολοκληρωση|αποπερατωση|διαθεσιμο\s+απο)[^.]{0,60}?(?:20)?(\d{2})\b"
)
_BUILDING_NOW_RE = re.compile(r"κατασκευη\s+(?:του\s+)?ξεκινησε|κατασκευαζεται|αποπερατωση\s+σε")
# Listing pages checked before this date were opened without the under-construction check
# (unfinished_on_detail): they don't count as checked, and are checked again.
UNFINISHED_CHECK_SINCE = datetime(2026, 10, 31)


def checked_for_unfinished(detail_checked_at: datetime | None) -> bool:
    """Was the listing page read with the under-construction check?"""
    return bool(detail_checked_at and detail_checked_at >= UNFINISHED_CHECK_SINCE)


# Agents selling off-plan say the photos are illustrations / 3D renders, or stock photos
# "for presentation purposes" (seen stamped on the images themselves and in the text).
_RENDER_RE = re.compile(
    r"ενδεικτικ\w*\s+(?:φωτογραφ|απεικον|εικον)|φωτορεαλιστικ|3d\s+(?:απεικον|σχεδ)|\brenders?\b"
    r"|παρομοι\w*\s+φωτογραφ|για\s+λογους\s+παρουσιασης"
)
_AVAILABLE_RE = re.compile(r"Διαθέσιμο από:\s*(\d{1,2})/(\d{1,2})/(\d{4})")


# Rental-card facts. Accent-stripped, lower-cased text. A non-negated "επιπλωμένο" /
# "με έπιπλα" says furnished — it wins over "ανεπίπλωτο", which ads also use to compare
# ("τιμές αντίστοιχες με τα ανεπίπλωτα", seen on a real XE card). Otherwise "μη
# επιπλωμένο" / "χωρίς έπιπλα" / "ανεπίπλωτο" say unfurnished; silence = None.
_UNFURNISHED_RE = re.compile(r"\b(?:μη|οχι)\s+επιπλωμεν|χωρις\s+επιπλ|ανεπιπλωτ|unfurnished")
_FURNISHED_RE = re.compile(r"(?<![α-ω])επιπλωμεν|\bμε\s+επιπλ|(?<!un)furnished")
_FURNISHED_NEG_RE = re.compile(r"\b(?:μη|οχι)\s+$")
_AVAILABLE_FROM_RE = re.compile(r"διαθεσιμο\s+απο:?\s*(\d{1,2})/(\d{1,2})/(\d{2,4})")


def parse_furnished(text: str | None) -> bool | None:
    """True / False when a rental's text says (un)furnished, None when it is silent."""
    norm = _strip_accents(text or "").lower()
    for m in _FURNISHED_RE.finditer(norm):
        if not _FURNISHED_NEG_RE.search(norm[max(0, m.start() - 6) : m.start()]):
            return True
    if _UNFURNISHED_RE.search(norm):
        return False
    return None


def parse_available_from(text: str | None) -> date | None:
    """The «Διαθέσιμο από: 1/12/2026» date on a rental, or None."""
    m = _AVAILABLE_FROM_RE.search(_strip_accents(text or "").lower())
    if not m:
        return None
    year = int(m.group(3))
    year = year + 2000 if year < 100 else year
    try:
        return date(year, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def unfinished_on_detail(html: str, detail: dict, today: date | None = None) -> bool:
    """True when a listing's own page says it is not finished yet: XE's "Υπό κατασκευή"
    characteristic or under-construction condition, an availability date ahead, or a
    description promising delivery in a future year. The results-page card says none of
    this, so a "νεόδμητο 2025" card is often still a shell sold off-plan."""
    today = today or date.today()
    node = HTMLParser(html).css_first("[data-testid='characteristics']")
    facts = node.text(separator=" ") if node else ""
    if detail.get("condition") == "under_construction" or "Υπό κατασκευή" in facts:
        return True
    m = _AVAILABLE_RE.search(facts)
    if m and date(int(m.group(3)), int(m.group(2)), int(m.group(1))) > today:
        return True
    desc = _strip_accents(detail.get("description") or "").lower()
    if is_unfinished_text(desc) or _BUILDING_NOW_RE.search(desc) or _RENDER_RE.search(desc):
        return True
    for m in _DELIVERY_RE.finditer(desc):
        year = 2000 + int(m.group(1))
        if year > today.year or (year == today.year and today.month <= 6):
            return True
    return False


def is_unfinished_text(*texts: str | None) -> bool:
    """True when any text describes an unfinished building / one under construction."""
    for text in texts:
        if not text:
            continue
        norm = _strip_accents(text).lower()
        for m in _UNFINISHED_RE.finditer(norm):
            if not _NEGATION_RE.search(norm[max(0, m.start() - 25) : m.start()]):
                return True
    return False


def _feature_value(name: str) -> tuple[str, str] | None:
    """Split a JSON-LD feature string 'Έτος κατασκευής: 1984' into (key, value)."""
    if ":" not in name:
        return None
    key, value = name.split(":", 1)
    return key.strip(), value.strip()


# The detail page embeds the listing's location as a small privacy bounding box under
# ``property_location.coordinates`` (HTML-escaped JSON). The box CENTRE is the listing's
# real position — precise enough for an accurate walking distance to the nearest metro.
_OG_IMAGE_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']')
_COORDS_RE = re.compile(r"property_location\.coordinates\"\s*:\s*(\{.*?\}\s*\})")
_LAT_RE = re.compile(r"\"lat\"\s*:\s*(-?\d+\.\d+)")
_LON_RE = re.compile(r"\"lon\"\s*:\s*(-?\d+\.\d+)")

# The listing's own posting date — present on ~100% of XE detail pages as the schema.org
# ``datePosted`` field (ISO-8601, usually with a trailing Z). This is the REAL market age,
# so days-on-market / negotiation work from the first sight instead of only after the daily
# tracker has watched the listing for weeks. This is the answer to "why scrape daily".
_DATE_POSTED_RE = re.compile(r'"datePosted"\s*:\s*"([^"]+)"')


def parse_listed_date(html: str) -> datetime | None:
    """Return the listing's posting date from the detail page's ``datePosted``, or None.

    Accepts the common ISO-8601 forms XE emits (``2026-07-09T13:49:08Z`` and the
    offset-less ``2026-07-09T13:49:08``). Fails soft: an absent or unparseable value
    yields None so the listing simply falls back to first-seen for its market age.
    """
    m = _DATE_POSTED_RE.search(html)
    if not m:
        return None
    raw = m.group(1).strip()
    try:
        # Normalize a trailing Z to a form fromisoformat accepts, then drop tz so the
        # value is comparable with the pipeline's naive UTC ``now``.
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


# The listing's own photos are the JSON-LD ``image`` list (``.../<uuid>-source.jpg?...``,
# one file per photo, often repeated per format). XE's escaped ``"image_count"`` values are
# NOT used: on real pages the first ones belong to the embedded "similar listings" (checked
# on 12 live pages, Oct 2026 — e.g. 25 declared vs 2 own photos), so they only overstate.
_SOURCE_IMG_RE = re.compile(r"/([0-9a-f-]{36})-source\.(?:jpe?g|webp|png)", re.IGNORECASE)


def parse_photo_urls(html: str) -> list[str]:
    """The listing's own photo URLs, one per distinct file, in page order (first format
    seen wins) — the same JSON-LD ``RealEstateListing.image`` list ``parse_photo_count``
    counts. Empty when the page lists none."""
    urls: dict[str, str] = {}
    for block in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        for node in data if isinstance(data, list) else [data]:
            if not isinstance(node, dict) or node.get("@type") != "RealEstateListing":
                continue
            images = node.get("image") or []
            for url in [images] if isinstance(images, str) else images:
                found = _SOURCE_IMG_RE.search(url) if isinstance(url, str) else None
                if found:
                    urls.setdefault(found.group(1).lower(), url)
    return list(urls.values())


def parse_photo_count(html: str) -> int | None:
    """Distinct photo files in the listing's own JSON-LD ``RealEstateListing.image`` list.

    0 when the listing lists no photos; None when the page has no listing data at all."""
    listed: set[str] = set()
    has_listing = False
    for block in _LD_JSON_RE.findall(html):
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        for node in data if isinstance(data, list) else [data]:
            if not isinstance(node, dict) or node.get("@type") != "RealEstateListing":
                continue
            has_listing = True
            images = node.get("image") or []
            for url in [images] if isinstance(images, str) else images:
                found = _SOURCE_IMG_RE.search(url) if isinstance(url, str) else None
                if found:
                    listed.add(found.group(1).lower())
    return len(listed) if has_listing else None


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
    renovated_year, description`` that are present, plus best-effort extras parsed
    from the description prose: ``parking`` (int count or ``True``), ``storage``
    (bool), ``condition`` (newbuild/under_construction/renovated/needs_renovation),
    ``delivery_year`` (off-plan handover year), and a prose fallback for ``heating``.
    Fails soft (returns ``{}`` on missing/garbled data) so a bad detail page never
    breaks the run — the card fields still stand.
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
                elif "Κατάσταση" in key and "condition" not in out:
                    cond = _condition_from_text(value)
                    if cond:
                        out["condition"] = cond
            desc = node.get("description")
            if desc:
                out["description"] = desc
                # Renovation year is never a structured field, but listings routinely state
                # it in prose ("ανακαινισμένο το 2019"). Capturing it makes the "Renovated"
                # archetype and the newness signal reflect reality instead of build-year only.
                reno = _RENO_YEAR_RE.search(desc)
                if reno:
                    year = parse_int(reno.group(1))
                    if year and 1950 <= year <= datetime.utcnow().year:
                        out["renovated_year"] = year
                _extract_prose_fields(desc, out)
    return out


def _extract_prose_fields(desc: str, out: dict) -> None:
    """Fill parking/storage/condition/delivery_year (and a heating fallback) from the
    free-text description ``desc`` into ``out``. Each is optional and only set when
    found, so absent facts simply leave the key out. Never raises."""
    # Heating: the structured amenity list is authoritative; only mine the prose when it
    # didn't provide one, so we never overwrite a clean "Θέρμανση: …" value.
    if "heating" not in out:
        m_heat = _HEATING_PROSE_RE.search(desc)
        if m_heat:
            heat = m_heat.group(1).strip()
            if heat:
                out["heating"] = heat

    # Booleans/condition are accent-insensitive, so match on a normalized copy.
    norm = _strip_accents(desc).lower()

    m_park = _PARKING_RE.search(norm)
    if m_park:
        count = parse_int(m_park.group(1)) if m_park.group(1) else None
        out["parking"] = count if count else True

    if _STORAGE_RE.search(norm):
        out["storage"] = True

    if "condition" not in out:
        cond = _condition_from_text(desc)
        if cond:
            out["condition"] = cond

    m_del = _DELIVERY_YEAR_RE.search(norm)
    if m_del:
        year = parse_int(m_del.group(1))
        # Regex already fixes the century (20xx); just cap an absurd far-future value.
        if year and year <= datetime.utcnow().year + 15:
            out["delivery_year"] = year


class XeCollector(Collector):
    source = "xe"
    BASE = "https://www.xe.gr"
    CARD_SELECTOR = "div.common-ad-body"

    # Each field has a `data-testid` selector (the markup XE serves now, present in the raw
    # HTML) and the older class selector as a fallback, so either layout parses.
    SEL_LINK = "a[href*='/property/']"
    SEL_TITLE = "[data-testid='property_ad_title'], .common-property-ad-title"
    SEL_PRICE = "[data-testid='property_ad_price'], .property-ad-price"
    SEL_PPSQM = ".property-ad-price-per-sqm"
    # The level container first: XE gives ground/basement flats a different icon test-id.
    SEL_FLOOR = (
        "[data-testid='property_ad_level_container'], "
        "[data-testid='property_ad_icon_levels_new'], .property-ad-level-container"
    )
    SEL_ADDRESS = "[data-testid='property_ad_address'], .common-property-ad-address"
    SEL_DETAIL = ".property-ad-detail-container"
    SEL_BEDROOMS = "[data-testid='property_ad_icon_bedroom']"
    SEL_YEAR = "[data-testid='property_ad_icon_house_construction']"
    SEL_DESCRIPTION = "#property-ad-description"
    # The listing's first photo. It sits in the ad's image container, a sibling of the card
    # body, so the loops hand ``parse_card`` the whole ad (``_card_html``). Not the agency
    # logo, which is ``[data-testid='property-ad-realtor-logo']`` inside the body.
    SEL_IMAGE = "[data-testid='property-ad-image'] img, .common-property-ad-image img"

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

    # Adaptive throttle: extra seconds added to every inter-request pause. It GROWS each
    # time XE pushes back (a blocked/empty page) and DECAYS on clean fetches, so the crawler
    # self-tunes to XE's per-IP limit — fast while it's tolerated, backing off the moment it
    # isn't — instead of relying on one hand-picked constant. Reset at the start of each run.
    _BLOCK_PENALTY_S = 2.5
    _DECAY_S = 0.5
    _MAX_EXTRA_S = 15.0

    def _register_block(self) -> None:
        self._extra_delay = min(
            getattr(self, "_extra_delay", 0.0) + self._BLOCK_PENALTY_S, self._MAX_EXTRA_S
        )

    def _register_ok(self) -> None:
        self._extra_delay = max(0.0, getattr(self, "_extra_delay", 0.0) - self._DECAY_S)

    def _paced_sleep(self, settings) -> None:
        base = random.uniform(settings.scrape_request_min_s, settings.scrape_request_max_s)
        time.sleep(base + getattr(self, "_extra_delay", 0.0))

    def _new_session(self) -> requests.Session:
        """A cookie-persisting session warmed up against XE's homepage."""
        self._extra_delay = 0.0  # reset the adaptive throttle for a fresh run
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

    @staticmethod
    def _card_html(card) -> str:
        """The whole ad (photo container + body) around a ``CARD_SELECTOR`` body node."""
        ad = card.parent
        if ad is not None and "common-ad" in (ad.attributes.get("class") or "").split():
            return ad.html
        return card.html

    def _has_cards(self, html: str) -> bool:
        return bool(HTMLParser(html).css_first(self.CARD_SELECTOR))

    def _fetch_html(
        self, session: requests.Session, url: str, max_attempts: int | None = None
    ) -> str | None:
        """Fetch a results page, retrying transient empty/blocked responses.

        XE rate-limits per IP: an over-frequent request returns a page with zero
        cards. We treat that as a transient block and retry with growing backoff;
        a successful page is cached so re-runs within the TTL don't re-hit XE.

        ``max_attempts`` overrides the retry budget — pagination passes a small value so
        a genuinely empty page *past the last result* (0 cards, not a block) ends the
        walk quickly instead of burning the full backoff sequence on every area's tail.
        """
        settings = get_settings()
        attempts = max_attempts or settings.scrape_max_retries
        cached = self._read_cache(url, settings.scrape_cache_ttl_minutes)
        if cached is not None and self._has_cards(cached):
            logger.info("xe: served %s from cache", url)
            return cached

        for attempt in range(1, attempts + 1):
            html = ""
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                html = resp.text
            except requests.RequestException as exc:
                logger.warning("xe: fetch failed (attempt %d/%d): %s", attempt, attempts, exc)
            if html and self._has_cards(html):
                self._write_cache(url, html)
                self._register_ok()  # clean fetch → let the adaptive throttle ease off
                return html
            self._register_block()  # XE pushed back → widen the pause for the rest of the run
            logger.warning(
                "xe: empty/blocked page (attempt %d/%d) — backing off", attempt, attempts
            )
            if attempt < attempts:
                time.sleep(settings.scrape_retry_backoff_s * attempt + random.uniform(0, 3))
        logger.warning("xe: gave up on %s after %d attempts", url, attempts)
        return None

    @staticmethod
    def _has_jsonld(html: str) -> bool:
        return "RealEstateListing" in html

    def _fetch_detail(self, session: requests.Session, url: str) -> str | None:
        """Fetch a listing detail page (cached; one retry).

        Returns the HTML; ``""`` when the ad is definitively GONE (XE redirects removed
        listings); ``None`` on transient failure (block page / network) — the caller can
        retry those later, but must not treat a gone ad as retryable."""
        settings = get_settings()
        cached = self._read_cache(url, settings.scrape_cache_ttl_minutes)
        if cached is not None and self._has_jsonld(cached):
            return cached
        for attempt in range(1, 3):
            html = ""
            try:
                # allow_redirects=False: a redirected detail URL means the listing is GONE
                # (XE 30x-es dead ads to a search page). Following it is never useful and
                # the redirect target can trickle bytes slower than the read-timeout window,
                # hanging the whole enrichment pipeline on one dead ad (observed via py-spy:
                # blocked in ssl read inside resolve_redirects for 30+ minutes).
                resp = session.get(url, timeout=30, allow_redirects=False)
                if 300 <= resp.status_code < 400:
                    logger.info("xe: detail page gone (redirect %d) for %s", resp.status_code, url)
                    return ""
                resp.raise_for_status()
                html = resp.text
            except requests.RequestException as exc:
                logger.warning("xe: detail fetch failed (%d/2) for %s: %s", attempt, url, exc)
            if html and self._has_jsonld(html):
                self._write_cache(url, html)
                self._register_ok()  # clean detail fetch → ease the adaptive throttle
                return html
            self._register_block()  # a 403 here too → widen subsequent pauses
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
        if not raw.get("image_url"):
            m_img = _OG_IMAGE_RE.search(html)
            if m_img:
                raw["image_url"] = portal_photo_url(unescape(m_img.group(1)), self.BASE, "xe.gr")
        if not raw.get("listed_date"):
            listed = parse_listed_date(html)
            if listed is not None:
                raw["listed_date"] = listed
        try:
            detail = parse_detail_jsonld(html)
        except Exception as exc:
            logger.warning("xe: detail parse error for %s: %s", raw.get("url"), exc)
            return
        for key in ("year_built", "renovated_year", "bedrooms", "energy_class", "heating"):
            if detail.get(key) is not None:
                raw[key] = detail[key]
        if detail.get("area_m2") and not raw.get("area_m2"):
            raw["area_m2"] = detail["area_m2"]
        if unfinished_on_detail(html, detail):
            raw["is_unfinished"] = True
        photos = parse_photo_count(html)
        if photos is not None:
            raw["photo_count"] = photos
        desc = detail.get("description")
        if desc:
            raw["description"] = clean_description(desc)
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
                    raw = self.parse_card(self._card_html(card), base_url=url)
                except Exception:
                    continue
                if raw and raw.get("price") and raw.get("area_m2"):
                    yield {
                        "rent": raw["price"],
                        "area_m2": raw["area_m2"],
                        "neighborhood": raw.get("neighborhood"),
                    }
            self._paced_sleep(settings)

    # Rental search pages walked per area (~36 cards a page). Bounded so the rental pass
    # stays about a minute per area at the polite pacing; no detail-page fetch.
    RENT_MAX_PAGES = 5

    def collect_rentals(self) -> Iterator[dict]:
        """Full rental cards for the area: the same ``parse_card`` fields as sale cards
        (price = monthly rent), plus ``listing_type="rent"`` and ``furnished`` /
        ``available_from`` when the card says so. Pages are walked until one adds nothing
        new or ``RENT_MAX_PAGES``."""
        settings = get_settings()
        session = self._new_session()
        for base_url in self.search_urls(self.strategy, transaction="rent"):
            seen_ids: set[str] = set()
            for page in range(1, self.RENT_MAX_PAGES + 1):
                url = base_url if page == 1 else f"{base_url}&page={page}"
                html = self._fetch_html(session, url, max_attempts=None if page == 1 else 2)
                if not html:
                    break
                new_on_page = 0
                for card in HTMLParser(html).css(self.CARD_SELECTOR):
                    try:
                        raw = self.parse_rental_card(self._card_html(card), base_url=url)
                    except Exception as exc:  # fail soft per card
                        logger.warning("xe: rental card parse error: %s", exc)
                        continue
                    sid = raw.get("source_id")
                    if not sid or sid in seen_ids:
                        continue
                    seen_ids.add(sid)
                    new_on_page += 1
                    yield raw
                logger.info("xe: rent page %d -> %d new rentals (%s)", page, new_on_page, base_url)
                if new_on_page == 0:
                    break
                self._paced_sleep(settings)

    def parse_rental_card(self, html: str, base_url: str) -> dict:
        """``parse_card`` for a rental-search card, plus the rental facts it states."""
        raw = self.parse_card(html, base_url=base_url)
        raw["listing_type"] = "rent"
        # A rental ad's "currently rented" wording is not a sitting tenant to buy with.
        raw["is_currently_rented"] = False
        raw["listed_rent"] = None
        text = HTMLParser(html).text(separator=" ")
        raw["furnished"] = parse_furnished(text)
        raw["available_from"] = parse_available_from(text)
        return raw

    def collect(self) -> Iterator[dict]:
        settings = get_settings()
        session = self._new_session()
        cap = settings.scrape_detail_max_per_area
        for base_url in self.search_urls(self.strategy):
            enriched = 0
            seen_ids: set[str] = set()
            # Walk pages (XE ~36/page; `&page=N` advances) until a page adds nothing new
            # or we hit the page cap — deeper collection, but no wasted requests.
            for page in range(1, settings.scrape_max_pages + 1):
                url = base_url if page == 1 else f"{base_url}&page={page}"
                # Page 1 gets the full retry budget (transient blocks matter); later pages
                # get a small budget so an empty page past the last result ends fast.
                html = self._fetch_html(session, url, max_attempts=None if page == 1 else 2)
                if not html:
                    break
                cards = HTMLParser(html).css(self.CARD_SELECTOR)
                new_on_page = 0
                for card in cards:
                    try:
                        raw = self.parse_card(self._card_html(card), base_url=url)
                    except Exception as exc:  # fail soft per card
                        logger.warning("xe: card parse error: %s", exc)
                        continue
                    if not raw:
                        continue
                    sid = raw.get("source_id")
                    if sid and sid in seen_ids:
                        continue  # already yielded on an earlier page
                    if sid:
                        seen_ids.add(sid)
                    new_on_page += 1
                    if (
                        settings.scrape_detail_pages
                        and raw.get("url")
                        and (cap == 0 or enriched < cap)
                    ):
                        self._enrich_from_detail(session, raw)
                        enriched += 1
                        self._paced_sleep(settings)
                    yield raw
                logger.info("xe: page %d -> %d new listings (%s)", page, new_on_page, base_url)
                if new_on_page == 0:
                    break  # exhausted this area's results
                self._paced_sleep(settings)

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

        bedrooms = parse_int(text(self.SEL_BEDROOMS) or detail_by_icon("xe-bedroom"))  # "2 υ/δ"
        year = parse_int(text(self.SEL_YEAR) or detail_by_icon("xe-house-construction"))

        # The card's (truncated-by-CSS but complete-in-HTML) description is the only place
        # an unfinished building is stated ("ημιτελής", "υπό κατασκευή").
        description = text(self.SEL_DESCRIPTION)
        floor = parse_floor(text(self.SEL_FLOOR))
        # Rent/private-seller surface on detail pages.
        rented, listed_rent = parse_rent(title)
        # The card footer says "Αγγελία ιδιώτη" for a private seller (agencies show a logo).
        footer = text(".common-ad-body-footer")
        private = parse_private_seller(title) or parse_private_seller(footer)

        return {
            "source": self.source,
            "source_id": source_id,
            "url": href,
            "title": title,
            "price": parse_int(text(self.SEL_PRICE)),
            "area_m2": area,
            "floor": floor,
            "bedrooms": bedrooms,
            "year_built": year,
            "neighborhood": neighborhood,
            "address": address,
            "is_currently_rented": rented,
            "listed_rent": listed_rent,
            "is_private_seller": private,
            "is_unfinished": is_unfinished_text(title, description),
            "image_url": card_image_url(tree.css(self.SEL_IMAGE), self.BASE, "xe.gr"),
        }
