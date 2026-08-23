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

src_meta = MetaData()
src_meta.reflect(bind=src_engine)

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
tables = [src_meta.tables[name] for name in order if name in src_meta.tables]
tables += [t for t in src_meta.tables.values() if t.name not in order]


def _fill_none_with_orm_defaults(row: dict, dst_table) -> None:
    """A historical SQLite row can carry NULL in a column the ORM model declares NOT NULL
    with a Python-side default (e.g. negotiation_score: Mapped[float] = mapped_column(...,
    default=0.0)) — that default is applied by the ORM's own insert path, which this
    bulk Core insert() bypasses entirely, so raw NULLs would hit Postgres's real NOT NULL
    constraint. Substitute the model's own default for any such NULL — exactly what a
    normal ORM insert would have produced for that row in the first place."""
    for col in dst_table.columns:
        if row.get(col.name) is None and not col.nullable and col.default is not None:
            arg = col.default.arg
            row[col.name] = arg(None) if callable(arg) else arg


with src_engine.connect() as sconn, dst_engine.begin() as dconn:
    for table in tables:
        rows = [dict(r._mapping) for r in sconn.execute(select(table))]
        # Insert against the ORM-DECLARED table (Base.metadata), not the SQLite-reflected
        # one — it's what create_all() actually built on Postgres, and it's the only place
        # nullable/default info (needed above) lives; a bare SQLite reflection has neither.
        dst_table = Base.metadata.tables[table.name]
        for row in rows:
            _fill_none_with_orm_defaults(row, dst_table)
        dconn.execute(dst_table.delete())
        if rows:
            dconn.execute(insert(dst_table), rows)
        print(f"{table.name}: {len(rows)} rows migrated", flush=True)

print("done", flush=True)
