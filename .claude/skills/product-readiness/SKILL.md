---
name: product-readiness
description: Evaluate whether a product (or feature) is genuinely ready to show paying customers — across BOTH methodology/data-science and UI/UX — grade it against a hard rubric, and when it falls short, investigate what's missing and fix it, looping continuously until it passes. Use when asked "is this ready for customers / a final product", to audit a project's quality bar, or when told to make something customer-grade and not stop until it is. Runs the whole loop in ONE turn without checking in; only stops when it genuinely passes or hits a decision only the user can make.
---

# Product Readiness — evaluate, then close the gaps until it passes

You are the last line of defense before a customer sees this. Your job is not to
declare victory — it is to find every reason a smart, skeptical customer would say
"this isn't ready" and fix it, looping until none remain. Grade honestly. A polished
demo that recommends garbage, or a correct model behind a dev-tool UI, both FAIL.

## THE ONE RULE THAT MAKES THIS AUTONOMOUS

**Do not end your turn until the product PASSES or you hit a user-only decision.**

A skill is just instructions — nothing else forces you to keep going. So YOU keep
going: run the entire evaluate → fix → re-evaluate loop as one continuous stream of
tool calls in a single turn. Do **not** stop after one improvement to report progress.
Do **not** ask "should I continue?". Do **not** hand back a status update and wait.
Keep issuing tool calls — grade, fix, verify, re-grade — until one of exactly two
things is true:

1. **PASS** — every line of both rubrics passes with evidence. Then run the gate,
   commit, and report with the evidence.
2. **BLOCKED** — you need a decision only the user can make (budget, paid services,
   scope of the thesis, credentials/secrets). Then report *that specific decision* and
   stop. Nothing else is a reason to stop.

Track the loop with tasks (TaskCreate/TaskUpdate) so progress is visible while you run.
Between iterations, do not narrate — just take the next action.

## Operating rules

1. **Evidence over assertion.** Every PASS must be backed by something you ran or saw —
   a query result, a test, a screenshot, a live output. "It should work" is a FAIL.
   Screenshots are mandatory for any UI claim; never grade UI from the code alone.
2. **Adversarial framing.** For each area ask: "What would make a customer laugh at this
   or distrust it?" Top recommendations looking amateurish, false precision, a
   spreadsheet where a product should be, blocked/empty states — those are the failures
   that matter, not lint.
3. **Honest, not rosy.** If something can't be fixed here (infra, paid data, sandbox
   limits), say so plainly and route around it — never fake a PASS. Overclaiming
   readiness is the worst failure mode.
4. **Verify each fix end-to-end** before marking its line PASS (drive the flow,
   re-screenshot, re-query). A change you didn't observe working is not done.
5. **One gap at a time, highest impact first.** Recommendation quality and "looks like a
   dev tool" usually dominate — fix those before cosmetics.

## Two rubrics — grade every line PASS / FAIL with evidence

### A. Methodology & data (is the substance trustworthy?)

- **Coverage** — enough real inputs, from enough sources, to reflect the market? A
  single thin source is a FAIL unless honestly framed.
- **Completeness** — are the fields the model relies on actually populated (not mostly
  imputed)? Report the real % populated per key field.
- **Freshness** — does it refresh unattended and prove it (a real scheduled run)?
- **Model validity** — validated *out-of-sample*, not just in-sample. Report the honest
  metric. A model that fails a holdout is a FAIL.
- **No false precision** — uncertainty is shown (ranges/confidence), never a hard number
  the model can't support.
- **Recommendation quality** — THE decisive test. Would a domain expert respect the top
  5 outputs? If the ranking surfaces junk (or buries the obviously-good options), fix
  the scoring philosophy, not the cosmetics.
- **Robustness** — fail-soft on bad input / one dead dependency; covered by tests.
- **Transparency** — scores/decisions are explainable and the caveats are stated.

### B. UI / UX (does it look and feel like a product, not an internal tool?)

- **No dev-tool chrome** — framework scaffolding (Streamlit hamburger/footer/"Deploy",
  raw widget defaults) is hidden. If it looks like the framework's default template, FAIL.
