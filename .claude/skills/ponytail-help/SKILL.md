---
name: ponytail-help
description: >
  Quick reference for all ponytail commands and modes. Use when asked
  "ponytail help", "ponytail commands", or /ponytail-help.
license: MIT
source: https://github.com/DietrichGebert/ponytail
---

# ponytail-help — Quick reference

## Modes

| Level | Behaviour |
|-------|-----------|
| **lite** | Builds what's asked; names the lazier alternative in one line. User picks. |
| **full** | The lazy-senior ladder enforced. Default. |
| **ultra** | YAGNI extremist — deletion before addition, challenges requirements inline. |

## The ladder (full mode — stop at first rung that holds)

1. Does this need to exist at all? (YAGNI)
2. Already in this codebase? → reuse it.
3. Stdlib does it? → use it.
4. Native platform feature covers it? → use it.
5. Already-installed dependency solves it? → use it.
6. Can it be one line? → one line.
7. Only then: minimum code that works.

## Commands

| Command | What |
|---------|------|
| `/ponytail [lite\|full\|ultra]` | Activate / change intensity |
| `/ponytail-review` | Review diff for over-engineering (delete-list) |
| `/ponytail-audit` | Audit whole repo for bloat (ranked delete-list) |
| `/ponytail-debt` | Show deferred-shortcut ledger (`ponytail:` comments) |
| `/ponytail-help` | This reference |
| `stop ponytail` / `normal mode` | Deactivate |

## Output rule

Code first. At most three short lines: what was skipped, when to add it.
Pattern: `[code] → skipped: [X], add when [Y].`

## Source

[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) — MIT
