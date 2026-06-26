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
  Health results are persisted to the `health_report` table after every run.

## Config

- **Operational/secrets** → env / `.env` (`config.py: Settings`). Key vars:
  `DATABASE_URL` (Postgres), `FLARESOLVERR_URL`, `TELEGRAM_BOT_TOKEN`/`_CHAT_ID`,
  `SCRAPE_*` (politeness), `HEALTH_STALE_HOURS`. See `.env.example`.
- **Investment thesis** → `strategy.yaml` (`config.py: Strategy`), hot-editable in the
  UI. `search.municipality` + `search.areas` define coverage (`all_areas()`).

## Conventions

- Python ≮3.11, `from __future__ import annotations`. Line length 100 (black + ruff).
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

## Project skills (`.claude/skills/`)

Invoke the matching skill for these recurring tasks (plus the vendored `superpowers`
general-workflow skills — see `.claude/skills/NOTICE.md`):

| Task | Skill |
|---|---|
| Run the test/lint gate + real-Postgres smoke + ship | `holargos-verify` |
| A live collector returns 0 cards / wrong fields (markup changed) | `repair-collector` |
| Healthcheck pages WARN/ERROR (stale / blocked / partial) — what to do | `triage-scraper-health` |
| Add/change a DB column safely (the migration trap) | `db-schema-change` |
| Add a brand-new portal source | `add-portal` |
| Bring up the WAF portals (Spitogatos/Indomio) via FlareSolverr | `finalize-portal-selectors` |
| Add a coverage municipality | `add-coverage-area` |
| Change scoring weights / filters / thesis | `tune-scoring` |
| Daily ops loop (observe → triage → fix → escalate) | `autonomous-ops` |
| Ship a fix safely: gate → CI → merge → verify autodeploy | `self-deploy-safely` |
| Weekly data-quality + coverage + dependency sweep | `weekly-review` |

**MCP servers** (`.claude/mcp/`, live config `/.mcp.json`): `postgres` (read-only DB
inspection), `playwright` (render WAF/JS portals for selector work), `fetch` (HTML pulls).
GitHub MCP is provided by the environment. See `.claude/README.md` for the full toolkit
index (skills + MCP + plugins).

## Cross-session memory

- **`docs/OPS_LOG.md`** — agent-maintained log; append one entry per ops cycle or
  notable event. Newest at the top.
- **`health_report` table** — every `scripts/healthcheck.py` run appends a row.
  Read via the postgres MCP to see recent system state without needing log access:
  ```sql
  SELECT checked_at, status, issues, metrics
  FROM health_report ORDER BY checked_at DESC LIMIT 5;
  ```
- **CI** — use `mcp__github__actions_list` on `main` to get the latest gate result.

## Guardrail allow-list

The agent may do these **without owner sign-off**:
- CSS selector constant updates in `src/scout/collectors/`
- Add or fix a test that doesn’t change production behaviour
- Patch-version dep bump in `pyproject.toml` (x.y.**Z** → x.y.**Z+1**)
- Add or fix a `scripts/` entrypoint or logging call
- Re-enqueue failed scrape jobs (`python scripts/enqueue.py`)
- Document findings in `docs/OPS_LOG.md`
- Restart a crashed Docker service (log it in OPS_LOG)

The agent **MUST stop and send a Telegram alert** before:
- DB schema changes (new column / table / index)
- `strategy.yaml` / scoring / hard-filter changes
- Secrets rotation or new env vars that affect production
- Adding a new portal source
- Topology changes (new Oracle instance, new port, new service)
- Anything that can delete or retire data
- Cost-affecting changes
- Same failure persisting for ≥ 3 consecutive autonomous cycles

Escalate via:
```python
from scout.alerts import send_alert
send_alert(
    "🆘 Holargos Agent blocked.\nIssue: <issue>\nTried: <action>\nNeed: <decision>"
)
```

## Workflow

- Develop on branch `claude/holargos-property-scout-8yffib`; commit with clear messages;
  fast-forward `main` and push both. Do NOT open a PR unless asked.
- The Oracle instance auto-deploys `main` every 5 min (`deploy/auto-update.sh`).
- CI runs on every push via `.github/workflows/ci.yml` (pytest + ruff + black).
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
7. **Phase B triggers**: scheduled agent ops runs + subscribe to CI/PR activity for
   event-driven auto-fix. Depends on hosting decision (Oracle stable IP required).
