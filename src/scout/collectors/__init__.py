"""Portal collectors. Each emits raw dicts; normalize.py maps them to Listing."""

from __future__ import annotations

import logging
import os

from ..config import Strategy, get_settings
from .base import Collector
from .goldenhome import GoldenHomeCollector
from .greenacres import GreenAcresCollector
from .indomio import IndomioCollector
from .spitogatos import SpitogatosCollector
from .xe import XeCollector

logger = logging.getLogger(__name__)

# Kept for reference/tests; Spitogatos & Indomio are WAF-blocked and not run by
# default. The pipeline builds its collectors via ``default_collectors`` instead.
ALL_COLLECTORS: list[type[Collector]] = [
    SpitogatosCollector,
    XeCollector,
    IndomioCollector,
]


# Collectors selectable by the ``SOURCES`` env toggle (comma-separated names).
BY_NAME: dict[str, type[Collector]] = {
    c.source: c for c in (XeCollector, GreenAcresCollector, GoldenHomeCollector)
}
# Display name per ``Listing.source`` for the UI's source label and coverage line.
SOURCE_LABELS: dict[str, str] = {
    "xe": "XE.gr",
    "greenacres": "Green-Acres",
    "goldenhome": "Golden Home",
    "spitogatos": "Spitogatos",
    "indomio": "Indomio",
}
# What runs when ``SOURCES`` is unset: the sources that were live before the toggle existed.
DEFAULT_SOURCES = ("xe", "greenacres")


def enabled_sources() -> list[str]:
    """Source names from ``SOURCES`` (e.g. ``xe,remax``), else ``DEFAULT_SOURCES``.
    Unknown names are logged and ignored, never fatal."""
    raw = os.environ.get("SOURCES", "")
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]
    if not names:
        return list(DEFAULT_SOURCES)
    unknown = [n for n in names if n not in BY_NAME]
    if unknown:
        logger.warning("SOURCES: ignoring unknown source(s) %s", ", ".join(unknown))
    return [n for n in dict.fromkeys(names) if n in BY_NAME]


def default_collectors(strategy: Strategy) -> list[Collector]:
    """The collectors the pipeline runs.

    The plain-HTTP sources named by ``SOURCES`` (default XE + Green-Acres; all serve
    static HTML to a plain client, no browser needed). The PerimeterX/Cloudflare-blocked
    portals (Spitogatos, Indomio) are added only when a FlareSolverr endpoint is
    configured to drive a real browser past their challenge.
    """
    collectors: list[Collector] = [BY_NAME[n](strategy) for n in enabled_sources()]
    if get_settings().flaresolverr_url:
        collectors += [SpitogatosCollector(strategy), IndomioCollector(strategy)]
    return collectors


__all__ = [
    "Collector",
    "SpitogatosCollector",
    "XeCollector",
    "IndomioCollector",
    "GreenAcresCollector",
    "GoldenHomeCollector",
    "enabled_sources",
    "SOURCE_LABELS",
    "ALL_COLLECTORS",
    "default_collectors",
]
