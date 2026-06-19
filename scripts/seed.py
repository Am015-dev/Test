"""Seed the DB with a few hand-entered listings to verify upsert-with-history.

Run it twice: the second run must NOT create duplicate price_history rows. Change
a price and re-run: exactly one new price_history row should appear.

    python scripts/seed.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scout.config import load_strategy  # noqa: E402
from scout.db import init_db, session_scope, upsert_listing_with_history  # noqa: E402
from scout.enrich import enrich_listing  # noqa: E402
from scout.models import Listing  # noqa: E402
from scout.scoring import compute_market_stats, score  # noqa: E402

SEED_LISTINGS = [
    Listing(
        source="spitogatos",
        source_id="seed-1",
        url="https://www.spitogatos.gr/listing/seed-1",
        title="Renovated 2BR, Ano Cholargos, 3rd floor",
        price=215_000,
        area_m2=82.0,
        rooms=3,
        bedrooms=2,
        floor=3.0,
        year_built=1998,
        neighborhood="Ano Cholargos",
        address="Ano Cholargos, Athens, Greece",
        lat=38.0010,
        lng=23.7975,
        is_private_seller=True,
        is_currently_rented=True,
        listed_rent=850,
    ),
    Listing(
        source="spitogatos",
        source_id="seed-2",
        url="https://www.spitogatos.gr/listing/seed-2",
        title="Bright flat near Faneromeni",
        price=168_000,
        area_m2=64.0,
        rooms=2,
        bedrooms=1,
        floor=2.0,
        neighborhood="Faneromeni",
        address="Faneromeni, Cholargos, Greece",
        lat=37.9990,
        lng=23.7950,
    ),
    Listing(
        source="xe",
        source_id="seed-3",
        url="https://www.xe.gr/property/seed-3",
        title="Ground floor maisonette (should be excluded)",
        price=240_000,
        area_m2=110.0,
        rooms=4,
        bedrooms=3,
        floor=0.0,
        neighborhood="Plateia Dimokratias",
        address="Plateia Dimokratias, Cholargos, Greece",
    ),
    Listing(
        source="indomio",
        source_id="seed-4",
        url="https://www.indomio.gr/property/seed-4",
        title="Top-floor apartment, Lofos Tsakou",
        price=295_000,
        area_m2=95.0,
        rooms=3,
        bedrooms=2,
        floor=5.0,
        neighborhood="Lofos Tsakou",
        address="Lofos Tsakou, Cholargos, Greece",
        lat=38.0040,
        lng=23.8010,
    ),
]


def main() -> None:
    strategy = load_strategy()
    init_db()
    now = datetime.utcnow()

    # Enrich offline (no geocode/OSRM) so seeding is deterministic and network-free.
    enriched = [enrich_listing(lst, use_network=False) for lst in SEED_LISTINGS]
    market_stats = compute_market_stats(enriched)

    with session_scope() as session:
        for lst in enriched:
            scored = score(lst, market_stats, strategy)
            row = upsert_listing_with_history(session, lst, observed_at=now)
            row.score = scored.score
            row.is_opportunity = scored.is_opportunity
            row.excluded = scored.excluded
            row.exclusion_reason = scored.exclusion_reason

    print(f"Seeded {len(enriched)} listings into the DB.")


if __name__ == "__main__":
    main()
