# autonomous-ops — daily observe → triage → fix → verify → escalate

The daily maintenance loop. Run this skill each morning after the scrape (07:00 UTC)
and healthcheck have fired. Observe the live system, triage issues, apply only
allow-listed fixes, verify, and escalate anything that needs a human decision.

## When to invoke
- After the daily scrape + healthcheck cron (07:00 UTC).
- Any time asked: "run the ops loop", "check the system status", "ops cycle".
- After a CI failure notification arrives.

---

## Step 1 — Observe

**Read the last 3 health reports** via the postgres MCP:
```sql
SELECT checked_at, status, issues, metrics
FROM health_report
ORDER BY checked_at DESC
LIMIT 3;
```

**Check CI** via GitHub MCP:
```
mcp__github__actions_list  →  owner=am015-dev, repo=test, branch=main
```
Get the latest run; if failed, load logs:
```
mcp__github__get_job_logs  →  run_id=<latest>
```

**Check uptime** (if DASHBOARD_URL is set on the host):
```bash
python scripts/uptime.py
```
Or use the fetch MCP to GET the dashboard URL directly.

**Record findings** in `docs/OPS_LOG.md` under a `## YYYY-MM-DD HH:MM UTC` heading.

---

## Step 2 — Triage

For each WARN / ERROR issue, classify it:

| Symptom | Classification | Next action |
|---|---|---|
| Data stale / all jobs returned 0 | IP block (all workers) | See §3 fix table; escalate if extra worker needed |
| One area returned 0, others OK | Partial block or area gone | Re-enqueue; watch next cycle; escalate if 3 consecutive |
| CI failing | Code bug or selector break | Read logs → fix if allow-listed; escalate if schema/arch |
| Dashboard unreachable (uptime fail) | Service down | Note; suggest `docker compose restart web`; escalate |
| Scrape jobs stuck in `running` past lease | Crashed worker | `requeue_stale()` is cron'd; check worker logs |
| `failed` jobs > 3 same area | Poison-pill / markup change | Run `repair-collector` skill |

---

## Step 3 — Fix

### Autonomous allow-list (no sign-off needed)
- CSS selector constant update in `src/scout/collectors/*.py`
- Fix a failing test that is clearly wrong (no prod-behaviour change)
- Patch-version dep bump in `pyproject.toml` (x.y.**Z** → x.y.**Z+1**)
- Add a missing `scripts/` entrypoint or logging call
- Re-enqueue failed jobs: `python scripts/enqueue.py`
- Document a finding in `docs/OPS_LOG.md`

### STOP and escalate (send Telegram alert first)
- DB schema changes (new column / table / index)
- `strategy.yaml` / scoring / hard-filter changes
- Secrets rotation or new env vars that affect production
- Adding a new portal source
- Topology changes (new Oracle instance, new port, new service)
- Anything that can delete or retire data
- Cost-affecting changes
- Same failure persists for ≥ 3 consecutive autonomous cycles

---

## Step 4 — Verify

After any code change:
```bash
cd /root/holargos && . .venv/bin/activate
python -m pytest -q
ruff check src/ tests/ scripts/
black --check src/ tests/ scripts/
```
If all pass: use the `self-deploy-safely` skill to push and merge.  
If tests fail: fix the test too before shipping.

---

## Step 5 — Escalate

When blocked, send a Telegram alert with exactly:
1. The specific issue (copy the health_report issue text)
2. What was tried
3. The decision or action needed from the owner

```python
from scout.alerts import send_alert
send_alert(
    "🆘 Holargos Agent blocked.\n"
    "Issue: <paste issue text>\n"
    "Tried: <what you did>\n"
    "Need: <specific decision or action>"
)
```

Always log the escalation in `docs/OPS_LOG.md`.

---

## OPS_LOG entry format

Append at the **top** of `docs/OPS_LOG.md`:

```
## YYYY-MM-DD HH:MM UTC
- Health: ok|warn|error  (from health_report table)
- CI: pass|fail|unknown
- Uptime: ok|fail|unchecked
- Actions taken: [list or "none"]
- Escalated: yes — [reason] / no
```
