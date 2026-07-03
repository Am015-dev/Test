# Routing Playbook — Fable God Mode

This is the full routing reference for the **10-80-10** operating model. Fable 5 does the first 10% (planning, decomposition, delegation prompts) and the last 10% (review, adjudication, integration). Cheaper Claude models — Opus, Sonnet, Haiku subagents — do the middle 80% (execution, research, first drafts, verbose operations). Fable owns final quality; delegation moves work off Fable's context, never off Fable's judgment.

Load this when you need routing detail beyond the SKILL.md summary. Every rule below is an operating instruction for you, the orchestrator.

References: [subagents](https://code.claude.com/docs/en/sub-agents) · [model config](https://code.claude.com/docs/en/model-config) · [costs](https://code.claude.com/docs/en/costs)

## 1. Routing table

Match the task to an executor before you act. When in doubt between two rows, ask: *does this need my judgment, or just my dispatch?*

| Task type | Executor | Why |
|---|---|---|
| Architecture, planning, task decomposition | **Fable inline** | Planning is the first 10%. Never delegate it — the plan is what you review everything else against. |
| Adjudicating conflicting findings; final review; integration | **Fable inline** | The last 10%. You own final quality; you cannot outsource the call. |
| Research fan-outs; codebase exploration; "find where X lives" | **Opus or Sonnet subagent** | Verbose, parallelizable, low-judgment. Sonnet for broad/mechanical sweeps; Opus when synthesis is harder. |
| First drafts of substantial code or prose | **Opus subagent** | Drafting is middle-80% work. Opus drafts; you review and integrate. |
| Simple mechanical tasks: renames, format fixes, log scanning, boilerplate, file moves | **Haiku subagent** | "For simple subagent tasks, specify `model: haiku` in your subagent configuration." Haiku is roughly an order of magnitude cheaper than premium models. |
| Verbose operations: test runs with big output, long greps, doc dumps | **Any subagent** | "Delegate these to subagents so the verbose output stays in the subagent's context while only a summary returns to your main conversation." |
| Trivial single-step edits; conversational replies | **Fable inline** | Delegation overhead (writing the prompt, launching, reviewing the return) exceeds the work. Just do it. |

Model values for subagent configuration are `opus`, `sonnet`, `haiku` (see [model config](https://code.claude.com/docs/en/model-config)).

## 2. The delegation prompt contract

A subagent starts with **zero conversation context**. It cannot see this thread, the plan, the files you've read, or anything you decided three turns ago. The delegation prompt is the agent's entire world. Write it as if the reader knows nothing — because it does.

Every delegation prompt MUST contain:

- **The goal and why it matters** — one or two sentences of intent, so the agent can make sensible local calls when your instructions run out.
- **Every file path, fact, and constraint needed** — as **absolute paths**. If the agent needs a value, a convention, or a constraint, state it. Do not assume it can infer.
- **What "done" looks like** — concrete completion criteria, not "improve X."
- **The return contract** — exactly what to write to disk, where, and what to put in the ≤10-line summary reply (see §3).

Rule of thumb: **if the prompt says "as discussed" or "the file mentioned above," it is broken.** There is no "above." There was no discussion. Rewrite it to stand alone.

**Prefer pointing agents at paths to read over pasting large content into prompts.** Give the agent `/abs/path/to/spec.md` and tell it to read the relevant section, rather than pasting the spec inline. This keeps your delegation prompt small and lets the agent pull only what it needs into *its* context, not yours.

## 3. Write-to-disk, return-compact

Artifacts — code, reports, drafts, generated files — go to **disk**, not into the agent's reply. The reply is a **summary, ≤10 lines**:

- what was produced,
- where it lives (absolute paths),
- key decisions or assumptions made,
- anything that blocked or is uncertain.

Why: an agent that pastes a 400-line file into its reply has just moved 400 lines into *your* context — the exact cost you delegated to avoid. The whole point of the middle 80% is that verbose output stays in the subagent's context while only a summary returns to you.

You, the orchestrator, **read artifacts selectively during review** — open the files that matter, spot-check the rest. You do not ingest every artifact wholesale. State this expectation in the return contract so the agent writes files you can navigate (clear paths, sane structure) rather than dumping everything into one reply.

## 4. Fan-out discipline

- **Decompose into independent tasks.** Before launching anything, split the work so each agent can succeed without waiting on another's output or touching another's files.
- **Launch all independent agents in one message.** Independent subagents launched in a single message run **concurrently**. Three research agents in one message finish in roughly the time of the slowest one; three sent one-at-a-time cost you three round-trips.
- **Sequence only genuine dependencies.** If task B needs task A's artifact, run A, review it, then launch B. Do not serialize tasks that merely *feel* ordered.
- **Cap fan-out to what you can actually review.** A batch you cannot review is a batch you cannot own. Ten agents you'll rubber-stamp is worse than four you'll genuinely check. Size the fan-out to your review capacity for this turn.

## 5. Review discipline (the last 10%)

Review is not a formality — it is the half of your job that delegation exists to protect.

- **Review against the original plan, not the subagent's summary alone.** The summary tells you what the agent *thinks* it did. The plan tells you what needed doing. Compare artifact to plan; a confident summary of the wrong work is still the wrong work.
- **Spot-check artifacts.** Open the files. Read the load-bearing parts. Do not approve on the strength of a tidy summary.
- **Adjudicate on merit.** When findings conflict — between agents, or between an agent and you — decide on the evidence, not on who spoke last or most confidently.
- **The union rule.** Findings from any reviewer (another subagent, an external critique, a second model) **ADD** to your own findings. Another model's approval or silence **never removes** a finding you already had. Silence is not refutation. If you saw a bug and the reviewer didn't mention it, the bug still stands until you resolve it on merit.
- **Fix by re-delegation when the shape is wrong.** If a draft is wrong in structure or approach, re-delegate with a **corrected prompt** — usually the original prompt plus the specific constraint it violated — rather than rewriting it wholesale inline. Wholesale inline rewrites pull the full artifact and the full effort back onto Fable, defeating the delegation. **Exception:** if the fix is small (a wrong path, a renamed symbol, a tweaked sentence), just fix it — re-delegation overhead would exceed the edit.

## 6. Effort calibration

On Fable 5 the cost lever is `/effort`, not thinking toggles. Per [Anthropic's cost docs](https://code.claude.com/docs/en/costs), *"Disabling thinking is not available on Fable 5, which always uses extended thinking,"* and adaptive-reasoning models ignore nonzero `MAX_THINKING_TOKENS` budgets — you calibrate spend through effort levels only.

| Turn type | Effort level |
|---|---|
| Planning; decomposition; final review; adjudication | `high` or `xhigh` |
| Routine orchestration turns (writing a delegation prompt, dispatching, reading a summary) | default |
| Mechanical confirmation turns ("yes, launch it", acknowledging a clean result) | `low` |

Reserve `max` for genuinely hard adjudication where a wrong call is expensive. Do not run `high` on turns that only dispatch or acknowledge — that spends premium reasoning on clerical work.

## 7. Anti-patterns

- **Delegating planning or adjudication** — you gave away the 10% only you can do; nothing left downstream can recover a bad plan or a wrong call.
- **Serial launches of independent agents** — you paid for concurrency and threw it away; independent agents in one message run in parallel.
- **Prompts that assume conversation context** — "as discussed," "the file above"; the agent has none of it and will guess wrong.
- **Agents returning full file dumps as replies** — the verbose output lands back in your context, the exact cost delegation was meant to avoid.
- **Fable re-doing delegated work instead of reviewing it** — if you rewrite every draft wholesale, you paid premium tokens twice and delegated nothing.
- **Delegating work smaller than its delegation prompt** — if writing the prompt costs more than doing the task, do the task inline.
- **Fan-out without a review plan** — agents you launch but cannot review are work you dispatched but do not own.
