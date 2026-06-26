---
name: ponytail-review
description: >
  Review the current diff for over-engineering: reinvented stdlib, unneeded
  dependencies, speculative abstractions, dead flexibility. Returns a delete-list,
  not a general review. Use when asked "review for over-engineering", "what can we
  delete", "is this over-engineered", "simplify review", or /ponytail-review.
license: MIT
source: https://github.com/DietrichGebert/ponytail
---

# ponytail-review — Hunt deletable code in the diff

Scans the **current diff only** (not the whole repo). Returns what can be cut
or replaced with something simpler. Does NOT touch correctness, security, or
performance — those belong in a separate `/code-review` pass.

## Detection tags

| Tag | Meaning |
|-----|---------|
| `delete:` | Unused code — no replacement needed |
| `stdlib:` | Reimplemented standard library functionality |
| `native:` | Custom code duplicating platform capability |
| `yagni:` | Single-use abstraction or config for one value |
| `shrink:` | Same logic expressible more concisely |

## Output format

One finding per line:
```
L<line>: <tag> <what>. <replacement>.
```

Close with: `net: -<N> lines possible.`

If nothing to cut: `Lean already. Ship.`

## Scope

Over-engineering only. For correctness/security bugs use `/code-review`.
For whole-repo audit use `/ponytail-audit`.
