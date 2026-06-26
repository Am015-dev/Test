---
name: ponytail-debt
description: >
  Harvest the ponytail: shortcut comments scattered in the codebase into a
  centralized ledger. Use when asked "ponytail debt", "what did ponytail defer",
  "list the shortcuts", "ponytail ledger", or /ponytail-debt.
license: MIT
source: https://github.com/DietrichGebert/ponytail
---

# ponytail-debt — Deferred shortcut ledger

Greps the codebase for `ponytail:` comments — the deliberate ceiling markers
left when ponytail consciously took a shortcut — and produces a centralized
ledger. Entries with no upgrade trigger are flagged as the highest rot risk.

## Comment convention

```python
# ponytail: global lock, per-account locks if throughput matters
# ponytail: naive O(n²) scan, add index when n > 10k
# ponytail: no retry, add backoff before going to prod
```

Format: `# ponytail: <ceiling>, <upgrade path>`

## Ledger output

| Location | What | Ceiling | Trigger |
|---|---|---|---|
| `src/x.py:42` | global lock | throughput-bound | load test fails |
| `src/y.py:88` | O(n²) scan | n > 10k rows | profiler |

Entries with no upgrade trigger are marked `⚠ no-trigger` — these are the
highest rot risk since there's no condition to revisit them.

## Scope

Read-only report. Can be written to `PONYTAIL-DEBT.md` if explicitly asked.
