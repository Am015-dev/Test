"""Portal collectors. Each emits raw dicts; normalize.py maps them to Listing."""

from __future__ import annotations

from ..config import Strategy, get_settings
from .base import Collector
from .greenacres import GreenAcresCollector
from .indomio import IndomioCollector
from .spitogatos import SpitogatosCollector
from .xe import XeCollector

# Kept for reference/tests; Spitogatos & Indomio are WAF-blocked and not run by
# default. The pipeline builds its collectors via ``default_collectors`` instead.
ALL_COLLECTORS: list[type[Collector]] = [
    SpitogatosCollector,
    XeCollector,
    IndomioCollector,
]


def default_collectors(strategy: Strategy) -> list[Collector]:
    """The collectors the pipeline runs.

    XE and Green-Acres always (both serve static HTML to a plain client, no browser
    needed). The PerimeterX/Cloudflare-blocked portals (Spitogatos, Indomio) are added
    only when a FlareSolverr endpoint is configured to drive a real browser past their
    challenge.
    """
    collectors: list[Collector] = [XeCollector(strategy), GreenAcresCollector(strategy)]
    if get_settings().flaresolverr_url:
        collectors += [SpitogatosCollector(strategy), IndomioCollector(strategy)]
    return collectors


__all__ = [
    "Collector",
    "SpitogatosCollector",
    "XeCollector",
    "IndomioCollector",
    "GreenAcresCollector",
    "ALL_COLLECTORS",
    "default_collectors",
]
