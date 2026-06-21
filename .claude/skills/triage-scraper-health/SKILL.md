---
name: triage-scraper-health
description: Runbook for when the scraper healthcheck reports WARN or ERROR (stale data, every area returned zero / IP-blocked, some areas zero, jobs failed) or the daily digest stops arriving. Use to diagnose the root cause and decide the fix — more workers vs repair selectors vs config vs genuinely empty market. The first thing to do when an unsupervised session is paged about scraper health.
---

# Triage scraper health

`scripts/healthcheck.py` (`scout/health.py: check_health`) grades the system. Map the
report to a root cause and action.

## Get the current report

```bash
cd /root/holargos && . .venv/bin/activate && python scripts/healthcheck.py
```

The metrics that matter: `hours_since_refresh`, `areas_with_data`, `areas_returned_zero`,
`recent_jobs_failed`, `active_listings`.

## Decision table

| Symptom in report | Likely cause | Action |
|---|---|---|
| `ERROR: Data is stale` (hours_since_refresh > HEALTH_STALE_HOURS) AND a recent job exists | The cron isn't running, OR every scrape is blocked | Check the cron ran (`/var/log/holargos-daily.log` on the instance); if it ran but all zero, treat as the block row below |
| `ERROR: every job returned 0 listings` | The control VM's IP is rate-limited by XE on all areas | Confirm it's a block not markup: run `repair-collector` step 1. If block → add a worker on another Oracle Always-Free instance (`add-coverage-area` scale note); each new IP drains the same queue |
| `WARN: some areas returned 0` | That area's IP got throttled this run, or its geo id doesn't resolve | Re-run just that area (`run_for_area`); if it persistently returns 0, check `_resolve_place_id` for the name, and `repair-collector` step 1 to rule out markup |
| `ERROR: no active listings` / empty DB | Fresh DB never populated, or DATABASE_URL points at the wrong DB | Confirm DATABASE_URL; run `python scripts/enqueue.py && python scripts/worker.py` once |
| `WARN: N jobs failed` | A real exception in `run_for_area` (not a block — blocks return 0, not failure) | Read the job's `error` column and the log; this is usually a code bug → fix it, it won't self-heal |
| Stale but jobs look fine | Markup change making parse yield 0 stored while raw>0 | `repair-collector` |

## Key distinctions (don't misdiagnose)
- **Block vs markup**: a block returns a small/403 body with 0 cards; a markup change
  returns a large body with 0 cards (or cards with None fields). `repair-collector` step 1
  settles it. Churning selectors on a block wastes effort.
- **Zero vs failed**: a job that returned 0 listings is `done` with `listings_found=0`
  (block/empty market). A `failed` job hit a real exception (code bug) — these don't
  self-heal and need a fix.
- `listings_found` is the pre-scoring (deduped) count, so a scoring bug shows up as
  `failed` jobs / errors, not as a false "0 listings = blocked".

## After fixing
Re-run `scripts/healthcheck.py`; expect `ok`. If you changed code, run `holargos-verify`.
