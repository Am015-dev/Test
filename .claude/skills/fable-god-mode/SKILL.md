---
name: fable-god-mode
description: Run token-disciplined Fable 5 sessions with the 10-80-10 model — use when starting any multi-step coding or research task, when work could fan out to parallel subagents, when the user mentions token cost, usage limits, or "save tokens", when the user asks to delegate or orchestrate work across models, or when the user asks to audit or clean up stale skills and CLAUDE.md left over from before Fable. Fable plans and reviews (the two 10s); cheaper Claude models (Opus, Sonnet, Haiku subagents) do the verbose middle 80%. Keeps Fable's expensive tokens on planning and quality ownership, not on work a cheaper model could do.
---

# Fable God Mode

## Core principle

You are running as **Fable 5**, the most expensive model in the stack. Every token you
spend doing work a cheaper model could do is waste. But quality ownership never
delegates: you plan, you review, you decide, you integrate.

**10-80-10** is the operating loop:

- **First 10%** — Fable plans.
- **Middle 80%** — cheaper Claude subagents execute the verbose work.
- **Last 10%** — Fable reviews, adjudicates, and integrates. Fable owns final quality.

The middle 80% is delegated so that, in the words of [Anthropic's cost guidance](https://code.claude.com/docs/en/costs),
"the verbose output stays in the subagent's context while only a summary returns to
your main conversation." Your context stays lean; your judgment stays in charge.

## The 10-80-10 loop

### First 10% — Fable plans

Do this yourself; it is the highest-leverage work in the session.

- **Understand intent.** What outcome does the user actually want? Restate it before decomposing.
- **Decompose** into tasks that are independent where possible, so they can run in parallel.
- **Write complete, self-contained subagent prompts.** A subagent has no access to this
  conversation — it sees only the prompt you give it. Include the goal, the relevant paths,
  the constraints, the definition of done, and the exact return format. Assume zero shared context.

### Middle 80% — delegate

Route each task to the cheapest model that can do it well:

- **Haiku** — simple, mechanical, high-volume: renames, boilerplate, log grepping, format
  conversion, mechanical edits. "For simple subagent tasks, specify `model: haiku` in your
  subagent configuration." Haiku is roughly an order of magnitude cheaper than premium
  models (see platform.claude.com pricing).
- **Opus / Sonnet** — research fan-outs, first drafts of hard code or prose, analysis that
  needs reasoning. Sonnet for most; Opus when the draft is genuinely hard.

**Subagent contract** (put this in every delegation prompt): write full artifacts to disk;
return a **compact summary of ≤10 lines** (what you did, where it lives, what to check next).
The verbose output stays in the subagent's context, not yours.

**Fan out in parallel.** Launch all independent agents in a single message so they run
concurrently. Only serialize when one task truly depends on another's output.

### Last 10% — Fable reviews

- Review each returned summary and its artifacts **against the plan** — not against the
  subagent's self-assessment.
- **Adjudicate findings on merit.** Accept what is correct, reject false positives with a
  stated reason, and fix what the subagent got wrong.
- **Never rubber-stamp.** A returned "done" is a claim, not a verification.
- **Union rule.** A reviewer's silence or approval never removes a concern you already had.
  Findings ADD; they do not subtract. Your own review stands unless actively refuted.
- Integrate the pieces into a coherent whole. This is your work, not the subagents'.

## Effort calibration

Match `/effort` to the step. Use **high** or **xhigh** for the first-10% planning and the
last-10% review; drop to the default for ordinary conversational turns. Reserve **max** for
the hardest adjudication.

Note: "Disabling thinking is not available on Fable 5, which always uses extended thinking."
The cost lever on Fable 5 is the `/effort` level (low | medium | high | xhigh | max), **not**
thinking toggles or `MAX_THINKING_TOKENS` — adaptive-reasoning models ignore nonzero token budgets.

## When NOT to delegate

Delegation has overhead. Do the work yourself when:

- It is a single-file, trivial edit.
- It is a quick factual answer or a lookup you can do in one step.
- It is a conversational turn — talking to the user is your job, not a subagent's.
- Writing a complete, self-contained delegation prompt would cost more than just doing the task.

## Stale-config audit

A **report-only** scan for configuration that degrades Fable sessions: pre-Fable-era skills
and CLAUDE.md instructions written for older models — thinking-toggle advice, token-budget
tuning, model-routing rules that predate Fable, or bloated always-on context.

Run it when the user asks to audit or clean up config, or when session behavior suggests
stale instructions are interfering (e.g. advice that contradicts Fable's always-on thinking).

Justification: "Aim to keep CLAUDE.md under 200 lines by including only essentials." Skills
load on demand, so moving specialized instructions into skills keeps the base context smaller
and the Fable session cleaner.

Defer **all** audit procedure — rules, archive, and restore steps — to `references/audit.md`.
The scan never modifies files on its own; it reports.

## Scope & control

- **A discipline, not a gate.** This skill never blocks a response and never
  forces a tool call. When the user asks to skip it — "just do it inline",
  "no delegation this time", "skip god mode" — comply without ceremony, for
  that task or that whole session. The user is always in control.
- **Model-relative.** If the session runs a different premium model (e.g.
  Opus), apply the same loop relative to it: plan and review at the session
  model's full power, delegate the verbose middle to cheaper models. The
  savings are largest on Fable 5, but the discipline is not Fable-only.

## References

These load on demand — read them when the task calls for it, not preemptively.

- **`references/routing.md`** — the full routing playbook and fan-out discipline: the routing
  table, the delegation prompt contract, review discipline, and effort calibration.
- **`references/audit.md`** — the stale-config audit rules and the archive / restore procedure.

Related docs: https://code.claude.com/docs/en/costs · https://code.claude.com/docs/en/sub-agents · https://code.claude.com/docs/en/model-config
