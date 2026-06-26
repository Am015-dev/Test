# weekly-review — data-quality sweep, coverage gaps, dependency check

Run once a week (Sunday UTC morning works well) or when asked "do a weekly review".
Produces a short data-quality + ops report and executes any auto-fixable items.

---

## Step 1 — Data quality sweep

Run these queries via the postgres MCP:

```sql
-- Enrichment fill rates (missing metro / yield signals)
SELECT
    count(*) FILTER (WHERE metro_distance_m IS NULL) AS no_metro,
    count(*) FILTER (WHERE price_per_m2    IS NULL) AS no_ppqm,
    count(*) FILTER (WHERE gross_yield     IS NULL) AS no_yield,
    count(*) AS total
FROM listing WHERE status = 'active';

-- Price-cut velocity last 7 days
SELECT count(*) AS price_cuts
FROM price_history ph
WHERE ph.observed_at >= now() - interval '7 days'
  AND ph.price < (
      SELECT ph2.price FROM price_history ph2
      WHERE ph2.listing_id = ph.listing_id
        AND ph2.observed_at < ph.observed_at
      ORDER BY ph2.observed_at DESC LIMIT 1
  );

-- Active / gone churn
SELECT status, count(*) FROM listing GROUP BY status;

-- Dedup risk (same address + area + price across sources)
SELECT address, area_m2, price, count(*) AS n
FROM listing
WHERE status = 'active'
GROUP BY address, area_m2, price
HAVING count(*) > 1
LIMIT 20;
```

**Flag if:**
- > 20% active listings have `metro_distance_m IS NULL` → geocoding / OSRM broken
- Dedup query returns > 5 rows → cross-source dedup may need tuning
- Churn (gone / active ratio) > 50% → scraping instability

---

## Step 2 — Coverage gaps

Compare `strategy.yaml` `search.all_areas()` against the `areas_with_data` field
in the latest health report:
```sql
SELECT metrics
FROM health_report
ORDER BY checked_at DESC
LIMIT 1;
```
Any configured area NOT in `areas_with_data` in the last 48h needs investigation.

---

## Step 3 — Dependency check

```bash
pip list --outdated 2>/dev/null | grep -v Package | grep -v -
```

For each outdated package:
- Patch bump (x.y.Z → x.y.Z+1): update `pyproject.toml`, run the gate, use
  `self-deploy-safely` to ship. No sign-off needed.
- Minor or major bump: note it in OPS_LOG and send an escalation summary.

---

## Step 4 — Test coverage scan

```bash
python -m pytest -q --tb=no 2>&1 | tail -5
```

Check that the test count hasn’t dropped since last week.
List modules under `src/scout/` that have no matching test file:
```bash
for f in src/scout/*.py; do
    base=$(basename $f .py)
    [ -f "tests/test_${base}.py" ] || echo "untested: $base"
done
```

Flag uncovered modules as a backlog item (don’t add tests autonomously unless the
module is in the allow-list and the tests are trivial).

---

## Step 5 — Report

Append a `## YYYY-MM-DD Weekly Review` entry at the top of `docs/OPS_LOG.md`:

```
## YYYY-MM-DD Weekly Review
- Enrichment fill rates: metro=XX%, ppqm=XX%, yield=XX%
- Churn: XX active / XX gone
- Dedup risk: XX duplicate candidates
- Coverage gaps: [areas or "none"]
- Deps patched: [list or "none"]
- Deps needing sign-off: [list or "none"]
- Test count: NN (delta: +/-N vs last week)
- Uncovered modules: [list or "none"]
- Action items auto-fixed: [list or "none"]
- Escalated: yes — [reason] / no
```

For any sign-off items, send **one** consolidated Telegram alert listing them all
(don’t send a separate message per item).
