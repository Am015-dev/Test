# Improvement Log

Running record of autonomous improvement cycles (newest first). Each entry: what shipped,
the data-quality / sellability delta, and the top remaining blockers.

## Cycle 16 — full-page coherence sweep (screenshot every page, fix noise)
Screenshotted and critically reviewed EVERY page; fixed the clutter/consistency issues found,
added zero features:
- KPI header: dropped outlier "cheapest €/m²" (always a 330 m² fixer-upper) → median net yield.
- Fair-value banner: 5-line yellow wall → one-line headline + "how to read" expander.
- Neighborhoods "Median yield" → "Median gross yield" (it's gross; app emphasises net).
- Strategy: metro-distance input was mislabelled a "Hard filter" — it's a signal now; relabelled
  as the "near metro" threshold with a help note.
- Verified all 5 detail-page tabs render (Returns/Costs&risk/Sensitivity/Score&comps/Details),
  0 exceptions. Deals / Saved searches / Strategy confirmed clean, left as-is. 336 tests green.

## Cycle 15 — RESTRAINT: consolidate, stop piling on (user: "very bad result")
Honest lesson: the last few cycles kept ADDING blocks and the detail page became a
15-section single-scroll wall — my feature-adding made the product WORSE to use.
Corrected course toward coherence, not more features:
- Detail page → verdict-first header (grade · scorecard · net yield · vs-model gap ·
  strategy tags · offer thesis) + 5 tabs (Returns · Costs & risk · Sensitivity · Score &
  comps · Details). Same info, a fraction of the scroll, reads as a tool not a data dump.
- Card → dropped OPPORTUNITY/NEGOTIABLE badges that duplicate the Underpriced/Motivated
  strategy tags. Less noise per card.
No new features this cycle — deliberately. 336 tests green; screenshot-verified.

## Cycle 14 — implemented the REST of the GitHub-project ideas (5 features)
Second batch from the deal-analyzer study, all shipped (5 pure modules, 40 tests, 336 green,
every one screenshot-verified rendering):
- deal_scorecard.py — transparent 14-point Athens-calibrated scorecard on the detail page
  (Strong/Fair/Pass), every check with points + honest note; unknowns score 0.
- projection.py — 5-year total-return (four pillars) block.
- strategy_fit.py — card pills + sidebar filter (Cashflow/Value-add/Underpriced/Motivated/Prime).
- sensitivity.py — rent-change and price-change what-if tables added.
- listing_report.py — printable HTML one-pager download (the agent deliverable, backlog #27).
Kept honest: still no US 1%/50%/70% rules, no IRS depreciation. The scorecard is a good
anti-inflation counterweight — it openly shows a "31% under model" flat scoring only 7/14
(Fair) because its DSCR/break-even are weak.

## Cycle 13 — ideas from similar GitHub projects (adapted honestly to Athens)
Studied open-source deal analyzers (berkcankapusuzoglu/Rental-Property-Deal-Analyzer,
crankstorn/real-estate-analysis, DealCheck-style tools). Took the metrics investors expect
BY NAME and adapted thresholds to the Greek market instead of copying US rules:
- metrics.py: cap rate, GRM, DSCR, break-even occupancy on the same Greek cost model, each
  with an Athens-calibrated good/ok/weak verdict. Surfaced as a colour-coded detail block.
  Explicitly rejected the US "1% / 50% rules" (at ~5% Athens yields they fail on everything).
- Compare page (backlog #25): shortlist 2–4 flats side-by-side on the deciding numbers.
- Honest payoff: DSCR/break-even expose downside a "31% under fair value" flat hides (rent
  may not cover the mortgage — DSCR 0.91). 296 tests green; both screenshot-verified.
Not adopted (US-specific or blocked): 1%/50%/70% rules, IRS depreciation tax benefit,
Freddie-Mac rate auto-fill; PDF export deferred (backlog #27).

## Cycle 12 — anti-inflation: honest grades/badges (user: "all the scores are inflated")
The user was right. The valuation model's out-of-sample band is ±42%, but value gaps were
tiny (p50=11%, p90=32% — nearly all WITHIN the noise) and still drove a green "+11% vs model
value" badge, the undervaluation score, and 26 grade-A "deals". Puffery.
- Significance gate: value_gap_pct is now kept only when the price clears the model's own ±1σ
  band; within-noise gaps drop to None. deal_grade thresholds raised (score 60/40, yield 4.5%).
- Effect after rescore: "undervalued" claims **3,069 → 1,053**, grade **A 26 → 6**, **B 260 → 87**.
  Cards now show a "vs model value" badge ONLY on genuinely beyond-noise gaps (e.g. +30%); the
  rest show just net yield / days-on-market / metro. 290 tests green.
- **Revised sellability: ~33/100** (down from the ~40 I gave last pass — that number was itself
  a bit generous). The honest read: the "find undervalued flats" claim is the WEAK part (asking-
  based, mostly noise); the tool's real, defensible value is the **motivated-seller signals**
  (days-on-market, relistings — real and live) plus the **decision math** (net yield after Greek
  tax, total acquisition cost, sensitivity). Price it on those, not on an "AI valuation".

## Cycle 11 — improvement pass (50 identified, decision tools shipped) + sellability score
Ran the redefined improvement-loop: identified 50 improvements (IMPROVEMENTS.md pass 2),
built a task list, implemented a batch via 5 parallel subagents + integration, verified by
tests + screenshots, then scored the price.

**Shipped (all gated, screenshot-verified, 289 tests green):**
- 4 new pure decision modules on the listing-detail page: `acquisition.py` (total cash-in
  = price + Greek transfer tax/notary/registry/legal/agent), `sensitivity.py` (rate×vacancy
  net-yield grid), `comps_panel.py` (softer comps so the section is never empty),
  `score_explain.py` (plain-language 🟢/🔴/⚪ "why this score"). 39 new unit tests.
- Affordability filter (income → max mortgage-supported price); freshness doctor (warns when
  data ≥3 days old); Debug data-quality audit panel; mobile-responsive card grid.
- Detail parser (xe.py) now extracts heating/parking/storage/condition/off-plan year —
  parsing only; persistence deferred (needs a schema change, flagged not done).
- Data: enriched 200 top-scored incomplete listings → coords +182, energy +11, year +11.
  Honest delta: complete 48.7%→48.8%, year_or_reno 49.6%→49.7% — barely moved, because the
  batch was small and those rows lacked coords, not year. Moving the top_gap needs a
  sustained production enrichment run (1,500+/day over days) = ops/time, NOT a code fix.

**Sellability score: ~40/100** (up from ~25 when the UI was broken, ~52 self-claimed before
the visual-QA truth pass). Tier: **prosumer-adjacent, currently hobby**. Realistic price:
- €19/mo: *plausible for a niche (a buyer's-agent doing lead-gen off the CSV export) ONCE the
  daily pipeline + alerts demonstrably run live and coverage broadens* — not for a general
  buyer today.
- €100k one-off: **no** — needs revenue/users or a data moat, not more code.

Why the price is capped (most damaging first):
1. **Valuation is relative to ASKING prices, not sold prices** (Greek sold data isn't public)
   with out-of-sample R²=0.45 / ±42% bands — wider than the ~10–20% edge it claims to find.
   The tool is now honest about this, but honesty doesn't make the signal reliable.
2. **Single portal (XE) + 49% depth** — partial market slice, half the listings card-only.
3. **Not proven live** — data is 2 days old; the daily-refresh premise is unverified in prod.
4. **Low defensibility** — a competent dev rebuilds the scraper+scoring in ~2 weeks.
The genuinely strong parts: motivated-seller signals (days-on-market, relistings) are REAL
and live now, and the decision math (net yield after Greek tax, acquisition cost, sensitivity)
is solid. What would 10× willingness-to-pay: sold-price data (or a defensible proxy),
a proven always-on daily pipeline with alerts, and a second portal for full coverage.

## Cycle 10 — visual-QA, every remaining page
Screenshotted Map, Today, Neighborhoods, Watchlist and fixed what the buyer sees:
- **Map was a sea of red** (absolute scores are low: p50=14, max=70, so the absolute
  red→green scale painted everything red). Now colours pins by percentile rank within the
  view → a real heatmap of relatively-better listings; legend says so.
- **Non-dwellings scored as investments** — air rights ("αέρας"), land, shops, parking have
  no comparable €/m². Hard-excluded by title; keeps houses/maisonettes/buildings.
- **Today was blank on a quiet day** → falls back to current top-ranked picks.
- Neighborhoods table + Watchlist empty state reviewed: clean, kept as-is. 245 tests green.

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
