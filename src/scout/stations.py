"""Rail stations (Athens Metro Lines 1–3 and the suburban railway) with Greek names.

One data file, ``data/stations.json``, holds every station with its coordinates, its source
URL and the retrieval date. ``enrich.nearest_metro`` measures against it; ``picks`` prints the
station label. The label is what a user reads and what ``listing.nearest_metro`` stores:
«Μετρό Χολαργός», «ΗΣΑΠ Περισσός», «Προαστιακός Ηράκλειο».

Older database rows hold Latin names («Holargos»); ``label()`` maps them to the same Greek label.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).with_name("data") / "stations.json"
PREFIX = {"metro": "Μετρό", "isap": "ΗΣΑΠ", "rail": "Προαστιακός"}
EARTH_RADIUS_M = 6_371_000


@dataclass(frozen=True)
class Station:
    name: str  # Greek, nominative: «Άγιος Δημήτριος»
    mode: str  # metro | isap | rail
    lines: tuple[int, ...]
    lat: float
    lng: float
    legacy: str | None = None  # the Latin name old rows hold

    @property
    def label(self) -> str:
        return f"{PREFIX[self.mode]} {self.name}"


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def meta() -> dict:
    """The data file's provenance: source, source_url, retrieved, notes."""
    doc = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in doc.items() if k != "stations"}


@lru_cache(maxsize=1)
def all_stations() -> tuple[Station, ...]:
    doc = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return tuple(
        Station(s["name"], s["mode"], tuple(s["lines"]), s["lat"], s["lng"], s.get("legacy"))
        for s in doc["stations"]
    )


@lru_cache(maxsize=1)
def _by_label() -> dict[str, Station]:
    out: dict[str, Station] = {}
    for s in all_stations():
        out[s.label] = s
        if s.legacy:
            out[s.legacy] = s
    return out


def find(name: str | None) -> Station | None:
    """The station for a stored name (Greek label or the legacy Latin name), or None."""
    return _by_label().get(name or "")


def label(name: str | None) -> str | None:
    """Greek label for a stored ``nearest_metro`` value; unknown values pass through."""
    st = find(name)
    return st.label if st else (name or None)


def nearest(lat: float, lng: float) -> tuple[Station, float]:
    """Nearest station by straight line and that distance in metres."""
    return min(
        ((s, _haversine_m(lat, lng, s.lat, s.lng)) for s in all_stations()), key=lambda t: t[1]
    )
