"""Portal collectors. Each emits raw dicts; normalize.py maps them to Listing."""

from __future__ import annotations

from ..config import Strategy, get_settings
from .apify_xe import ApifyXeCollector
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

    Prefer the reliable, scalable Apify-backed source when an ``APIFY_TOKEN`` is
    configured; otherwise fall back to the best-effort direct XE fetch (free, but
    intermittently throttled by XE from datacenter IPs).
    """
    if get_settings().apify_token:
        return [ApifyXeCollector(strategy)]
    return [XeCollector(strategy)]


__all__ = [
    "Collector",
    "ApifyXeCollector",
    "SpitogatosCollector",
    "XeCollector",
    "IndomioCollector",
    "ALL_COLLECTORS",
    "default_collectors",
]
