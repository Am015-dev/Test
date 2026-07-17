# Holargos Property Scout — Improvement Backlog (50, pass 2)

Fresh 50, grounded in the cycle-9/10 visual-QA observations (screenshots of every page) and
the data-quality audit (complete 48.7%, top100 76%, top_gap = year_or_reno). Impact ★1–5 on
sellability, effort S/M/L. Status: ☐ todo · ◐ partial · ✅ done · 🚫 blocked (go-to-market /
data we can't get — NOT code). Priority = impact ÷ effort, correctness bugs jump the queue.

## A. Data depth & coverage
1. ◐ Enrich top-scored incomplete listings (year/energy/coords) — batch of 200 running. ★5 M
2. ☐ Parse heating type + parking + floor-count from detail JSON-LD description. ★3 S
3. ☐ Extract balcony/veranda + storage (αποθήκη) flags from description. ★2 S
4. ☐ Parse condition (νεόδμητο / υπό κατασκευή / ανακαινισμένο) → `condition` field. ★3 S
5. ☐ Extract `image_url` (og:image) for all detailed listings. ★2 S
6. ☐ Street-address parse from JSON-LD → geocode → sub-listing precision. ★3 M
7. ◐ Relisting detection via datePosted reset (collapse shipped; cross-run tracking TODO). ★4 M
8. 🚫 Second portal (Spitogatos/Indomio) via self-hosted FlareSolverr — needs infra. ★5 L
9. ☐ Incremental scrape (skip unchanged by content hash) to go deeper cheaper. ★3 M
10. 🚫 Clean price-cut capture needs multiple daily runs (time, not code). ★4 M
11. ☐ Junk/agent-farm duplicate filter beyond same-flat relisting. ★3 M
12. ☐ Capture off-plan delivery year ("ΘΑ ΠΑΡΑΔΩΘΕΙ 2026") distinct from build year. ★2 S

## B. Valuation & scoring quality
13. ☐ Bootstrap prediction intervals per listing (honest ± not one area band). ★3 M
14. ◐ Rent model per area × size-band (studio/1BR/2BR/3BR+). ★4 M
15. ☐ Calibrate energy-liability floor + band ceilings from the data. ★2 M
16. ☐ Down-weight comps drawn from consistency-flagged listings. ★2 S
17. ☐ Own-use vs investment scoring modes (different weightings). ★2 M
18. ☐ Widen value-gap band (lower confidence) when a listing has consistency flags. ★2 S
19. ☐ Confidence-weighted value_gap: widen when few comps in the submarket. ★3 S
20. ☐ Surface per-area model R² on the listing (trust the number or not). ★3 S
21. ☐ Seasonality-adjust the days-on-market baseline. ★1 M
22. ✅ Cap yield as a signal when rent is imputed, not a comp. ★3 S

## C. Decision tools (value a buyer pays for)
23. ◐ Mortgage cash-on-cash: static line → interactive slider (deposit/rate/term). ★3 S
24. ☐ Sensitivity table (rate × vacancy → net yield / monthly cashflow). ★3 S
25. ☐ Portfolio compare view: shortlist N, rank side-by-side. ★3 M
26. 🚫 Neighborhood price-trend index needs accumulated history (time). ★3 M
27. ☐ One-page PDF per listing (the deliverable an agent hands a client). ★3 M
28. ✅ Rent-vs-buy monthly + break-even. ★2 M
29. ✅ Renovation-ROI estimator (capex vs rent uplift). ★3 M
30. ✅ Exit-value projection from area €/m² trend. ★2 M
31. ☐ "Comparable active listings" panel per listing (the comps behind the value). ★4 M
32. ☐ Affordability filter (net income → max affordable price). ★2 S
33. ☐ Total acquisition cost breakdown (transfer tax, notary, agent, legal). ★3 S

## D. Product / UX / trust
34. ✅ Internal-consistency "verify this" flags on cards. ★3 S
35. ☐ Per-field source attribution (scraped vs imputed) on the detail page. ★2 S
36. ☐ Mobile-responsive card grid (single column < 640px). ★2 S
37. ☐ Onboarding/strategy wizard for a new investor. ★2 M
38. ◐ Empty-state polish across pages (Today fallback shipped; others TODO). ★2 S
39. ☐ Sidebar filter simplification / grouping (currently long & dense). ★2 S
40. ☐ "Why this score" breakdown on card/detail (signal_known already exposed). ★3 S
41. ☐ Listing-detail redesign (hero, spec grid, finance block, comps). ★3 M
42. ◐ Watchlist price-cut section in the digest. ★3 S
43. ✅ Non-dwelling types (air rights/land/shops) excluded from scoring. ★3 S
44. ☐ Accessibility: colour contrast on chips, alt text, focus states. ★2 S

## E. Infra / ops / reliability / autonomy
45. ◐ Adaptive throttle persisted + extended to detail fetches. ★3 S
46. ☐ Debug page: audit-metrics panel (complete %, top_gap, per-field). ★2 S
47. ☐ Alembic migrations instead of ad-hoc `_ensure_columns`. ★2 M
48. ☐ CI: coverage gate + a headless screenshot smoke test. ★2 M
49. ◐ Daily run richer metrics + regression alert. ★2 M
50. ☐ Deployment doctor: freshness check that the daily pipeline actually ran. ★3 S

---
Done this pass so far: 22, 28, 29, 30, 34, 43 (✅). Blocked (go-to-market/time, not code):
8, 10, 26. The **improvement-loop** skill grinds the rest by impact ÷ effort.
