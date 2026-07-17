---
name: data-quality-audit
description: Measure what the product actually KNOWS — field completeness, per-region coverage, freshness, and how much the ranking rests on complete vs card-only data. Run this as the "observe" step before deciding what to improve, or whenever asked "how good is our data / coverage / completeness". Outputs a prioritised gap so the next work targets the biggest weakness, not a guess.
---

# Data-quality audit — observe before you improve

The product's honesty and its score both hinge on how much it really knows. This skill
measures that from the live DB and names the single biggest gap to close next.

## Run it

```bash
cd /root/holargos && python -c "from scout.data_quality import audit, format_report; print(format_report(audit()))"
```

For the full structured report (per-region, per-field), print `audit()` directly.

## Read the result

- **complete_pct** — share of listings with energy + year + exact location + real rent. This
  is the trustworthy core; the rest carry a "limited data" badge.
- **top100_complete** — of the highest-ranked 100, how many are fully known. If this is low,
  the ranking is being driven by card-only guesses — fix data before trusting the picks.
- **fields** — per-field completeness. The lowest one is `top_gap`.
- **regions** — coverage + `stale_days` per area; a large `stale_days` means that area needs
  a re-scrape.

## Turn it into action (feeds the improvement-loop)

Map the biggest gap to the backlog item in `IMPROVEMENTS.md`:

| Biggest gap | Do next |
|---|---|
| `real_rent` low (usually ~0%) | Backlog #4/#19 — rental sweep per region → real rent comps |
| `energy_class` / `year_or_reno` low | Backlog #2 — run `scripts/enrich_details.py` (safe 4-7 s cadence) on the top-scored incomplete |
| `exact_location` low | same detail-enrichment pass (it now sets `location_precision="exact"`) |
| a region with high `stale_days` or few listings | Backlog #3 — re-scrape / finish that area |

Guardrails: the detail-enrichment and scraping steps hold a long DB write session, so never
run a rescore or other DB write **while** a scrape/enrich is in flight (SQLite single-writer).
Keep the detail cadence ≥ 4 s (measured safe) to avoid XE 403s.
