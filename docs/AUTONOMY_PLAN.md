# Plan to evaluate: a much more independent agent

Goal: let this agent **operate and maintain the project on its own** — observe the live
system, decide, act, verify, and bother you only when it needs a decision. Everything
proposed here is **free**.

---

## 1. Where we are (honest evaluation)

| Layer | State | Notes |
|---|---|---|
| **Application** | 🟢 Mature | Scraper (XE, browser-free, polite/retry/cache), pipeline, scoring, Postgres, dashboard, alerts, health, work queue/workers, FlareSolverr path. 18 modules, **91 tests**, lint clean. |
| **Deploy / ops** | 🟡 Improving | Oracle cloud-init + **self-healing** reconcile/auto-update, Caddy HTTPS, compose profiles. Config drift fixed. But single datacenter IP (throttle risk) and **hosting still undecided** (Oracle vs old PC vs Streamlit Cloud+Neon). |
| **Agent toolkit** | 🟡 Early | 22 skills (8 project + 14 superpowers), 3 MCP servers (postgres/playwright/fetch), CLAUDE.md, plugins doc. Good for a *human-driven* session. |
| **Observability** | 🔴 Weak | The agent **can't see live state** — last session it had to ask you to paste logs. Health output goes only to logs/Telegram. **No CI.** No uptime check. No metrics the agent can read. |
| **Autonomy loop** | 🔴 Absent | The agent acts **only when you prompt**. No scheduling, no event triggers, no self-escalation, no durable cross-session memory of decisions. |

**The single biggest gap is the autonomy loop**: observe → decide → act → verify →
escalate, on a schedule, without you. The app is ready; the agent's *operating
capabilities* are not.

---

## 2. What "independent" means (capability model + target)

| Capability | Now | Target |
|---|---|---|
| **Observe** live system | ❌ asks you | DB (read-only), health, dashboard-uptime, CI status — all readable by the agent |
| **Triggered** without you | ❌ prompt-only | scheduled ops runs + event-driven (CI/PR, health alerts) |
| **Decide** (runbooks) | 🟡 `triage-scraper-health` only | full runbooks for the common ops |
| **Act** safely | 🟡 manual gate + auto-deploy | branch → verify → merge → auto-deploy autonomously for *low-risk* changes |
| **Verify** | 🟢 tests/gate | + post-deploy smoke |
| **Escalate** to you | ❌ | notify only when blocked / a decision is needed |
| **Memory** across sessions | 🟡 repo + CLAUDE.md | an agent-maintained ops log + a health table |

---

## 3. Tool-expansion plan (phased, all free)

### Phase A — Observability (so the agent can SEE) — *do first*
- **Live DB read**: wire the already-configured `postgres` MCP to the chosen host's DB
  (read-only). Lets the agent query listings/health/jobs directly.
- **CI**: add a **GitHub Actions** workflow (free) running the gate (pytest + ruff +
  black) on every push/PR. The agent reads pass/fail via the GitHub MCP — a real signal.
- **Health as data**: write each healthcheck report to a `health_report` table (and/or
  open a GitHub issue on ERROR), so state is durable and the agent can read it.
- **Uptime**: a tiny `scripts/uptime.py` (or the `fetch` MCP) that GETs the dashboard URL.

### Phase B — Triggers (so the agent ACTS without you)
- **Scheduled ops session**: a daily agent run that executes `triage-scraper-health` +
  `holargos-verify`, fixes what it can, escalates the rest. Mechanism options in §4.
- **Event-driven**: subscribe to PR/CI activity so the agent auto-fixes failing CI and
  answers review comments (the harness already supports PR-activity subscriptions).

### Phase C — Decision runbooks (new skills)
- `autonomous-ops` — the daily loop (observe → triage → fix → verify → escalate).
- `self-deploy-safely` — branch → gate → merge, with a guardrail allow-list.
- `weekly-review` — data-quality sweep, coverage gaps, dependency bumps.

### Phase D — Escalation (notify only when needed)
- The agent messages **you** via the project's existing Telegram (`alerts.send_alert`)
  — only on blocked decisions, repeated failures, or risky changes. Quiet otherwise.

### Phase E — Memory + guardrails
- Agent-maintained `docs/OPS_LOG.md` + the `health_report` table = state across the
  ephemeral containers.
- **Guardrail allow-list** (in CLAUDE.md + a hook): what the agent may do alone
  (fix selectors, add coverage, kick CI, bump patch deps) vs. what needs your sign-off
  (schema/topology changes, secrets, anything spend-related).

### (Optional) More MCP servers to evaluate
- **Telegram MCP** — agent ↔ you messaging (or just reuse the project's Telegram).
- **Sentry/Logflare-style** — only if we add error tracking later. Skip for now.
- We deliberately **don't** add servers without a job (kept postgres/playwright/fetch).

---

## 4. Decisions for you to evaluate

1. **Hosting first — it gates everything.** The agent can only watch a *stable* live
   system. Pick: (a) old PC scraper + Neon + Streamlit Cloud [recommended], (b) keep
   Oracle, (c) Railway. Observability (Phase A) is wired to whichever you choose.
2. **How much autonomy?**
   - *Watcher* — observe + report only, never changes code.
   - *Auto-fix + escalate* [recommended] — fixes low-risk (selectors, CI, coverage),
     escalates the rest.
   - *Full self-deploy* — also merges + deploys low-risk changes itself.
3. **Trigger mechanism (free):** GitHub Actions-invoked agent runs · Claude Code
   scheduled sessions · a host cron that opens issues the agent then handles. Depends on
   what you'll keep running.
4. **Notification channel:** reuse the project Telegram [simplest] vs a separate channel.
5. **Guardrails:** confirm the allow-list of autonomous vs sign-off actions.

---

## 5. Suggested order (once you've answered §4)

1. Decide hosting → 2. Phase A (CI + DB read + health-as-data) → 3. Phase E guardrails →
4. Phase C runbooks → 5. Phase B triggers → 6. Phase D escalation.

CI + guardrails come early on purpose: the agent should be *observable and bounded*
before it's *triggered and acting*.
