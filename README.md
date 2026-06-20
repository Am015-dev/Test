# 🏠 Holargos Property Scout

A daily real-estate investment assistant for the Holargos / Athens market. It
collects listings from property portals via Playwright, normalizes and
de-duplicates them, scores each one against a configurable investment strategy
(yield, €/m², floor, metro distance, price drops), tracks price & status history
over time, and surfaces the best opportunities in a Streamlit web app.

> Answers one question every morning: *"What should I look at today, and which
> listings just dropped in price?"*

## What it does

- **Collect** — scheduled scrape of configured portals (Spitogatos, XE, Indomio)
  with Playwright (headless Chromium). Selectors are class constants; raw HTML is
  saved under `data/raw/` so parsing is replayable offline.
- **Normalize** — every portal maps onto one canonical `Listing` schema.
- **Dedup** — the same flat across portals collapses to one record (cheapest kept).
- **Enrich** — €/m², geocoding (Nominatim, cached), walking distance to the nearest
  Metro Line 3 station (OSRM with haversine×1.3 fallback), estimated rent, gross yield.
- **Score** — pure, unit-tested engine driven entirely by `strategy.yaml`: hard
  filters (exclude floor ≤ 0, exclude > 600 m from metro) + weighted soft signals
  (yield, price-vs-median, price drop, currently-rented, private-seller) → 0–100.
- **Track history** — `price_history` / `status_history` tables. Price-cut detection
  and days-on-market fall out of these; the upsert appends history only on real change.
- **Surface** — Streamlit app: Today, All opportunities, Map, Listing detail (with
  price-history chart), Watchlist, and a live Strategy editor.

## Architecture

```
src/scout/
  config.py        # Settings (.env) + Strategy (strategy.yaml) loader
  models.py        # Pydantic Listing + SQLAlchemy tables (+ history, geocode cache)
  db.py            # engine/session + upsert_listing_with_history (idempotent)
  collectors/      # Collector ABC + spitogatos/xe/indomio + Greek parse helpers
  normalize.py     # raw dict -> canonical Listing (fails soft)
  enrich.py        # geocode, metro distance, €/m², est rent, gross yield
  dedup.py         # cross-source matching
  scoring.py       # pure filters + weighted score + market stats
  pipeline.py      # collect -> normalize -> enrich -> dedup -> store -> score
  alerts.py        # optional NEW + PRICE-drop digest (Telegram/email, off by default)
  ui/app.py        # Streamlit entrypoint (read-only over the DB)
scripts/
  run_daily.py     # cron entrypoint (seeds demo data if portals yield nothing)
  seed.py          # hand-entered listings to verify upsert-with-history
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium          # only needed for live scraping
cp .env.example .env                 # adjust geocoder UA etc.

python scripts/seed.py               # populate the DB with demo listings
streamlit run src/scout/ui/app.py    # launch the UI

# real daily run (scrapes portals; falls back to seeding if none reachable)
python scripts/run_daily.py
```

## Configuration

- `strategy.yaml` — investor rules & weights. **Hot-editable**: change neighborhoods,
  price band, hard filters, or weights and re-score without touching code (also
  editable live from the UI Strategy page).
- `.env` — operational config: geocoder User-Agent, DB path, OSRM base URL, optional
  alert credentials. See `.env.example`.

## Scheduling

- **Cron (prod):** run `scripts/run_daily.py` each morning; Streamlit just reads the DB.
- **In-app:** the UI has a "Refresh now" button that runs the pipeline on demand.

Runs are **idempotent** — running twice in a day creates no duplicate history rows.

## Tests

```bash
pytest            # scoring, enrichment, parse helpers, normalize, dedup, db history, pipeline
ruff check . && black --check .
```

Parser tests run offline against saved HTML fixtures in `tests/fixtures/`, so the
suite never needs the network or a live portal.

## Notes on scraping

Selectors live as class constants in each collector, so a portal redesign is a
one-file fix; update the constants and refresh the fixtures. Be considerate: the
crawler throttles (2–5 s between pages), sets a real User-Agent, waits for
network-idle, and crawls one source at a time.

Current collector status:

- **XE** — hardened against live markup (cards are `div.common-ad-body` with
  `data-testid` fields). Verified end-to-end: a live run scrapes, parses, dedups,
  scores and stores real listings. Geo filtering is server-side: the `municipality`
  in `strategy.yaml` is resolved to a `geo_place_id` via XE's autocomplete API
  (`/services/places/autocomplete`) and passed on the search URL, so results come
  back already scoped to the target area instead of spanning all of Athens. If the
  autocomplete is unreachable the collector falls back to the (unfiltered)
  `geo_place_name` search so it still returns something. `tests/fixtures/xe_card.html`
  is a real captured card.
- **Spitogatos, Indomio** — behind a CloudFront/WAF that 403s a plain client. Set
  `FLARESOLVERR_URL` (start the free `flaresolverr` compose service) and they're
  scraped through it — FlareSolverr drives a real browser and solves the challenge,
  returning rendered HTML, so they're added to the default collectors automatically.
  Their within-card selectors are reasonable placeholders; finalize them against the
  first live capture under `data/raw/` (the rest of the pipeline is unaffected).

Behind a TLS-intercepting proxy, set `SCRAPE_IGNORE_HTTPS_ERRORS=true` (defaults to
strict TLS).

## Reliability & scaling (Oracle, free)

XE serves **server-rendered HTML**, so the collector fetches it with a plain
cookie-persisting `requests` session — **no headless browser** (the image ships no
Chromium). XE rate-limits per IP: an over-frequent request returns an empty page, so
the fetcher (a) keeps requests polite/spaced, (b) retries empties with backoff and
logs a clear block signal, and (c) caches a good page for `SCRAPE_CACHE_TTL_MINUTES`
so re-runs don't re-hit XE. The pipeline is fail-soft and never wipes existing data on
an empty run.

**Storage** is Postgres (the `db` service in `docker-compose.yml`); set
`DATABASE_URL` (defaults to the compose DSN). Shared Postgres is the foundation for
scaling: multiple scraper **workers**, each on its own Oracle Always-Free instance
(so each has a distinct public IP), write to the one database. `default_collectors`
is the single seam where additional sources/backends (e.g. a self-hosted FlareSolverr
for the WAF-blocked portals) plug in.

### Scaling to more areas (the worker queue)

List the municipalities to cover under `search.areas` in `strategy.yaml` (they share
the scoring thesis, so keep them on the same metro corridor). Each becomes a job in a
shared `scrape_job` queue:

- `scripts/enqueue.py` — adds one pending job per area (cron, control VM).
- `scripts/worker.py` — claims pending areas atomically, scrapes each from its own
  IP, writes to Postgres, marks them done. A crashed worker's lease expires and the
  area is requeued, so work is never lost. `run_for_area` scopes retirement per area,
  so concurrent workers never retire each other's listings.

The control VM's daily cron runs `enqueue` then `worker` (drains locally). To scale,
spin up extra Oracle Always-Free instances, point their `.env` `DATABASE_URL` at the
control VM's Postgres, and run `docker compose --profile worker up -d` — they drain
the same queue in parallel, each from a distinct public IP. More areas → more
instances, never more load on one IP.

## Disclaimer

This tool ranks and surfaces listings; it does **not** give financial or legal
advice. Yields are heuristic estimates. Verify titles, planning/πολεοδομία status,
and tax eligibility with a lawyer and accountant before any purchase, and confirm
that scraping each portal is consistent with its current Terms of Service.