- **Visual craft** — a coherent design system (type scale, spacing, restrained palette,
  real components). Default widgets on a page = FAIL.
- **Information hierarchy** — the customer's main question is answered above the fold; the
  eye is led, not dumped into a wall of controls or a raw table.
- **Data as product, not spreadsheet** — records render as designed cards/visuals with
  clear hierarchy (headline number, key signal, quality, a call to action), not a bare
  dataframe. A raw table where a product view belongs is a FAIL.
- **States** — empty, loading, and error states are designed and reassuring.
- **Trust cues** — freshness, sourcing, and confidence are visible.
- **Responsive & consistent** — holds together at different widths; nothing overflows.
- **Screenshot test** — render it and LOOK. Would you put this in a pitch deck? If not,
  iterate on the actual pixels until you would.

## Loop (run it continuously, no stopping between steps)

1. Establish a way to observe the product (launch the app + screenshot; run the pipeline
   + query outputs). If you can't observe it, fix that first.
2. Grade both rubrics, each line PASS/FAIL with evidence.
3. Take the highest-impact FAIL → find the root cause → implement → verify end-to-end.
4. Re-grade. Keep looping (back to step 3) — same turn, next tool call.
5. Only when every line PASSES (or you hit a user-only decision): run the full gate,
   commit, and report with screenshots/metrics — not adjectives.

## Anti-patterns (this is how it goes wrong)

- Ending the turn to report progress instead of continuing the loop.
- Declaring ready after one pass, or grading UI from code without a screenshot.
- Polishing cosmetics while the top recommendations are still wrong.
- Adding a CSS theme and calling a default layout "product-grade" — a real product
  replaces the default widgets/nav/table with designed components.
- Faking a PASS on something blocked by infra/paid data instead of stating it honestly.

## Optional: hard cross-turn enforcement (Stop hook)

The loop above runs within one turn. If you also want the runtime to *refuse to end the
turn* until the product passes (belt-and-suspenders, survives interruptions), install a
`Stop` hook. It is **opt-in and NOT auto-installed** — a hook that blocks stopping is a
self-perpetuating control change, so the user must add it deliberately.

1. Save this as `<repo>/.claude/hooks/readiness-gate.sh` (`chmod +x`):

```bash
#!/usr/bin/env bash
# Stop hook: keep the product-readiness loop going until the skill writes `done`.
set -euo pipefail
STATE="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)/readiness"
ACTIVE="$STATE/active"; DONE="$STATE/done"; ITER="$STATE/iter"; MAX=30
cat >/dev/null 2>&1 || true                 # consume the hook payload
[ -f "$ACTIVE" ] || exit 0                  # no run active -> normal stop
if [ -f "$DONE" ]; then rm -f "$ACTIVE" "$DONE" "$ITER"; exit 0; fi   # finished
n=$(( $(cat "$ITER" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$ITER"
[ "$n" -ge "$MAX" ] && { rm -f "$ACTIVE" "$ITER"; exit 0; }           # safety cap
R="product-readiness loop ACTIVE (pass ${n}/${MAX}) — do not stop. Re-grade both rubrics with fresh evidence (screenshot the app, query live outputs), fix the highest-impact FAIL, verify it, continue. When all lines PASS (or blocked on a user-only decision): run the gate, commit, then: touch \"${DONE}\""
printf '%s' "$R" | python3 -c 'import json,sys;print(json.dumps({"decision":"block","reason":sys.stdin.read()}))'
```

2. Register it in `<repo>/.claude/settings.json`:

```json
{ "hooks": { "Stop": [ { "hooks": [ { "type": "command",
  "command": "bash \"$CLAUDE_PROJECT_DIR/.claude/hooks/readiness-gate.sh\"" } ] } ] } }
```

3. To run in enforced mode: `mkdir -p <repo>/.claude/readiness && touch <repo>/.claude/readiness/active`,
   then work the loop. When it truly passes (or is user-blocked),
   `touch <repo>/.claude/readiness/done` releases the gate. Add `/.claude/readiness/` to
   `.gitignore`. The `MAX` cap guarantees the session can never be trapped forever.
