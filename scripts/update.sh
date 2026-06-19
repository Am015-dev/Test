#!/usr/bin/env bash
# Pull latest code and restart the app. No image rebuild needed.
# Run from /opt/holargos: bash scripts/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Pulling latest code..."
git pull origin main

echo "Restarting container..."
docker compose restart web

echo "Done. App running at http://$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo '<public-ip>'):8501"
