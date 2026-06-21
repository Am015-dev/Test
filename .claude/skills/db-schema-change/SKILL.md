---
name: db-schema-change
description: Safely add or change a column on the SQLAlchemy models in this project, given that production runs on a long-lived Postgres DB that already has data. Use whenever you add a field to Listing/ListingRow/ScrapeJobRow or any model. Encodes the migration trap — create_all never alters an existing table — and the race-safe forward-migration pattern.
---

# Change the DB schema safely

The trap: `Base.metadata.create_all()` (called by `init_db`) creates **new tables** but
**never alters an existing one**. On a fresh dev SQLite it "just works"; on the
already-deployed Postgres the new column is silently missing and queries crash. This
project handles it with idempotent, race-safe forward migrations in `init_db`.

## Steps to add a column

1. **Add it to the model** in `src/scout/models.py` (both the pydantic `Listing` if it's
   a listing field, and the ORM `ListingRow`). Use a nullable type so existing rows are
   valid.

2. **Add a forward migration** in `src/scout/db.py: init_db` so existing DBs get patched:
   ```python
   _ensure_columns(engine, "listing", {"search_area": "VARCHAR(128)", "your_col": "SQL_TYPE"})
   _ensure_index(engine, "ix_listing_your_col", "listing", "your_col")   # only if indexed
   ```
   `_ensure_columns` already: checks existence, adds each column in its own transaction,
   and tolerates a concurrent worker's "column already exists" (race-safe). Don't bypass it
   with a bare `ALTER`.

3. **Wire it through** if it's a listing field: add to `_SNAPSHOT_FIELDS` in `db.py` (so
   `upsert_listing_with_history` copies it), to the collector's `parse_card` output and
   `normalize.py`, and to `ui/queries.py: _row_to_dict` if the UI/digest needs it.

4. **Backfill** if existing rows need a non-null/derived value: do a one-time guarded
   `UPDATE` in the pipeline (see how `search_area` is backfilled in `pipeline.run`), not in
   `_ensure_columns` (which is schema-only and strategy-agnostic).

5. **Test on real Postgres**, not just SQLite — that's where the migration matters. Use
   `holargos-verify` step 2: drop+`init_db` against Postgres, confirm the column/index
   exist and a pipeline run succeeds. Also confirm idempotency (run `init_db` twice).

## For a NEW table
Just declare the model; `create_all` makes it. But if you later add columns to a table
that already exists in production (e.g. `scrape_job`), you MUST add a `_ensure_columns`
entry for it too — `create_all` won't patch it.

## Gotchas
- Postgres is case/sort-strict and enforces NOT NULL immediately — add columns nullable.
- `CREATE INDEX IF NOT EXISTS` and per-column `ADD COLUMN` are used so concurrent workers
  racing `init_db` on boot don't crash each other.
