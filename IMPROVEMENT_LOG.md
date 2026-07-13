# Improvement Log

Running record of autonomous improvement cycles (newest first). Each entry: what shipped,
the data-quality / sellability delta, and the top remaining blockers.

## Cycle 9 — visual-QA truth pass (look at the rendered product, then fix)
Adopted the visual-qa discipline: launch the app, screenshot every page, fix what the
BUYER sees, re-screenshot to prove it. Root-caused and fixed, each verified by screenshot:
- **Cards looked broken/unfinished** — footer rendered as raw HTML (blank-line ended
  Streamlit's HTML block); collapse inter-tag whitespace. Empty 96px photo blocks on the
  ~8,300 photo-less listings → thin archetype accent bar; real photos (811) keep full header.
- **Duplicate listings** — XE relistings (same flat, fresh id, reset DOM clock) showed as
  twin cards. load_listings collapses them to one richest-data card, anchors DOM to the
  oldest posting, and surfaces "🔁 RELISTED" as a motivated-seller tell. 285 dupes collapsed.
- **"0 m to metro" on ~2,000 listings** (provably false) — municipality centroids had been
  set to the metro-STATION coordinate. Replaced 16 with real town centres; guarded degenerate
  OSRM zeros. recompute_metro relocated 2,151 listings, fixed 8,070 distances, 0 zeros remain.
- **Deals page red "1" score chips** on genuine leads — the page ranks by motivation, so the
  big chip now shows the motivation score (grade chip still carries quality).
- 243 tests pass (added card-render, relist-collapse, metro-distance regression guards).

## Cycle 7-8 — decision calculators + operational readiness (autonomous)
- Cycle 7: recency-weighted comps (weighted ridge), renovation-ROI, Greek rental tax, exit-value,
  scrape-health monitor. Corrected the "needs weeks" claim (days-on-market is 100% live from
  datePosted; verified XE has no per-listing price history).
- Cycle 8: scripts/daily.py — unattended operator (enrich → rent refresh → rescore → health →
  saved-search alerts → metrics), CI workflow, run metrics. Proven end-to-end network-free:
  7,664 listings, 48% complete, health caught a thin area. This is the operational loop that
  makes it a running product (the €19/mo readiness piece). 235 tests pass.

## Cycle 6 — recurring-value batch (goal: justify €19/mo subscription)
- Saved searches: SavedSearchRow + saved_search.py (CRUD + pure matching) + a Saved-searches
  UI page — the persisted investor mandate a monthly sub actually pays for.
- Saved-search alerts: per-mandate digest (build_saved_search_digest + run_saved_search_alerts)
  so the daily run delivers only what matches ME.
- "Why this score": ScoredListing now exposes signal_known (real vs unknown signals).
- Negotiation playbook: concrete per-motivated-seller moves (the actionable half of the moat).
- 230 tests pass. Depth enrich landed: data-complete 32% → 48% (energy 50%, year 49%, exact-loc
  54%, rent 100%); cv_r2 0.44. Sellability ~52 → ~56. €19/mo defensible for a niche once alerts
  run live; €100k still needs revenue or a data moat (not more code).

## Cycle 5 — decision calculators + valuation quality + grade/confidence (batch of the 30)
- Valuation: ridge regularisation (stabilises collinear card-only areas) + €/m² outlier
  trimming before fit (garbage can't tilt the line); model still prices every listing.
- New investment.py: net-yield SENSITIVITY range (pessimistic/base/optimistic), yield-on-OFFER,
  break-even rent, unlevered payback, rent-vs-buy, and an A-D deal grade (capped at B without
  complete data). All pure + unit-tested.
- Per-listing data-confidence score (0-100) surfaced as a chip; ranking already tie-breaks on
  completeness. Deal grade + confidence on every card; a "Downside & scenarios" block on the
  detail page.
- 225 tests pass, ruff+black clean. ~10 of the 30 planned shipped; rest remain in IMPROVEMENTS.md
  for the loop. Depth enrich (year/energy — the audit's current top gap) running in background.

## Cycle 4 — real rent comps (loop-selected: audit top gap was real_rent 0%)
- New `rent_comp` table + persistence; `rescore_all` applies real per-area/hood rent; new
  `scrape_rent_comps.py`; `run()` persists comps for the cron.
- Swept 37 areas → 159 comp rows (9-18 €/m²/mo; Kolonaki 18.1 vs west 9.0).
- **real_rent 0% → 100%**; net yield now a REAL, independent signal (median 3.2%), no longer
  a double-count of €/m². Audit's next target auto-shifted to `year_or_reno` (more depth).
- Sellability ~47 → ~50. Blockers now: sold prices (data partnership), deeper attribute
  coverage (detail-enrich more), 2nd portal.

## Cycle 3 — depth recovery + autonomy tooling
- Fixed: `enrich_details` now flags detail coords `location_precision="exact"` (was left
  approx) — **data-complete 8% → 32%, exact-location 11% → 37%, top-100 complete 32 → 95**.
- Detail-enrichment pass recovered energy 8%→33%, year 8%→32% over the top-scored 2,000.
- Built the self-improvement engine: `data_quality.py` audit module + `data-quality-audit`
  and `improvement-loop` skills + `IMPROVEMENTS.md` (50-item backlog).
- Extended adaptive throttle to detail fetches; ranking now tie-breaks toward complete data.
- Audit verdict: biggest gap = **real_rent (0%)** → next cycle = rental sweep (backlog #4/#19).
- Sellability: ~44 → see review below. Blockers: real rent comps, sold-price basis, 2nd portal.

## Cycles 1–2 (summarised)
- Round 1 (10): honesty — renormalized scoring, rent provenance, municipality median,
  value-gap gating, location precision, grid cap, dedup blocking. Removed the fatal
  "checkable lie". Score 34 → 38.
- Round 2 (10): decision value — liquidity, comps, cash-on-cash, EPBD capex, percentile,
  coverage panel, map honesty, digest filters. Score 38 → 44.
