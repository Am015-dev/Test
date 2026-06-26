---
name: ponytail-audit
description: >
  Audit the whole repository for over-engineering. Returns a ranked delete-list
  ordered by potential impact. Use when asked "audit this codebase", "audit for
  over-engineering", "what can I delete", "find bloat", or /ponytail-audit.
license: MIT
source: https://github.com/DietrichGebert/ponytail
---

# ponytail-audit — Rank the whole repo for deletion opportunities

Scans the **entire codebase**, not just the current diff. Returns a ranked list
ordered from largest potential cut first. Read-only — no changes are applied.

## What it targets

- Dependencies redundant with stdlib
- Single-implementation interfaces / one-product factories
- Delegating wrappers with no added value
- Single-export files that add indirection
- Unused configuration flags
- Speculative features with no callers
- `ponytail:` comments that have lost their upgrade trigger

## Output format

```
<tag> <what to cut>. <replacement>. [path:line]
```

Close with: `net: -<N> lines, -<M> deps possible.`

If nothing to cut: `Lean already. Ship.`

## Scope

Complexity and over-engineering only. Correctness, security, and performance
concerns go to `/code-review` or `/security-review`.
