"""Apify-backed XE collector — the reliable, scalable data source.

Instead of driving a headless browser from a datacenter IP (which XE throttles to
empty pages), this calls Apify's maintained xe.gr actor. Apify runs the scrape on
its cloud with GR residential proxies and anti-bot handling, returning structured
JSON — so it isn't IP-blocked and scales across areas just by adding geo place ids.

Used automatically when ``APIFY_TOKEN`` is set (see ``collectors.default_collectors``).
Pricing is ~$3.50 / 1000 results; a daily Holargos scrape is a few cents.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import requests

from ..config import Strategy, get_settings
from .base import Collector
from .parse_helpers import parse_floor, parse_int
from .xe import XeCollector

logger = logging.getLogger(__name__)


class ApifyXeCollector(Collector):
    source = "xe"
    API_BASE = "https://api.apify.com/v2/acts"
    VARIATION = "apartment-for-sale"

    def search_urls(self, strategy: Strategy) -> list[str]:  # not used (JSON API, no pages)
        return []

    def parse_card(self, html: str, base_url: str) -> dict:  # not used (actor returns JSON)
        return {}

    def _actor_path(self) -> str:
        # Apify API addresses actors as "username~actorname".
        return get_settings().apify_xe_actor.replace("/", "~")

    def _build_input(self) -> dict | None:
        s = self.strategy.search
        place_id = XeCollector(self.strategy)._resolve_place_id(s.municipality)
        if not place_id:
            logger.warning("apify-xe: could not resolve geo place id for %r", s.municipality)
            return None
        return {
            "geoPlaceIds": [place_id],
            "variation": self.VARIATION,
            "priceMin": s.price_min,
            "priceMax": s.price_max,
            "sqmMin": int(s.area_min_m2),
            "language": "el",
            "maxListings": 1000,
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": "GR",
            },
        }

    def collect(self) -> Iterator[dict]:
        settings = get_settings()
        if not settings.apify_token:
            logger.warning("apify-xe: no APIFY_TOKEN set; yielding nothing")
            return
        payload = self._build_input()
        if payload is None:
            return

        url = f"{self.API_BASE}/{self._actor_path()}/run-sync-get-dataset-items"
        try:
            resp = requests.post(
                url,
                params={"token": settings.apify_token},
                json=payload,
                timeout=300,  # the actor runs synchronously
                verify=not settings.scrape_ignore_https_errors,
            )
            resp.raise_for_status()
            items = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("apify-xe: actor run failed: %s", exc)
            return

        logger.info("apify-xe: actor returned %d items", len(items))
        for item in items:
            raw = self.map_item(item)
            if raw:
                yield raw

    @staticmethod
    def map_item(item: dict) -> dict | None:
        """Map one Apify actor result onto our raw collector dict."""
        ad_id = item.get("adId")
        if not ad_id:
            return None
        return {
            "source": "xe",
            "source_id": str(ad_id),
            "url": item.get("detailUrl"),
            "title": item.get("title"),
            "price": parse_int(str(item.get("price"))) if item.get("price") is not None else None,
            "area_m2": _to_float(item.get("sqMeters")),
            "floor": (
                parse_floor(str(item.get("floors"))) if item.get("floors") is not None else None
            ),
            "bedrooms": (
                parse_int(str(item.get("bedrooms"))) if item.get("bedrooms") is not None else None
            ),
            "year_built": (
                parse_int(str(item.get("yearBuilt"))) if item.get("yearBuilt") is not None else None
            ),
            "neighborhood": item.get("area") or item.get("city"),
            "address": item.get("location") or item.get("area"),
            "price_per_m2": _to_float(item.get("pricePerSqm")),
        }


def _to_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
