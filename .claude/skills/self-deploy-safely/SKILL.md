# self-deploy-safely — branch → gate → CI → merge → verify autodeploy

Use this skill whenever a fix is ready to ship. It gates on CI, ensures the change
is in the autonomous allow-list, and verifies the Oracle instance picked it up.

## When to invoke
After committing a fix on the feature branch and confirming the local gate passes.

---

## Step 0 — Guardrail check (mandatory)

Before touching anything, confirm the change is in the autonomous allow-list
(see `autonomous-ops` Step 3).

**If the change is NOT in the allow-list: STOP.** Send a Telegram alert explaining
what the change is and why it needs sign-off. Do not push to main.

---

## Step 1 — Local gate

```bash
cd /root/holargos && . .venv/bin/activate
python -m pytest -q
ruff check src/ tests/ scripts/
black --check src/ tests/ scripts/
```

All three must pass. Fix any failures before continuing.

---

## Step 2 — Push feature branch and wait for CI

```bash
git push -u origin <branch-name>
```

Find the CI run:
```
mcp__github__actions_list → owner=am015-dev, repo=test, branch=<branch-name>
```

Poll until `status: completed`:
```
mcp__github__get_check_run → check_run_id=<id>
```

If CI fails: diagnose with `mcp__github__get_job_logs`, fix, push again, repeat.
Do NOT merge a branch with a failing CI run.

---

## Step 3 — Merge to main (CI green only)

Fast-forward merge:
```bash
git checkout main
git merge --ff-only <branch-name>
git push -u origin main
```

Or via GitHub MCP if a PR exists:
```
mcp__github__merge_pull_request → merge_method: "merge"
```

---

## Step 4 — Verify Oracle autodeploy

The instance polls `origin/main` every 5 min via `deploy/auto-update.sh`.
Wait 6–10 min, then confirm:

```sql
-- Agent-readable via postgres MCP
SELECT checked_at, status
FROM health_report
ORDER BY checked_at DESC
LIMIT 1;
```

And check uptime:
```bash
python scripts/uptime.py
```

If the instance hasn't updated after 15 min, check the auto-update log:
```
tail -20 /var/log/holargos-update.log   # via Oracle Serial Console or Run Command
```

Common cause: GitHub token expired in `/opt/holargos/.git/config` → escalate.

---

## Step 5 — Log it

Add a line to the current day's `docs/OPS_LOG.md` entry:
```
- Deployed: <branch> → main — <one-line description of the fix>
```
