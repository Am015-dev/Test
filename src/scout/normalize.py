"""Raw collector dict -> canonical Listing.

Collectors never leak portal-specific fields downstream: anything not in the
canonical schema (e.g. ``description``) is consumed here and dropped. Normalization
fails soft — a raw dict missing required fields is skipped (returns None) rather
than crashing the pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime

from .data_quality_guards import clean_future_years
from .models import Listing

logger = logging.getLogger(__name__)

# Fields the canonical Listing accepts; everything else in a raw dict is dropped.
_ALLOWED = set(Listing.model_fields.keys())


def normalize(raw: dict, now: datetime | None = None) -> Listing | None:
    """Map a raw collector dict onto a canonical Listing, or None if unusable."""
    now = now or datetime.utcnow()

    source = raw.get("source")
    source_id = raw.get("source_id")
    url = raw.get("url")
    price = raw.get("price")
    area = raw.get("area_m2")

    # Required fields. Without these the listing is meaningless — skip it.
    if not source or not source_id or not url:
        logger.debug("dropping raw without source/source_id/url: %s", raw)
        return None
    # Validate the SIGN, not just truthiness: `not price` rejects 0/None but a garbled
    # negative price (bool(-50000) is True) would sail through and later produce a
    # negative €/m² that clamps to a maxed-out "priced well below market" signal.
    if not price or price <= 0 or not area or area <= 0:
        logger.debug("dropping %s:%s without usable price/area", source, source_id)
        return None

    payload = {k: v for k, v in raw.items() if k in _ALLOWED}
    payload.setdefault("first_seen", now)
    payload.setdefault("last_seen", now)
    # A future build/renovation year is a data error (the year, not the listing, is wrong):
    # null it here so it never reaches valuation/scoring or gets shown as-is. The suspect
    # FLAG is raised downstream in the UI (data_quality_guards.future_year_flag).
    payload["year_built"], payload["renovated_year"] = clean_future_years(
        payload.get("year_built"), payload.get("renovated_year"), current_year=now.year
    )

    # Collectors that don't detect it omit the key; a None must not fail the bool field.
    payload["is_unfinished"] = bool(payload.get("is_unfinished"))

    try:
        return Listing(**payload)
    except Exception as exc:  # fail soft on validation errors
        logger.warning("normalize failed for %s:%s: %s", source, source_id, exc)
        return None
