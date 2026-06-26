#!/bin/bash
# SessionStart hook — set up the Python environment for remote Claude Code sessions.
# Runs synchronously so the toolchain is ready before the first agent turn.
set -euo pipefail

# Only run in remote (web) sessions; local devs manage their own envs.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJ="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJ"

VENV="$PROJ/.venv"

# Create venv if absent (idempotent).
if [ ! -d "$VENV" ]; then
  echo "[session-start] Creating virtual environment..."
  python3 -m venv "$VENV"
fi

# Install / sync dev deps. --quiet suppresses per-package progress spam.
echo "[session-start] Installing holargos-scout[dev]..."
"$VENV/bin/pip" install --quiet -e ".[dev]"

# Persist toolchain paths for the session so every subsequent command
# picks up pytest, ruff, black, etc. without explicit activation.
ENV_FILE="${CLAUDE_ENV_FILE:-}"
if [ -n "$ENV_FILE" ]; then
  echo "PATH=$VENV/bin:$PATH" >> "$ENV_FILE"
  echo "PYTHONPATH=$PROJ/src" >> "$ENV_FILE"
fi

echo "[session-start] Done. Python: $($VENV/bin/python --version), pytest: $($VENV/bin/pytest --version 2>&1 | head -1)"
