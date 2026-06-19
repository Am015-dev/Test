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

Portal markup changes and is bot-guarded. Selectors live as class constants in each
collector, so a redesign is a one-file fix; update the constants and refresh the
fixtures. Be considerate: the crawler throttles (2–5 s between pages), sets a real
User-Agent, waits for network-idle, and crawls one source at a time.

## Disclaimer

This tool ranks and surfaces listings; it does **not** give financial or legal
advice. Yields are heuristic estimates. Verify titles, planning/πολεοδομία status,
and tax eligibility with a lawyer and accountant before any purchase, and confirm
that scraping each portal is consistent with its current Terms of Service.
