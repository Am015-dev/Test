# Listing sources — which Greek portals we can read (survey 2026-10-31)

The owner compares us with noikaki.gr, which aggregates many portals. This page records,
portal by portal, whether a **GitHub runner with plain `requests`** (no browser, no paid
proxy) can read a sale search page, what robots.txt says, and what we did about it.

How it was measured: `diag/sources_probe.py`, run by `.github/workflows/diag-sources.yml`
on `ubuntu-latest` (Azure, westcentralus). Real browser User-Agent, `el-GR`, 4–7 s between
every request, robots.txt read first. The dev sandbox cannot reach any of these hosts, so
every number below comes from the runner log (runs 41217895673, 41218204255, 41218453286
and the smoke run listed at the bottom).

## Survey

| Portal | Search page from runner | Cards in raw HTML | JSON / API | robots.txt for search | Verdict |
|---|---|---|---|---|---|
| **goldenhome.gr** | 200, `/property/pwlisi/katoikies/perioxi-holargos`, 434 KB | yes — 30 `article.property-card` / page, price, m², floor, year, bedrooms, photo count | map GeoJSON in page (ids + prices, fuzzed coords) | allowed (disallows only `/api`, `/backend`, `/console`, `?sort=`, `OFFSET`) | **Implemented** (`GoldenHomeCollector`) |
| remax.gr | 200 homepage (121 KB, 11 prices, `/property/<id>-polisi-…` links) | yes on the homepage; the sale search path was not found in this round (`/poliseis-katoikies/…` and `/pwliseis-katoikies/…` → 404) | none seen | allowed (disallows `/backend.php`, `/ftp`, `/property/createPDF`) | Reachable — next candidate; needs the sale search URL (try the `/search/` form or the `xml_sitemaps/el` index) |
| era.gr | 200 homepage (WordPress, 59 KB) | no — listings load via `admin-ajax` | WP AJAX endpoint, not probed | allowed (`/wp-admin/` only) | Not implemented: listings are JS/AJAX; would need the AJAX call reverse-engineered |
| spitogatos.gr | **403** (919-byte block page) on home and search | — | — | robots.txt itself 403 | Blocked (WAF). Existing FlareSolverr path only |
| indomio.gr | **403** (770-byte block page) on home and search | — | — | readable; disallows `/search-list`, `/search-map`, `*idmacroarea=`, `/dettaglio.php` | Blocked (WAF). Existing FlareSolverr path only |
| spiti24.gr | **403** on home and robots.txt | — | — | unreadable (403) | Blocked |
| plot.gr | **403** on home and robots.txt | — | — | unreadable (403) | Blocked |
| tospitimou.gr | **403** on home and robots.txt | — | — | unreadable (403) | Blocked |
| xrysi-eukairia.gr | DNS does not resolve | — | — | — | Gone (the brand now lives inside XE.gr, which we already scrape) |
| noikaki.gr | 200 homepage (85 KB) | no listings on the homepage | has `/api/` | **`Disallow: /search`** and `/api/` | Not scraped — robots.txt forbids the search path. It is an aggregator anyway: its sources are the portals above |

Already live before this survey: **XE.gr** (server-rendered HTML) and **Green-Acres**
(server-rendered HTML, small inventory: 193 listings in the DB on 2026-10-31).

## Recommendation

1. **Golden Home — done.** Plain HTML, every field the comparables and twins logic needs is
   on the card (no detail-page visits), per-area URLs for all 15 weekly areas, ~100 sale
   listings in Χολαργός alone. Off-plan flats show a future build year on the card; the
   collector flags those `is_unfinished` so they are never passed off as new builds.
2. **RE/MAX — next.** Reachable and server-rendered; one more probe round to find the sale
   search URL (`diag/sources_probe.py --only remax --links --grep …`).
3. Spitogatos / Indomio / spiti24 / plot / tospitimou answer 403 to a datacenter client.
   Only the optional self-hosted FlareSolverr path (already in `base.py`) can reach the first
   two; we do not run it by default and add no paid proxy.
4. noikaki.gr: do not scrape (robots.txt). ERA: AJAX only; low priority.

## How it is wired

- `SOURCES` env (comma-separated `Listing.source` names) picks the plain-HTTP collectors:
  `SOURCES=xe,greenacres,goldenhome`. **Unset = `xe,greenacres`, i.e. unchanged
  production behaviour**; the coordinator flips the default after a verified run (add
  `SOURCES` to `daily.yml`'s collect step, or change `DEFAULT_SOURCES`). Unknown names are
  logged and ignored.
- Each collector scrapes only the run's municipality (same contract as XE), politely
  (`SCRAPE_REQUEST_MIN_S`–`MAX_S` between pages), fail-soft per card and per page.
- Every stored listing keeps `source`; the UI dict already carries it
  (`ui/queries.py: "source"`). Display names: `collectors.SOURCE_LABELS`
  (`goldenhome` → «Golden Home»).
- Cross-portal duplicates: Golden Home areas are rewritten to XE's form
  («Χολαργός (Φανερωμένη)»), titles to «Διαμέρισμα 72 τ.μ.», floors through the same
  `parse_floor` mapping, so `market_intel.twins` (same municipality, m², floor, year, price
  ±10 %) groups an XE and a Golden Home listing of one flat. Test:
  `tests/test_goldenhome.py::test_xe_and_golden_home_listing_of_one_flat_are_twins`.

## Live smoke from the runner

`scripts/smoke_sources.py --area Cholargos` with `SOURCES=xe,goldenhome`, into a throwaway
SQLite DB (`diag-sources.yml`, step "Smoke the collectors"):

Run 41220363373 (2026-10-31, after the storage fix below):

| | XE.gr | Golden Home |
|---|---|---|
| cards read | 11 pages (page 12 rate-limited, as usual) | 68 cards over 3 pages |
| raw → normalized | 374 → 374 | 36 → 36 (in the 90–450 k € / ≥ 40 τ.μ. band; air rights dropped) |
| stored | 374 | 36 |
| price / m² / floor / year / bedrooms / area / photos | 374 / 374 / 356 / 334 / 363 / 374 / 0 (card only) | 36 / 36 / 36 / 35 / 36 / 36 / 36 |
| flagged under construction | 64 | 1 (future build year) |

**38 listings** (both sides counted) have a twin on the other portal under
`market_intel.twins`.

Finding fixed on the way: the pipeline's fuzzy `dedup` (m² ±3, price ±5 %, any shared area
word, no floor/year) used to *drop* the non-canonical copy before storage. On the first smoke
(run 41219031909) it threw away 23 of 36 Golden Home listings, many of them different flats
that only shared «Χολαργός». `pipeline.run` now stores every portal's listing; dedup only
decides which copy counts once in the market stats, and the UI groups copies with the stricter
twins rule.
