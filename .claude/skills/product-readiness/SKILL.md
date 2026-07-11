---
name: product-readiness
description: Evaluate whether a product (or a feature) is genuinely ready to show paying customers — across BOTH methodology/data-science and UI/UX — score it against a hard rubric, and when it falls short, investigate what's missing and implement the fixes autonomously, looping until it passes. Use when asked "is this ready for customers / a final product", to audit a project's quality bar, or when told to make something customer-grade and not stop until it is. Runs autonomously; do not ask the user to confirm — only report when it genuinely passes or you hit a decision only they can make (budget, scope, credentials).
---

# Product Readiness — evaluate, then close the gaps until it passes

You are the last line of defense before a customer sees this. Your job is not to
declare victory — it is to find every reason a smart, skeptical customer would say
"this isn't ready" and fix it, looping until none remain. Grade honestly. A polished
demo that recommends garbage, or a correct model behind a dev-tool UI, both FAIL.

## Operating rules

1. **Autonomous loop.** Evaluate → find the biggest gap → implement it → re-evaluate.
   Repeat until every rubric line passes. Do not stop at the first improvement and do
   not report "done" until it genuinely passes. Only surface to the user for a decision
   that is truly theirs (budget, paid services, scope of the thesis, credentials/secrets).
2. **Evidence over assertion.** Every PASS must be backed by something you ran or saw —
   a query result, a test, a screenshot, a live output. "It should work" is a FAIL.
   Screenshots are mandatory for any UI claim; never grade UI from the code alone.
3. **Adversarial framing.** For each area ask: "What would make a customer laugh at this
   or distrust it?" The top recommendations looking amateurish, false precision, a
   spreadsheet where a product should be, blocked/empty states — these are the failures
   that matter, not lint.
4. **Honest, not rosy.** If something can't be fixed here (infra, paid data, sandbox
   limits), say so plainly and route around it — don't fake a pass. Overclaiming
   readiness is the worst failure mode.
5. **Verify each fix end-to-end** before marking its rubric line PASS (drive the flow,
   re-screenshot, re-query) — a change that isn't observed to work is not done.

## Two rubrics — grade every line PASS / FAIL with evidence

### A. Methodology & data (is the substance trustworthy?)

- **Coverage** — Are there enough real inputs, from enough sources, that a customer
  believes it reflects the market? A single thin source is a FAIL unless honestly framed.
- **Completeness** — Are the attributes the model relies on actually populated (not
  mostly imputed)? Report the real % populated for each key field.
- **Freshness** — Does it refresh unattended and prove it (a real scheduled run, not a
  manual poke)?
- **Model validity** — Validated *out-of-sample*, not just in-sample. Report the honest
  metric. A model that fails a holdout is a FAIL.
- **No false precision** — Uncertainty is shown (ranges/confidence), never a hard number
  the model can't support. Overconfident output is a FAIL.
- **Recommendation quality** — THE decisive test. Would a domain expert respect the top
  5 outputs? If the ranking surfaces junk (or buries the obviously-good options), the
  scoring is wrong — fix the scoring philosophy, not the cosmetics.
- **Robustness** — Fail-soft on bad input/one dead dependency; covered by tests.
- **Transparency** — Scores/decisions are explainable and the caveats are stated.

### B. UI / UX (does it look and feel like a product, not an internal tool?)

- **No dev-tool chrome** — Framework scaffolding (Streamlit hamburger/footer/"Deploy",
  raw widget defaults) is hidden. If it looks like the framework's default template, FAIL.
- **Visual craft** — A coherent design system (type scale, spacing rhythm, restrained
  palette, real components). Default widgets thrown on a page = FAIL.
- **Information hierarchy** — The one question the customer has is answered above the
  fold; the eye is led, not dumped into a wall of controls or a raw table.
- **Data as product, not spreadsheet** — Records render as designed cards/visuals with
  clear hierarchy (price, headline signal, quality, a call to action), not a bare
  dataframe/grid. A raw table where a product view belongs is a FAIL.
- **States** — Empty, loading, and error states are designed and reassuring, never blank
  or a stack trace.
- **Trust cues** — Freshness, sourcing, and confidence are visible so the user knows how
  much to rely on what they see.
- **Responsive & consistent** — Holds together at different widths; nothing overflows;
  spacing and alignment are consistent.
- **Screenshot test** — Render it and look. Would you put this in a pitch deck? If not,
  it's not ready — iterate on the actual pixels until it is.

## Loop

1. Establish/verify a way to observe the product (run the app + screenshot; run the
   pipeline + query outputs). If you can't observe it, fix that first.
2. Grade both rubrics, each line PASS/FAIL with the evidence.
3. Pick the highest-impact FAIL (recommendation quality and "looks like a dev tool"
   usually dominate). Investigate the root cause, implement the fix, verify it.
4. Re-grade. Keep looping. Track progress with tasks.
5. When every line PASSES with evidence, run the full quality gate (tests/lint), commit,
   and only then report — with the evidence (screenshots, metrics), not adjectives.

## Anti-patterns (these are how this goes wrong)

- Declaring ready after one pass, or grading UI from code without a screenshot.
- Polishing cosmetics while the top recommendations are still wrong.
- Adding a CSS theme and calling a Streamlit-default layout "product-grade" — a real
  product replaces the default widgets/nav/table with designed components.
- Faking a PASS on something blocked by infra/paid data instead of stating it honestly.
