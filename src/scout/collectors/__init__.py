"""Portal collectors. Each emits raw dicts; normalize.py maps them to Listing."""

from __future__ import annotations

from ..config import Strategy, get_settings
from .base import Collector
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

    XE always (reachable over plain HTTP). The WAF-blocked portals are added only
    when a FlareSolverr endpoint is configured to reach them.
    """
    collectors: list[Collector] = [XeCollector(strategy)]
    if get_settings().flaresolverr_url:
        collectors += [SpitogatosCollector(strategy), IndomioCollector(strategy)]
    return collectors


__all__ = [
    "Collector",
    "SpitogatosCollector",
    "XeCollector",
    "IndomioCollector",
    "ALL_COLLECTORS",
    "default_collectors",
]
