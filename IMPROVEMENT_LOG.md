# Improvement Log

Running record of autonomous improvement cycles (newest first). Each entry: what shipped,
the data-quality / sellability delta, and the top remaining blockers.

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
