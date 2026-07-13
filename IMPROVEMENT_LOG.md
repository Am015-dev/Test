# Improvement Log

Running record of autonomous improvement cycles (newest first). Each entry: what shipped,
the data-quality / sellability delta, and the top remaining blockers.

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
