"""Portal collectors. Each emits raw dicts; normalize.py maps them to Listing."""

from .base import Collector
from .indomio import IndomioCollector
from .spitogatos import SpitogatosCollector
from .xe import XeCollector

ALL_COLLECTORS: list[type[Collector]] = [
    SpitogatosCollector,
    XeCollector,
    IndomioCollector,
]

__all__ = [
    "Collector",
    "SpitogatosCollector",
    "XeCollector",
    "IndomioCollector",
    "ALL_COLLECTORS",
]
