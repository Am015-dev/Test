"""Cross-source deduplication.

The same flat is often listed on multiple portals (or re-posted). We collapse
near-duplicates using a cheap signature: rounded area + price bucket + a
normalized neighborhood/title token set. When two listings from different sources
match, we keep one canonical record and remember the alternate source links.

This is intentionally conservative: false merges are worse than a few dupes, so
matching requires close area AND close price AND overlapping location text.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .models import Listing

# Tolerances for considering two listings the same physical property.
AREA_TOL_M2 = 3.0
PRICE_TOL_PCT = 0.05


def _norm_text(text: str | None) -> set[str]:
    if not text:
        return set()
    nfkd = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    tokens = re.findall(r"[a-z0-9]+", stripped)
    return {t for t in tokens if len(t) > 2}


def _location_tokens(listing: Listing) -> set[str]:
    """Location-identifying tokens — neighborhood preferred, address as backup.

    The title is deliberately excluded: generic words ("flat", "bright") there
    cause false merges. Same physical property must share a location.
    """
    tokens = _norm_text(listing.neighborhood)
    if not tokens:
        tokens = _norm_text(listing.address)
    return tokens


def _similar(a: Listing, b: Listing) -> bool:
    if abs(a.area_m2 - b.area_m2) > AREA_TOL_M2:
        return False
    hi = max(a.price, b.price)
    if hi and abs(a.price - b.price) / hi > PRICE_TOL_PCT:
        return False
    # Require location overlap to avoid merging unrelated flats of similar size/price.
    ta, tb = _location_tokens(a), _location_tokens(b)
    if not ta or not tb:
        return False
    return bool(ta & tb)


@dataclass
class DedupGroup:
    canonical: Listing
    duplicates: list[Listing] = field(default_factory=list)

    @property
    def alternate_urls(self) -> list[str]:
        return [d.url for d in self.duplicates]


def deduplicate(listings: list[Listing]) -> list[DedupGroup]:
    """Group near-duplicate listings. Canonical = lowest price (best deal surfaced).

    Same-source/same-id exact dupes collapse first; then cross-source fuzzy match.
    """
    # Collapse exact (source, source_id) dupes, keeping the last seen.
    by_key: dict[str, Listing] = {}
    for lst in listings:
        by_key[lst.dedup_key] = lst
    unique = list(by_key.values())

    groups: list[DedupGroup] = []
    for lst in unique:
        placed = False
        for group in groups:
            if _similar(group.canonical, lst):
                # Keep the cheaper one canonical; demote the other.
                if lst.price < group.canonical.price:
                    group.duplicates.append(group.canonical)
                    group.canonical = lst
                else:
                    group.duplicates.append(lst)
                placed = True
                break
        if not placed:
            groups.append(DedupGroup(canonical=lst))
    return groups
