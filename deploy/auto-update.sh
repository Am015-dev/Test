#!/usr/bin/env bash
# Keep the live instance in sync with the repo's main branch — no manual SSH.
#
# Pulls origin/main and rebuilds the app ONLY when the code actually changed, so it
# is a cheap no-op when already current and safe to run every few minutes from cron.
# Installed by deploy/cloud-init.yaml on first boot; see deploy/README for retrofit.
set -uo pipefail

APP_DIR="${HOLARGOS_DIR:-/opt/holargos}"
cd "$APP_DIR" || { echo "$(date -u) auto-update: $APP_DIR missing"; exit 1; }

# Don't fail the cron run on a transient network blip — just try again next tick.
git fetch --quiet origin main || { echo "$(date -u) auto-update: fetch failed"; exit 0; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0  # already up to date
fi

echo "$(date -u) auto-update: ${LOCAL:0:8} -> ${REMOTE:0:8}, rebuilding"
git reset --hard origin/main
docker compose up -d --build
echo "$(date -u) auto-update: done"
