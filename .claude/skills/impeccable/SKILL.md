---
name: impeccable
description: Design-quality discipline for the Streamlit UI (src/scout/ui) — use when asked to critique, audit, polish, lay out, typeset, colorize, clarify copy, adapt to phone sizes, harden states, or make the app "look pretty / professional / not AI-sloppy". Vendored text of pbakaus/impeccable 4.8.0 (Apache 2.0) with the launcher, detector binary and live-browser tooling removed; measurements come from Playwright instead.
---

# Impeccable (vendored, text only)

Work as a design director would on an **Operate** surface (the visitor completes a task: find a
flat, compare two, read the checks). Scanability, consistency and native expectations outrank
expression; brand lives in precise details. The user is a Greek buyer on a 390 px phone,
often older; the copy is Greek only (`tests/test_copy.py` guards it).

## How to use it here

1. **Critique first** ([reference/critique.md](reference/critique.md)): two isolated
   assessments. A = design review from screenshots and source (the ten heuristics, cognitive
   load, persona red flags). B = measured evidence. Upstream B runs the `impeccable detect`
   binary; **here B is a Playwright script** that reads computed styles on the running app:
   text contrast, touch-target boxes, font-size and spacing values in use, `scrollWidth`,
   focus rings, radius and shadow declarations. Keep A and B apart until synthesis.
2. **Audit** ([reference/audit.md](reference/audit.md)) scores the five technical dimensions
   0–4; reuse B's numbers.
3. Read [reference/craft-floor.md](reference/craft-floor.md) immediately before any UI edit.
   Its bans hold (eyebrows, gradient text, glass as decoration, side-stripe borders, glyph
   icons, hard offset shadows, system display face as a voice, nested cards, hero-metric
   template, ghost cards with border and shadow both).
4. **Polish** ([reference/polish.md](reference/polish.md)) in its order: broken paths, missing
   states, hierarchy and drift, visual inconsistencies, cleanup. Refinement preserves the
   incumbent world (slate ink, one teal accent, off-white canvas, 12–16 px radii); it does not
   smuggle in a redesign.
5. Specific lenses when the critique points there: [layout](reference/layout.md),
   [typeset](reference/typeset.md), [colorize](reference/colorize.md),
   [clarify](reference/clarify.md), [adapt](reference/adapt.md),
   [harden](reference/harden.md), [onboard](reference/onboard.md),
   [quieter](reference/quieter.md), [distill](reference/distill.md),
   [component-review](reference/component-review.md), [operate](reference/operate.md),
   [ios](reference/ios.md) for the phone conventions.

## Streamlit constraints

- You do not own the DOM. Style through `[data-testid=…]` hooks and the project's own
  `hg-*` classes in `src/scout/ui/theme.py`; add a class name in a page module only when no
  hook exists. Never override Streamlit's Material Symbols font (icons turn into words).
- No web fonts, no CDNs (offline, strict CSP): the system stack is the face. Make it look
  deliberate through scale, weight, tracking and `font-variant-numeric: tabular-nums`.
- Verify by looking: Playwright at 390×844 and 1280×900, the real database, real copy.
  Batch the checks; fix what one look shows before looking again.
