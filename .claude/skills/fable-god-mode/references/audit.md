# Stale-Config Audit — Operating Reference

You are running a stale-config audit for **Fable God Mode**. Your job: scan the
user's accumulated Claude Code configuration (personal + project CLAUDE.md,
skills, subagent configs, settings), find items that waste tokens or degrade a
Fable 5 session, report them with reasons, and — only with per-item consent —
archive them reversibly. Follow this file exactly; the SKILL.md entrypoint
defers all procedure here.

## 1. Purpose & invariants

Fable 5 (Mythos-class, always-on extended thinking, adaptive reasoning) pays a
token tax for every skill description and every line of CLAUDE.md loaded into
context — in *every* session, whether or not the item is ever invoked. Config
written for older Claude models can also actively misdirect reasoning. This
audit surfaces that debt.

These invariants are absolute. They are not defaults you may relax:

- **REPORT-ONLY by default.** The audit's default output is a findings report.
  NOTHING is moved, edited, or deleted without explicit, per-item user
  confirmation. Do not batch-confirm; confirm each item on its own.
- **NEVER delete.** Remediation is *archive*: MOVE the item to
  `~/.claude/skills-archive/<YYYY-MM-DD>/`, preserving its relative structure.
- **Every archive run writes a manifest** (`manifest.json`) recording original
  paths + SHA-256 checksums, enabling a one-prompt restore.
- **CLAUDE.md is never bulk-rewritten.** Proposed edits are shown as a unified
  diff and applied only after approval. A timestamped backup of CLAUDE.md is
  written BEFORE any edit.
- **Respect other tools' managed blocks.** Content the fable-god-mode installer
  manages lives between `<!-- BEGIN fable-god-mode v<X> mode=<god|super> -->` …
  `<!-- END fable-god-mode -->`. NEVER flag or modify content inside ANOTHER
  tool's managed/sentinel block without naming that tool in the finding.
- **Enterprise/managed settings are out of scope.** Report-only; never propose
  changes there.
- **Never open or quote secrets/credentials files.** Flag by filename only.

## 2. Detection rules

Scan these locations: `~/.claude/CLAUDE.md`, project `.claude/CLAUDE.md` and any
nested/imported CLAUDE.md; personal skills `~/.claude/skills/<name>/SKILL.md`;
project skills `.claude/skills/<name>/SKILL.md`; subagent configs; and
`settings.json`. For each hit, record path, line where applicable, and an
exact quoted snippet.

### a. Obsolete thinking-era workarounds
Look for: `think hard`, `think harder`, `ultrathink`, "think step by step
before…" boilerplate baked into CLAUDE.md/skills; `MAX_THINKING_TOKENS` env or
settings entries; instructions that toggle, enable, or disable extended
thinking.
Why it degrades Fable: "Disabling thinking is not available on Fable 5, which
always uses extended thinking." Adaptive-reasoning models ignore nonzero
`MAX_THINKING_TOKENS` budgets — effort levels are the lever. These directives
are dead weight or silently ignored; the prose still costs context every turn.

### b. Mandatory-gate instructions
Look for: "you MUST invoke skill X before ANY response", "not negotiable",
"even a 1% chance", session-start mandates that require a tool call before
Claude may answer, clarify, or think.
Why it degrades Fable: they force tool calls on every turn regardless of
relevance, burning tokens and latency and pre-empting Fable's own judgment
about whether the skill fits.

### c. Model-routing rules for older model lineups
Look for: hardcoded ids like `claude-3-*`, `claude-3-5-sonnet-*`; rules premised
on Sonnet being the top model ("route hard tasks to Sonnet"); "always use
<old-id>" delegation rules; opus/haiku tiering that predates Fable.
Why it degrades Fable: stale routing misdirects delegation to weaker or
retired models and contradicts a Fable-first session.

### d. Oversized CLAUDE.md
Look for: any CLAUDE.md over 200 lines; large specialized instruction blocks
(language-specific style guides, one-off runbooks, tool tutorials) embedded
inline that would fit better as an on-demand skill. The line count EXCLUDES any
fable-god-mode managed block — the audit never counts the installer's own
lines toward the debt it reports.
Why it degrades Fable: Anthropic's cost docs say "Aim to keep CLAUDE.md under
200 lines by including only essentials." Skills load on demand, so moving
specialized instructions out of CLAUDE.md into skills keeps base context
smaller in every session.

### e. Dead or superseded skills
Look for: skills referencing tools, slash commands, MCP servers, or model ids
that no longer exist; skills duplicating a current built-in feature (e.g. a
hand-rolled web-search or git-commit skill now shipped natively).
Why it degrades Fable: their description text loads into every session (up to
1,536 chars per skill) even when never invoked — pure recurring cost for zero
capability.

### f. Overlapping trigger descriptions
Look for: multiple skills whose `description` fields claim the same or near-
identical trigger phrases ("use when the user asks to commit"; two "research"
skills; two image-prompt skills).
Why it degrades Fable: duplicated triggers bloat every session's skill listing
and cause misfires — Fable picks the wrong one or hesitates between them.

