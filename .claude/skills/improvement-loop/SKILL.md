---
name: improvement-loop
description: The autonomous self-improvement engine for Holargos Property Scout. Use when asked to "improve the product", "find and implement improvements", "make it more sellable", or to run unattended improvement cycles. Runs observe → prioritise → implement → gate → review → score → log, one small batch per cycle, respecting all project guardrails. The goal is autonomy: keep raising the sellability score without hand-holding, and stop honestly when returns diminish.
---

# Improvement loop — observe, fix the highest-ROI gap, prove it, repeat

The point is a *repeatable* cycle, not a one-off burst of 50 edits. Each cycle makes a
small, verified, committed improvement and records the new score, so progress compounds and
is auditable. Prefer three solid, tested changes over thirty unverified ones.

## The cycle (one batch per invocation)

1. **Observe.** Run the `data-quality-audit` skill. Note `complete_pct`, `top100_complete`,
   and `top_gap`. Read `IMPROVEMENTS.md` for the open backlog.
2. **Prioritise.** Pick 2–5 items maximising **impact ÷ effort**. Hard rules:
   - Skip anything blocked by data we can't get (sold prices, owner phone numbers) — those
     are go-to-market, not code. Say so; don't fake them.
   - Prefer the item the audit's `top_gap` points to — fixing the measured weakness beats a
     guess.
   - A correctness bug found mid-cycle jumps the queue.
3. **Plan.** State the batch and the expected measurable effect (e.g. "energy 33% → ~60%",
   "kills imputed-rent double-count"). Keep it short.
4. **Implement.** Make the changes. Keep functions pure and unit-testable where possible; put
   new logic in a module + a test, not only in the UI.
5. **Gate (blocking).** `python -m pytest -q` then `ruff check` and `black --check` over
   `src/ tests/ scripts/`. Green before commit — no exceptions.
6. **Review & score.** Run the `sellability-review` skill; record the new score, price band,
   and the 3 biggest remaining blockers. If a change didn't move a rubric line, say why.
7. **Log & commit.** Append a one-line entry to `IMPROVEMENTS.md` (mark items ✅/◐) and to a
   running `IMPROVEMENT_LOG.md` (date, batch, score before→after). Commit with the required
   trailers; push to the designated branch.
8. **Decide.** If the score moved and backlog remains, loop again. If two consecutive cycles
   fail to move the score, STOP and report honestly what's now blocking (usually data or
   go-to-market), rather than churning.

## Guardrails (never violate)

- **Free solutions only** — no paid APIs/services (no APIFY etc.).
- **Branch** `claude/holargos-property-scout-8yffib`; never push elsewhere. Do **not** open a
  PR unless explicitly asked.
- **Commit trailers** required: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  the `Claude-Session:` line. Never put the model identifier in commits/PRs/code/comments.
- **DB single-writer**: never rescore or write to the prod DB while a scrape/enrich holds a
  write session. Scraping cadence for XE detail pages ≥ 4 s (measured safe; faster → 403s).
- **Stop-and-flag** before: DB schema changes, `strategy.yaml` scoring changes, adding a new
  portal, or deleting data — implement only when the current task authorises it, and note it
  in the commit body.
- **Honesty over score**: never make the product claim precision it lacks to lift the number.
  A change that removes a false claim is a win even if the raw score dips.

## What "done for now" looks like

A committed, gated batch; an updated backlog + log; a fresh sellability score with the top
remaining blockers named. Then either loop or stop with an honest "the rest needs X" — where
X is usually sold-price data, a second portal, or weeks of accumulated time-series (the moat),
none of which more code can shortcut today.
