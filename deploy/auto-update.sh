#!/usr/bin/env bash
# Keep the live instance in sync with the repo's main branch — no manual SSH.
#
# Every tick it (1) converges cron + .env via reconcile.sh so config changes land too,
# then (2) pulls origin/main and rebuilds ONLY when the code changed, then (3) brings
# the stack up (honouring COMPOSE_PROFILES from .env, e.g. proxy/worker). Cheap no-op
# when already current. Installed by deploy/reconcile.sh; retrofit in deploy/README.md.
set -uo pipefail

APP_DIR="${HOLARGOS_DIR:-/opt/holargos}"
cd "$APP_DIR" || { echo "$(date -u) auto-update: $APP_DIR missing"; exit 1; }

# 1. Converge config (cron + new .env keys) — runs even if the code is unchanged, so
#    an older instance still picks up newly-added cron jobs / env defaults.
bash "$APP_DIR/deploy/reconcile.sh" || echo "$(date -u) auto-update: reconcile failed"

# 2. Pull code. Don't fail the run on a transient network/auth blip — retry next tick.
if ! git fetch --quiet origin main; then
  echo "$(date -u) auto-update: fetch failed (check the repo's GitHub token)"
  exit 0
fi

BUILD=""
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "$(date -u) auto-update: $(git rev-parse --short HEAD) -> $(git rev-parse --short origin/main), rebuilding"
  git reset --hard origin/main
  BUILD="--build"
fi

# 3. Apply. With no code change this is a fast no-op; with COMPOSE_PROFILES set it also
#    brings up the enabled profiles (e.g. the Caddy HTTPS proxy).
docker compose up -d $BUILD
echo "$(date -u) auto-update: up${BUILD:+ (rebuilt)}"
