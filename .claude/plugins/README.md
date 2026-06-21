# Plugins for Holargos Scout

Claude Code **plugins** bundle skills + slash-commands + hooks + MCP servers behind a
single install from a *marketplace*. This file records what's in use and what's
recommended, so the choice is documented rather than implicit.

## Current state

- **superpowers** (https://github.com/obra/superpowers, MIT) is the one toolkit we use.
  Its **skills are vendored** into `.claude/skills/` (see `.claude/skills/NOTICE.md`)
  rather than installed as a live plugin. Why vendored:
  - This repo runs in **ephemeral** remote containers; a marketplace-installed plugin
    lives in `~/.claude` and is wiped each session, whereas vendored skills are committed
    and available to every future session on the repo.
  - We only needed the skills, not the plugin's hooks/commands.

## Installing the full plugin instead (optional)

If you'd rather track upstream and get its commands/hooks too, install it as a real
plugin (interactive, in a Claude Code session) and remove the vendored copies to avoid
duplicate skill names:

```text
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

To enable a plugin for everyone on the project non-interactively, add it to
`.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "superpowers-marketplace": { "source": { "source": "github", "repo": "obra/superpowers-marketplace" } }
  },
  "enabledPlugins": { "superpowers@superpowers-marketplace": true }
}
```

## Recommended additional plugins

None required. This project's needs are covered by:
- the **project skills** (`.claude/skills/`) for domain workflows,
- the **MCP servers** (`.claude/mcp/`) for DB / browser / fetch,
- the environment-provided **GitHub** MCP for PRs/issues.

Re-evaluate if a recurring need emerges that a maintained plugin solves better than a
local skill (e.g. a richer Postgres or observability plugin).
