# `.claude/` — agent toolkit for Holargos Scout

Everything an unsupervised Claude session needs to work on this project, in one place.
Project conventions/architecture live in the repo-root `CLAUDE.md`.

```
.claude/
├── skills/     # invokable skills (project workflows + vendored superpowers toolkit)
├── mcp/        # MCP server docs + reference config (live file is /.mcp.json at root)
└── plugins/    # plugin policy + how-to
```

## Skills (`skills/`)

Project skills (domain workflows — see each `SKILL.md`):

| Skill | Use for |
|---|---|
| `holargos-verify` | Test/lint gate + real-Postgres smoke + ship |
| `repair-collector` | A live collector returns 0 cards / wrong fields (markup changed) |
| `triage-scraper-health` | Healthcheck pages WARN/ERROR — diagnose + act |
| `db-schema-change` | Add/change a DB column safely (migration trap) |
| `add-portal` | Add a brand-new listing source |
| `finalize-portal-selectors` | Bring up Spitogatos/Indomio via FlareSolverr |
| `add-coverage-area` | Add a coverage municipality |
| `tune-scoring` | Change scoring weights / filters / thesis |

Plus the vendored **superpowers** general-workflow skills (brainstorming, writing-plans,
test-driven-development, systematic-debugging, requesting/receiving-code-review, …) —
attribution in `skills/NOTICE.md`.

## MCP servers (`mcp/`)

Live config: **`/.mcp.json`** (must be at repo root to auto-load). Reference copy +
full analysis: `mcp/`. Configured: **postgres** (read-only DB inspection), **playwright**
(render WAF/JS portals for selector work), **fetch** (server-rendered HTML pulls).
GitHub MCP is provided by the environment. See `mcp/README.md` for prerequisites
(notably `DATABASE_URI` for postgres, `npx playwright install chromium` for playwright).

## Plugins (`plugins/`)

superpowers is vendored as skills (ephemeral-container friendly); see `plugins/README.md`
for the rationale and how to install the full plugin instead.
