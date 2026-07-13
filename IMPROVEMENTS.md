# Holargos Property Scout — Improvement Backlog (50)

Living backlog the **improvement-loop** skill grinds through autonomously. Each item has a
theme, a rough impact (★1–5 on sellability), and effort (S/M/L). "Data" impact means it
raises what the tool actually *knows*; "Trust" means it stops the tool overstating; "Value"
means new decision capability a buyer pays for. Status: ☐ todo · ◐ partial · ✅ done.

Priority rule the loop uses: **highest (impact ÷ effort), skipping anything blocked by data
we can't get** (sold prices, owner phone numbers) — those are go-to-market, not code.

## A. Data depth & coverage — the biggest lever
1. ✅ Flag detail-page coordinates as `location_precision="exact"` (was silently left approx). ★4 S
2. ✅ Daily operator (scripts/daily.py) enriches + refreshes rent + rescores + alerts. ★5 S
3. ☐ Retry the ~12 rate-limited/blocked areas + finish the full 37-area sweep. ★4 M
4. ✅ Rental sweep per region → real €/m²/month comps (rent now 100% real). ★5 M
5. ☐ Parse street address from detail JSON-LD → geocode → sub-listing precision. ★3 M
6. ☐ Extract `image_url` for all detailed listings (card carousel / og:image). ★2 S
7. ☐ Parse more fields: heating type, parking, balcony m², orientation, condition. ★3 M
8. ☐ Second portal (Spitogatos/Indomio) via self-hosted FlareSolverr. ★5 L
9. ☐ Green-Acres deeper pagination + more areas. ★2 S
10. ☐ Relisting detection via `datePosted` reset across runs (distress tell / moat). ★4 M
11. ✅ Cross-source dedup blocking key (O(n²)→~linear). ★2 M
12. ☐ Clean price-cut capture: daily diff → `price_history` so `num_cuts` is real. ★4 M
13. ☐ Capture active→gone transitions cleanly to feed liquidity (already recorded; validate). ★3 S
14. ☐ Deduplicate/junk-filter spam & agent-farm duplicate listings. ★3 M

## B. Valuation & scoring quality
15. ✅ Ridge regression stabilises small-area hedonic fits. ★3 M
16. ☐ Bootstrap prediction intervals (honest ± per listing, not one area band). ★3 M
17. ✅ Recency-weighted comps (120-day half-life) in the fit. ★3 M
18. ✅ €/m² outlier trimming (MAD band) before fitting. ★3 S
19. ◐ Rent model per area × size-band (area+hood medians live; size-band TODO). ★4 M
20. ☐ Calibrate `energy_liability_floor` / band ceilings from the data, not hand-set. ★2 M
21. ☐ "Own-use" vs "investment" scoring modes (different weightings). ★2 M
22. ✅ Net-yield sensitivity range (pessimistic/base/optimistic). ★3 S
23. ☐ Detect & down-rank listings whose area/price/energy are internally inconsistent. ★2 S
24. ✅ Ranking tie-breaks toward complete data; per-listing confidence score. ★4 S

## C. Decision tools (value a buyer pays for)
25. ◐ Mortgage cash-on-cash one-liner (done) → interactive slider (deposit/rate/term). ★3 S
26. ✅ Break-even rent + unlevered payback per listing. ★3 S
27. ☐ Sensitivity table (rate × vacancy → net yield / cashflow). ★2 M
28. ☐ Portfolio compare view (shortlist several, rank side-by-side). ★3 M
29. ☐ Neighborhood price-trend index over time (from `price_history`). ★3 M
30. ✅ Rent-vs-buy monthly calculator. ★2 M
31. ✅ Greek rental-income tax (progressive) surfaced on the detail page. ★2 S
32. ✅ Renovation-ROI estimator (capex vs rent uplift), pairs with EPBD. ★3 M
33. ✅ Exit-value projection from the area €/m² trend. ★2 M
34. ☐ One-page PDF per listing (the deliverable an agent hands a client). ★3 M

## D. Product / UX / trust
35. ✅ Per-listing "limited data — missing: …" badge. ★3 S
36. ✅ Coverage/freshness panel per region. ★2 S
37. ◐ Alerts wired into the daily operator (fires when a sink is configured). ★4 M
38. ✅ Saved searches (table + CRUD + matching + UI page + alerts). ★4 M
39. ◐ Score exposes signal_known (real vs unknown); UI breakdown TODO. ★3 S
40. ☐ Per-field source attribution (scraped vs imputed) on the detail page. ★2 S
41. ☐ Strategy/onboarding wizard for a new investor. ★2 M
42. ☐ Mobile-responsive card grid. ★2 M
43. ◐ Watchlist price-cut section in the digest. ★3 S
44. ☐ Multi-user auth (SaaS multi-tenant) — only once single-user value is proven. ★2 L

## E. Infra / ops / reliability / autonomy
45. ◐ Adaptive throttle (results done) → extend to detail fetches + persist learned rate. ★3 S
46. ✅ Scrape-health monitor (stale/thin areas) — scrape_health.py. ★3 S
47. ☐ Incremental scrape (skip unchanged listings by hash) to go deeper cheaper. ★3 M
48. ☐ Real migrations framework (Alembic) instead of ad-hoc `_ensure_columns`. ★2 M
49. ✅ CI (.github/workflows/ci.yml) runs ruff+black+pytest on push. ★3 S
50. ◐ Daily run emits metrics (listings, complete %, top gap). ★2 M

---
The **data-quality-audit** skill measures A/D state each cycle; the **improvement-loop**
skill picks the next items by (impact ÷ effort), implements, gates, and re-scores via
**sellability-review** — the self-improvement engine.