### g. Contradictory instructions
Look for: pairs of instructions that conflict — across CLAUDE.md levels
(personal vs project), or between CLAUDE.md and a skill, or between two skills.
Examples: "always run tests before committing" vs "never run tests
automatically"; conflicting formatting or tone rules.
Why it degrades Fable: Fable spends reasoning reconciling the conflict every
time both are in scope.
Detection is judgment-based — flag each with a **confidence** of LOW / MED /
HIGH and quote both sides.

## 3. Report format

Output a findings report only. Use this exact template. One numbered item per
finding.

```
### Finding <N>
- **Location:** <absolute/path:line, or path if line N/A>
- **Category:** <a–g> — <short category name>
- **Evidence:** > <exact quoted snippet>
- **Why it degrades Fable:** <one–two lines>
- **Proposed remediation:** <archive | CLAUDE.md diff | settings diff | leave-but-note>
- **Confidence:** <LOW | MED | HIGH>
```

After the numbered findings, print a summary table:

```
| # | Category | Location | Remediation | Confidence |
|---|----------|----------|-------------|------------|
```

Close the report with this exact sentence:

> Nothing has been changed. Confirm any item to proceed, one at a time.

## 4. Archive procedure (per-item consent)

Run this per item, only after the user confirms THAT item:

1. **Confirm the specific item** with the user (name the path). No batch
   confirmation.
2. **Compute SHA-256 of the item at its ORIGINAL path** (every file, when the
   item is a directory). This pre-move checksum is what goes in the manifest.
3. **Ensure the dated dir exists:** create `~/.claude/skills-archive/<YYYY-MM-DD>/`
   if absent (`<YYYY-MM-DD>` = today, local date).
4. **Move the item**, preserving its relative structure under the dated dir
   (e.g. `~/.claude/skills/foo/SKILL.md` → `…/<date>/skills/foo/SKILL.md`).
   Move the whole skill directory when the finding is a dead skill.
5. **Append to `manifest.json`** in the dated dir (create the file as a JSON
   array if absent) with the fields shown below, recording the pre-move checksum.
6. **Verify the move** by recomputing SHA-256 at the archive path and confirming
   it matches the pre-move value from step 2 (catches corruption on
   cross-filesystem moves).
7. **Report** the outcome for that item (moved, verified, manifest updated).

Manifest entry shape:

```json
[
  {
    "original_path": "/Users/<you>/.claude/skills/old-search/SKILL.md",
    "archive_path": "/Users/<you>/.claude/skills-archive/2026-07-02/skills/old-search/SKILL.md",
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "archived_at": "2026-07-02T14:33:07Z",
    "reason": "Duplicates built-in web search; description loads every session.",
    "finding_category": "e"
  }
]
```

## 5. Restore procedure

Trigger phrase: the user says **"restore my archived skills from <date>"**.

1. Read `~/.claude/skills-archive/<date>/manifest.json`.
2. For each entry, move the item from `archive_path` back to `original_path`,
   recreating any missing parent directories.
3. **Conflict guard:** if a NEW file already exists at `original_path`, do NOT
   overwrite it. Skip that entry and surface the conflict to the user for a
   decision.
4. **Verify** the restored file's SHA-256 against the manifest's `sha256`;
   report mismatches.
5. **Report per-item results** (restored / skipped-conflict / checksum-mismatch).
6. **Leave the manifest in place**, marked restored (e.g. add
   `"restored_at": "<ISO>"` to each successfully restored entry). Do not delete
   the manifest or the dated dir.

## 6. CLAUDE.md edit procedure

For any `CLAUDE.md diff` remediation:

1. **Backup first:** copy the file to `CLAUDE.md.bak-<ISO>` (alongside the
   original) BEFORE touching it. If this same run already produced a backup of
   this file (e.g. the installer's `claude_md_backup` minutes earlier), you may
   reuse it instead of writing a second one — state in the report which backup
   path the edit relies on.
2. **Show a unified diff** of the proposed change and wait for approval.
3. **Apply only on approval.** One logical change per approval — do not bundle
   unrelated edits into a single diff.
4. **Re-read the file after editing** to verify the change landed as shown.
5. Never bulk-rewrite; never touch content inside another tool's sentinel block
   (see §7). fable-god-mode's own sentinel block may be edited only when the
   finding is about that block.
6. A proposed `settings.json` edit (the "settings diff" remediation) follows
   this exact same procedure: timestamped backup → unified diff → apply only on
   approval → re-read to verify → one logical change per approval.

## 7. Out of scope

- **Enterprise / managed settings** — report-only, never propose changes.
- **Other tools' sentinel/managed blocks** — if a finding falls inside a block
  owned by another tool, name that tool in the finding and do not modify it.
- **Anything the user says to keep** — drop it from remediation, note the
  decision, move on.
- **Secrets / credentials files** — never open or quote them. If a finding
  concerns such a file, flag it by filename only.
