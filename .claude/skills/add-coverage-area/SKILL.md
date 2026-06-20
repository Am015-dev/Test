---
name: add-coverage-area
description: Add a new municipality/area to the scraper's coverage and verify it resolves and scrapes. Use when the user asks to track an additional area/neighborhood/municipality, or to expand beyond Holargos. Covers strategy config, geo-id resolution check, a scoped test run, and the scale-out note.
---

# Add a coverage area

Areas are municipalities the workers scrape, each as its own queue job. They all share
the scoring thesis, so keep new areas on the **same metro corridor** as Holargos (the
scoring weights metro proximity, configured POIs, etc.).

## Steps

1. **Add the area** to `strategy.yaml` under `search.areas` (a list). `search.municipality`
   stays the primary; `all_areas()` = municipality + areas, de-duplicated.
   ```yaml
   search:
     municipality: Cholargos
     areas: [Papagou, "Agia Paraskevi"]
   ```

2. **Verify XE can resolve its geo place id** (results are filtered server-side by it):
   ```bash
   cd /root/holargos && . .venv/bin/activate && SCRAPE_IGNORE_HTTPS_ERRORS=true python -c "
   from scout.collectors.xe import XeCollector
   from scout.config import load_strategy
   print(XeCollector(load_strategy())._resolve_place_id('Agia Paraskevi'))
   "
   ```
   A `None` means XE's autocomplete didn't match — try the exact Greek/English name XE
   uses; if it still fails the area will fall back to an unfiltered search.

3. **Scoped test run** for the new area against a real DB (ideally Postgres — see
   `holargos-verify`). Confirm listings come back tagged with `search_area`:
   ```bash
   python -c "
   from scout.pipeline import run_for_area
   print(run_for_area('Agia Paraskevi'))
   "
   ```
   Expect a summary dict; `stored`/`deduped` > 0 if XE isn't rate-limiting that IP.

4. **Check scoring sanity**: the metro-distance hard filter and POIs in `strategy.yaml`
   must cover the new area, or all its listings get excluded. If the area is on a
   different line, extend the metro/POI config accordingly.

5. **Confirm the queue picks it up**: `python scripts/enqueue.py` then
   `python scripts/worker.py` drains all `all_areas()`. `queue.job_stats()` should show
   the new area's job done. Health (`scripts/healthcheck.py`) flags an area that returns
   zero.

6. Run the verification gate, commit, merge to `main`.

## Scale note
One control VM drains all areas sequentially. To parallelize across IPs, add extra Oracle
Always-Free instances running `docker compose --profile worker up -d` with `DATABASE_URL`
pointed at the control VM's Postgres — each scrapes from its own public IP, dodging XE's
per-IP rate limit. More areas → more instances, never more load on one IP.
