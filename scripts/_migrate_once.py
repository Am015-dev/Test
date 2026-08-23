"""ONE-OFF migration: copy the historical SQLite DB into Postgres (DATABASE_URL).

Run once via the .github/workflows/migrate-once.yml workflow_dispatch job — this
sandbox's own network only permits HTTPS egress, not raw Postgres TCP, so the copy
has to happen on a runner with normal networking. Safe to re-run (idempotent: deletes
then reloads each table). Delete this script + its workflow after a successful run.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "src")

from sqlalchemy import MetaData, create_engine, insert, select  # noqa: E402

from scout.models import Base  # noqa: E402

SQLITE_PATH = os.environ.get("OLD_SQLITE_PATH", "old_data/data/listings.db")
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"
pg_url = os.environ["DATABASE_URL"]
if pg_url.startswith("postgres://") or pg_url.startswith("postgresql://"):
    pg_url = "postgresql+psycopg://" + pg_url.split("://", 1)[1]

src_engine = create_engine(SQLITE_URL, future=True)
dst_engine = create_engine(pg_url, future=True)

Base.metadata.create_all(dst_engine)

meta = MetaData()
meta.reflect(bind=src_engine)

# FK-safe order: listing before tables that reference it; anything unlisted goes last.
order = [
    "listing",
    "price_history",
    "status_history",
    "geocode_cache",
    "scrape_job",
    "rent_comp",
    "saved_search",
    "health_report",
]
tables = [meta.tables[name] for name in order if name in meta.tables]
tables += [t for t in meta.tables.values() if t.name not in order]

with src_engine.connect() as sconn, dst_engine.begin() as dconn:
    for table in tables:
        rows = [dict(r._mapping) for r in sconn.execute(select(table))]
        dst_table = meta.tables[table.name]
        dconn.execute(dst_table.delete())
        if rows:
            dconn.execute(insert(dst_table), rows)
        print(f"{table.name}: {len(rows)} rows migrated", flush=True)

print("done", flush=True)
