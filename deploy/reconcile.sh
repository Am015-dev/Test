#!/usr/bin/env bash
# Converge this instance to the repo's intended runtime state — idempotent, free,
# no SSH. Run at first boot (cloud-init) AND on every auto-update tick, so an instance
# built before a change still picks up new .env keys and cron jobs without re-provision.
#
# It does NOT overwrite values you've set — it only ADDS what's missing. All free:
# pure bash + cron + docker compose.
set -uo pipefail

APP_DIR="${HOLARGOS_DIR:-/opt/holargos}"
cd "$APP_DIR" || { echo "$(date -u) reconcile: $APP_DIR missing"; exit 1; }

# 1. .env — create from the example if absent, then append any NEW keys the example
#    has gained since this box was built (preserves your existing values).
[ -f .env ] || cp .env.example .env
while IFS= read -r line; do
  case "$line" in
    [A-Z]*=*)
      key="${line%%=*}"
      if ! grep -q "^${key}=" .env; then
        echo "$line" >> .env
        echo "$(date -u) reconcile: added .env key ${key}"
      fi
      ;;
  esac
done < .env.example

# 2. cron — (re)install the canonical schedule. Lines are tagged "# holargos" so we
#    can replace prior versions cleanly regardless of the install path.
M="# holargos"
update="*/5 * * * * ${APP_DIR}/deploy/auto-update.sh >> /var/log/holargos-update.log 2>&1 ${M}"
daily="0 6 * * * cd ${APP_DIR} && docker compose run --rm web bash -c 'python scripts/enqueue.py && python scripts/worker.py && python scripts/notify.py' >> /var/log/holargos-daily.log 2>&1 ${M}"
health="0 7,19 * * * cd ${APP_DIR} && docker compose run --rm web python scripts/healthcheck.py >> /var/log/holargos-health.log 2>&1 ${M}"
( crontab -l 2>/dev/null | grep -v "${M}"; echo "$update"; echo "$daily"; echo "$health" ) | crontab -
echo "$(date -u) reconcile: cron + .env converged"
