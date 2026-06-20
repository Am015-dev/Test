"""Portal collectors. Each emits raw dicts; normalize.py maps them to Listing."""

from __future__ import annotations

from ..config import Strategy
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

    XE only for now (the maintained, reachable source). The WAF-blocked portals plug
    in here later via a FlareSolverr backend; this is the single seam to extend.
    """
    return [XeCollector(strategy)]


__all__ = [
    "Collector",
    "SpitogatosCollector",
    "XeCollector",
    "IndomioCollector",
    "ALL_COLLECTORS",
    "default_collectors",
]
