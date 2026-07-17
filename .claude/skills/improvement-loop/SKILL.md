---
name: improvement-loop
description: The autonomous self-improvement engine for Holargos Property Scout. Use when asked to "improve the product", "run the improvement skill", "find and implement improvements", or "make it more sellable". One invocation = one full pass that IDENTIFIES 50 concrete improvements, turns them into a planned task list, IMPLEMENTS them in gated batches, VERIFIES the result (tests + screenshots), then CRITIQUES the product and scores its market price. The goal is autonomy toward a sellable product (€19/mo or €100k), stopping honestly when what remains needs data or go-to-market, not code.
---

# Improvement loop — 50 improvements, plan, implement, verify, critique, price

One invocation runs the whole pass below. Volume is the point (find 50), but so is honesty:
a shipped, tested improvement counts; a claimed one does not. Never fake data the product
can't get, and never let the product claim precision it lacks to lift a score.

## The pass (do all six phases, in order)

1. **Observe.** Run `data-quality-audit`; note `complete_pct`, `top100_complete`, `top_gap`.
   Launch the app and screenshot every page (the `visual-qa` skill) — judge what the BUYER
   sees, not what the tests say. Read `IMPROVEMENTS.md` for the standing backlog.

2. **Identify 50.** Produce a concrete, numbered list of 50 improvements grounded in what you
   just observed — real defects, missing decision value, trust gaps, data-depth levers, UX.
   Each item: one line, a rough impact (★1–5 on sellability) and effort (S/M/L). Split the
   50 across: data depth/coverage · valuation/scoring quality · decision tools · product/UX/
   trust · infra/ops. Skip nothing for being small; mark items blocked by ungettable data
   (sold prices, owner phones) as **go-to-market, not code** and don't fake them.

3. **Plan (task list).** Write the 50 into `IMPROVEMENTS.md` and create a tracked task list
   (TaskCreate) ordered by impact ÷ effort. A correctness bug jumps the queue. Say which
   items this pass will actually implement vs. which are blocked/deferred, and why.

4. **Implement.** Work the list top-down. Keep new logic pure and unit-tested in a module +
   test, not only in the UI. Fan independent items out to subagents where it helps. Update
   each task's status as you go (in_progress → completed). Batch-commit with the required
   trailers as coherent groups land — don't wait for all 50.

5. **Verify (blocking).** For every batch: `python -m pytest -q`, then `ruff check` and
   `black --check` over `src/ tests/ scripts/` — green before commit. For anything the buyer
   sees, re-launch the app and screenshot: **a UI fix isn't done until the new screenshot
   proves it.** Re-run `data-quality-audit` to measure data-depth items against their target
   (e.g. "year 49% → 62%"). Push to the designated branch.

6. **Critique & price.** Run `sellability-review` on the improved product with FRESH numbers
   (quote the new audit + real outputs). Output its 0–100 Sellability Score, the realistic
   price band/tier, the 3–6 reasons for that price, and what would 10× it. Append the
   before→after score to `IMPROVEMENT_LOG.md` and mark done items ✅/◐ in `IMPROVEMENTS.md`.

## Decide (end of pass)

If the score moved and code-addressable items remain, the next invocation runs another full
pass (find 50 more). If two consecutive passes don't move the score, STOP and report honestly
what now blocks it — usually sold-price data, a second portal, or weeks of accumulated
time-series (the moat), none of which more code can shortcut today.

## Guardrails (never violate)

- **Free solutions only** — no paid APIs/services.
- **Branch** `claude/holargos-property-scout-8yffib`; never push elsewhere. No PR unless asked.
- **Commit trailers** required: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  the `Claude-Session:` line. Never put the model identifier in commits/PRs/code/comments.
- **DB single-writer**: never rescore or write the prod DB while a scrape/enrich holds a write
  session. XE detail-page cadence ≥ 4 s (faster → 403s).
- **Stop-and-flag** before: DB schema changes, `strategy.yaml` scoring changes, adding a
  portal, or deleting data — note it in the commit body.
- **Honesty over score**: removing a false claim is a win even if the raw score dips.
