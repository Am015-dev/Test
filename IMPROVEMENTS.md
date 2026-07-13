# Holargos Property Scout — Improvement Backlog (50)

Living backlog the **improvement-loop** skill grinds through autonomously. Each item has a
theme, a rough impact (★1–5 on sellability), and effort (S/M/L). "Data" impact means it
raises what the tool actually *knows*; "Trust" means it stops the tool overstating; "Value"
means new decision capability a buyer pays for. Status: ☐ todo · ◐ partial · ✅ done.

Priority rule the loop uses: **highest (impact ÷ effort), skipping anything blocked by data
we can't get** (sold prices, owner phone numbers) — those are go-to-market, not code.

## A. Data depth & coverage — the biggest lever
1. ✅ Flag detail-page coordinates as `location_precision="exact"` (was silently left approx). ★4 S
2. ☐ Cron `enrich_details.py` daily (recover energy/year/coords for the top-scored backlog). ★5 S
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
15. ☐ Ridge/regularized regression to stabilise small-area hedonic fits. ★3 M
16. ☐ Bootstrap prediction intervals (honest ± per listing, not one area band). ★3 M
17. ☐ Recency-weight comps (a 200-day-old asking is weaker evidence). ★3 M
18. ☐ Outlier detection on price/area before fitting (garbage in → garbage fit). ★3 S
19. ◐ Rent model per area × size-band (area+hood medians live; size-band TODO). ★4 M
20. ☐ Calibrate `energy_liability_floor` / band ceilings from the data, not hand-set. ★2 M
21. ☐ "Own-use" vs "investment" scoring modes (different weightings). ★2 M
22. ☐ Net-yield sensitivity range (vacancy/rate/cost bands), not a point figure. ★3 S
23. ☐ Detect & down-rank listings whose area/price/energy are internally inconsistent. ★2 S
24. ☐ Confidence-weighted ranking: a complete listing outranks a same-score card-only one. ★4 S

## C. Decision tools (value a buyer pays for)
25. ◐ Mortgage cash-on-cash one-liner (done) → interactive slider (deposit/rate/term). ★3 S
26. ☐ Break-even & payback-period per listing. ★3 S
27. ☐ Sensitivity table (rate × vacancy → net yield / cashflow). ★2 M
28. ☐ Portfolio compare view (shortlist several, rank side-by-side). ★3 M
29. ☐ Neighborhood price-trend index over time (from `price_history`). ★3 M
30. ☐ Rent-vs-buy calculator per area. ★2 M
31. ☐ Explicit Greek tax breakdown (ENFIA, rental income tax) in the net figure. ★2 S
32. ☐ Renovation-ROI estimator (pairs with the EPBD capex flag). ★3 M
33. ☐ Exit-value projection from area trend + liquidity. ★2 M
34. ☐ One-page PDF per listing (the deliverable an agent hands a client). ★3 M

## D. Product / UX / trust
35. ✅ Per-listing "limited data — missing: …" badge. ★3 S
36. ✅ Coverage/freshness panel per region. ★2 S
37. ☐ Alerts (email/telegram) actually wired + a send test in CI. ★4 M
38. ☐ Saved searches persisted in a table (area/budget/yield mandate). ★4 M
39. ☐ Full "why this score" per-listing breakdown (known vs unknown signals). ★3 S
40. ☐ Per-field source attribution (scraped vs imputed) on the detail page. ★2 S
41. ☐ Strategy/onboarding wizard for a new investor. ★2 M
42. ☐ Mobile-responsive card grid. ★2 M
43. ☐ Watchlist with price-drop notifications. ★3 S
44. ☐ Multi-user auth (SaaS multi-tenant) — only once single-user value is proven. ★2 L

## E. Infra / ops / reliability / autonomy
45. ◐ Adaptive throttle (results done) → extend to detail fetches + persist learned rate. ★3 S
46. ☐ Scrape-health monitor + alert when an area silently returns nothing. ★3 S
47. ☐ Incremental scrape (skip unchanged listings by hash) to go deeper cheaper. ★3 M
48. ☐ Real migrations framework (Alembic) instead of ad-hoc `_ensure_columns`. ★2 M
49. ☐ CI (GitHub Actions) running the gate (pytest + ruff + black) on every push. ★3 S
50. ☐ Structured logging + run metrics (listings/hr, block rate) for observability. ★2 M

---
The **data-quality-audit** skill measures A/D state each cycle; the **improvement-loop**
skill picks the next items by (impact ÷ effort), implements, gates, and re-scores via
**sellability-review** — the self-improvement engine.
