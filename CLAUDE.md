# CLAUDE.md — Holargos Property Scout

Daily real-estate investment assistant for the Holargos / NE-Athens market. Scrapes
listings, scores them against an investment thesis (yield, price-vs-area-median, price
drops, metro proximity), stores history, serves a Streamlit dashboard, and pushes a
daily digest. **Free + self-hosted on Oracle Cloud Always-Free. No paid services.**

## Architecture (data flow)

```
collectors → normalize → enrich (geo/metro/yield) → dedup → store(+history) → score
   │                                                              │
   └─ XE: requests.Session (server-rendered HTML, no browser)     ├─ Postgres (DATABASE_URL)
   └─ Spitogatos/Indomio: via FlareSolverr (opt-in)               └─ Streamlit dashboard + daily digest
```

- **Collectors** (`src/scout/collectors/`): `XeCollector` is the live source — fetches
  XE's server-rendered HTML with a polite `requests.Session` (no Playwright). Selectors
  are **class-based** (present in raw HTML; `data-testid` only appears after JS hydration).
  Spitogatos/Indomio go through self-hosted FlareSolverr when `FLARESOLVERR_URL` is set.
  `default_collectors(strategy)` decides what runs.
- **Pipeline** (`pipeline.py`): `run(area=…)` is **scoped to one municipality**. A run only
  scrapes one area, so retirement (`mark_unseen_as_gone`) is scoped to that area —
  NEVER retire across all areas (that mass-deletes other areas' live listings).
  `run_for_area(area)` is the per-area entry; plain `run()` defaults to the strategy
  municipality and is scoped to it.
- **Work queue** (`queue.py` + `scripts/worker.py`): horizontal scale. Areas are jobs;
  workers (one per Oracle instance / IP) claim them atomically and drain into one
  Postgres. Lease + poison-pill cap + ownership-guarded completion.
- **Storage** (`db.py`, `models.py`): SQLAlchemy. `init_db()` runs `create_all` + light
  idempotent, race-safe forward migrations (`_ensure_columns` / `_ensure_index`).
- **Alerts** (`alerts.py`, `scripts/notify.py`) + **health** (`health.py`,
  `scripts/healthcheck.py`): config-gated Telegram/email; no-op when unconfigured.

## Config

- **Operational/secrets** → env / `.env` (`config.py: Settings`). Key vars:
  `DATABASE_URL` (Postgres), `FLARESOLVERR_URL`, `TELEGRAM_BOT_TOKEN`/`_CHAT_ID`,
  `SCRAPE_*` (politeness), `HEALTH_STALE_HOURS`. See `.env.example`.
- **Investment thesis** → `strategy.yaml` (`config.py: Strategy`), hot-editable in the
  UI. `search.municipality` + `search.areas` define coverage (`all_areas()`).

## Conventions

- Python ≥3.11, `from __future__ import annotations`. Line length 100 (black + ruff).
- **Fail-soft scraping**: one bad listing/portal logs and is skipped; a run that returns
  nothing must NOT wipe existing data (the `active_sources` guard + per-area scoping).
- **Idempotent**: running the pipeline twice a day adds no duplicate history.
- **No mock/seed data** in the production path — real listings only.
- Materialize SQLAlchemy row values inside `session_scope()`; rows detach on close.
- Collector selectors live as class constants; refresh `tests/fixtures/` alongside.

## Verification gate (run before every commit)

```bash
cd /root/holargos && . .venv/bin/activate
python -m pytest -q          # must be green
ruff check src/ tests/ scripts/
black --check src/ tests/ scripts/
```

For DB-touching changes, smoke against real Postgres (see the `holargos-verify` skill).

## Workflow

- Develop on branch `claude/holargos-property-scout-8yffib`; commit with clear messages;
  fast-forward `main` and push both. Do NOT open a PR unless asked.
- The Oracle instance auto-deploys `main` every 5 min (`deploy/auto-update.sh`).
- Commit-message footer lines are added by the harness; don't put the model id in commits.

## Open backlog (safe to pick up unsupervised)

1. **Finalize Spitogatos/Indomio selectors** against a live FlareSolverr capture — the
   fetch/parse wiring is done, the within-card selectors are placeholders. → skill
   `finalize-portal-selectors`.
2. **Lease heartbeat** for very long FlareSolverr scrapes (currently a 30-min lease; a
   slower scrape could be requeued). Renew `lease_until` mid-job in `worker.py`.
3. **Generalize `scrape_job` forward-migration**: `_ensure_columns` only patches
   `listing`; add a map for `scrape_job` if its columns ever change.
4. **De-dup**: shared card-iterator (`xe.collect` vs `base._collect_via_flaresolverr`),
   shared script bootstrap (sys.path + logging + init_db across `scripts/*.py`), and a
   single retry helper (xe vs base constants).
5. **XE `SEL_LINK` hardening**: `a[href*='/property/']` + `css_first` could grab a
   non-canonical anchor if a card ever has multiple; prefer the id-regex-matching anchor.
6. **Dashboard panel** for the `scrape_job` queue + health status.
